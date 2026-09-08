"""Shared synchronous SQL LangGraph with one retry budget for every failure stage."""

from datetime import datetime, timezone
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from pydantic import Field

from cce.context_packages.models.assets import Model
from cce.runtime.models import (
    SQLAttempt,
    SQLCandidate,
    SQLErrorAnalysis,
    SQLErrorRequest,
    SQLGenerationRequest,
    SQLResult,
    ValidationResult,
)
from cce.runtime.sql_guard import guard_ast, guard_query, parse_query, validate_scope


class SQLWork(Model):
    request: SQLGenerationRequest
    trace_id: UUID
    branch: str
    attempts: list[SQLAttempt] = Field(default_factory=list)
    current: SQLAttempt | None = None
    result: SQLResult | None = None
    error: str | None = None
    stage: str = ""


class SQLState(TypedDict):
    work: SQLWork


class SQLPipeline:
    def __init__(self, settings, llm, executor, traces):
        self.settings = settings
        self.llm = llm
        self.executor = executor
        self.traces = traces
        g = StateGraph(SQLState)
        for name in (
            "generate_sql",
            "parse_sql",
            "validate_sql",
            "guard_sql",
            "execute_sql",
            "describe_sql_error",
            "persist_attempt",
        ):
            fn = getattr(self, name)

            def node(state, fn=fn):
                work = SQLWork.model_validate(state["work"])
                started = datetime.now(timezone.utc)
                before = work.model_copy(deep=True)
                result = None
                error = None
                try:
                    result = fn(work)
                    return {"work": result}
                except Exception as exc:
                    error = {"message": str(exc)}
                    raise
                finally:
                    self.traces.node(
                        work.trace_id,
                        work.branch + "." + fn.__name__,
                        started,
                        datetime.now(timezone.utc),
                        before,
                        result,
                        error,
                    )

            g.add_node(name, node)
        g.add_edge(START, "generate_sql")
        stages = [
            "generate_sql",
            "parse_sql",
            "validate_sql",
            "guard_sql",
            "execute_sql",
        ]
        for a, b in zip(stages, stages[1:]):
            g.add_conditional_edges(
                a,
                lambda s, next_node=b: (
                    "describe_sql_error" if s["work"].error else next_node
                ),
            )
        g.add_conditional_edges(
            "execute_sql",
            lambda s: "describe_sql_error" if s["work"].error else "persist_attempt",
        )
        g.add_edge("describe_sql_error", "persist_attempt")
        g.add_conditional_edges(
            "persist_attempt", lambda s: END if s["work"].result else "generate_sql"
        )
        self.graph = g.compile()

    def run(self, request: SQLGenerationRequest, trace_id, branch) -> SQLResult:
        if not self.settings.sql_generation_enabled:
            return SQLResult(
                status="FAILED",
                error_code="SQL_GENERATION_FAILED",
                message="SQL generation is disabled",
            )
        work = SQLWork(request=request, trace_id=trace_id, branch=branch)
        return self.graph.invoke(
            {"work": work},
            config={"recursion_limit": 20 * (self.settings.sql_max_retries + 1)},
        )["work"].result

    def generate_sql(self, w: SQLWork) -> SQLWork:
        w.current = SQLAttempt(attempt_no=len(w.attempts) + 1)
        w.error = None
        w.stage = "SQL_GENERATION_FAILED"
        try:
            candidate = self.llm.invoke(
                "sql",
                "Generate one read-only SQL query using only the supplied source schema. Use governed context only when supplied. No external functions or cross-source access.",
                w.request,
                SQLCandidate,
            )
            w.current.sql = candidate.sql
        except Exception as exc:
            w.error = str(exc)
        return w

    def parse_sql(self, w: SQLWork) -> SQLWork:
        w.stage = "SQL_PARSE_FAILED"
        try:
            parse_query(w.current.sql, w.request.schema_context.dialect)
            w.current.parse_result = ValidationResult(valid=True)
        except Exception as exc:
            w.error = str(exc)
            w.current.parse_result = ValidationResult(
                valid=False, error_code=w.stage, message=w.error
            )
        return w

    def validate_sql(self, w: SQLWork) -> SQLWork:
        w.stage = "SQL_VALIDATION_FAILED"
        try:
            validate_scope(
                parse_query(w.current.sql, w.request.schema_context.dialect),
                w.request.schema_context,
            )
            w.current.validation_result = ValidationResult(valid=True)
        except Exception as exc:
            w.error = str(exc)
            w.current.validation_result = ValidationResult(
                valid=False, error_code=w.stage, message=w.error
            )
        return w

    def guard_sql(self, w: SQLWork) -> SQLWork:
        w.stage = "SQL_GUARD_FAILED"
        try:
            guard_ast(parse_query(w.current.sql, w.request.schema_context.dialect))
            w.current.guard_result = ValidationResult(valid=True)
        except Exception as exc:
            w.error = str(exc)
            w.current.guard_result = ValidationResult(
                valid=False, error_code=w.stage, message=w.error
            )
        return w

    def execute_sql(self, w: SQLWork) -> SQLWork:
        w.stage = "SQL_EXECUTION_FAILED"
        try:
            sql = guard_query(
                w.current.sql, w.request.schema_context, self.settings.sql_max_rows
            )
            rows = self.executor.execute(
                w.request.schema_context,
                sql,
                self.settings.sql_timeout_seconds,
                self.settings.sql_max_rows,
            )
            w.current.sql = sql
            w.current.status = "SUCCESS"
            w.result = SQLResult(status="SUCCESS", sql=sql, rows=rows)
        except Exception as exc:
            w.error = str(exc)
            w.current.database_error = w.error
        return w

    def describe_sql_error(self, w: SQLWork) -> SQLWork:
        # The repair model receives only SQL and the exact failure, never answer history.
        try:
            analysis = self.llm.invoke(
                "sql",
                "Describe the SQL failure and give concise correction guidance.",
                SQLErrorRequest(sql=w.current.sql, error=w.error),
                SQLErrorAnalysis,
            )
            w.current.correction_guidance = analysis.correction_guidance
        except Exception as exc:
            w.current.correction_guidance = f"Error analysis unavailable: {exc}"
        w.current.status = w.stage
        w.request = w.request.model_copy(
            update={
                "previous_sql": w.current.sql,
                "raw_error": w.error,
                "correction_guidance": w.current.correction_guidance,
            }
        )
        return w

    def persist_attempt(self, w: SQLWork) -> SQLWork:
        self.traces.attempt(w.trace_id, w.branch, w.current)
        w.attempts.append(w.current)
        if w.result:
            w.result.attempts = w.attempts
        elif len(w.attempts) >= 1 + self.settings.sql_max_retries:
            w.result = SQLResult(
                status="FAILED",
                error_code="RETRIES_EXHAUSTED",
                message=w.error,
                attempts=w.attempts,
                sql=w.current.sql,
            )
        return w
