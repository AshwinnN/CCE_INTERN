from uuid import uuid4

from cce.persistence.postgres.lifecycle_db import json_param
from cce.runtime.models import ColumnSchema, SourceSchema, TableSchema


class RuntimeRepository:
    def __init__(self, db):
        self.db = db

    def schema(self, source_id) -> SourceSchema:
        with self.db.transaction() as cur:
            cur.execute("SELECT source_type,config,name FROM cce_source WHERE source_id=%s", (str(source_id),))
            source = cur.fetchone()
            if source is None:
                raise KeyError("Source not found")
            dialect = {"snowflake": "snowflake", "postgresql": "postgres", "sql_server": "tsql", "mysql": "mysql"}.get(source["source_type"])
            if dialect is None:
                raise ValueError("Source does not support structured queries")
            cur.execute(
                """SELECT n.namespace_name,s.schema_name,t.table_name,c.column_name,c.native_data_type
                FROM cce_namespace n JOIN cce_schema s USING(namespace_id)
                JOIN LATERAL(SELECT snapshot_id FROM cce_schema_snapshot ss WHERE ss.schema_id=s.schema_id
                    ORDER BY captured_at DESC LIMIT 1) latest ON true
                JOIN cce_table t ON t.snapshot_id=latest.snapshot_id
                JOIN cce_column c ON c.table_id=t.table_id AND c.snapshot_id=t.snapshot_id
                WHERE n.source_id=%s ORDER BY t.table_name,c.ordinal_position""",
                (str(source_id),),
            )
            tables = {}
            for row in cur.fetchall():
                key = (row["namespace_name"], row["schema_name"], row["table_name"])
                if key not in tables:
                    tables[key] = TableSchema(
                        database=key[0], schema_name=key[1], name=key[2], columns=[]
                    )
                tables[key].columns.append(
                    ColumnSchema(
                        name=row["column_name"], data_type=row["native_data_type"]
                    )
                )
            selection = (source["config"] or {}).get("schema_selection")
            selected = list(tables.values())
            if selection and selection["mode"] == "selected":
                selected = [table for table in selected if table.schema_name in selection["schemas"]]
            return SourceSchema(source_id=source_id, source_name=source["name"], dialect=dialect, tables=selected)

    def workspace_schemas(self, workspace_uuid) -> list[SourceSchema]:
        with self.db.transaction() as cur:
            cur.execute(
                """SELECT s.source_id::text FROM cce_source s
                WHERE s.workspace_uuid=%s AND s.kind='structured' AND s.enabled AND s.archived_at IS NULL""",
                (str(workspace_uuid),),
            )
            ids = [r["source_id"] for r in cur.fetchall()]
        return [self.schema(i) for i in ids]

    def workspace_source_ids(self, workspace_uuid) -> list[str]:
        """Registered, enabled sources detected for the selected workspace."""
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT s.source_id::text FROM cce_source s WHERE s.workspace_uuid=%s AND s.enabled AND s.archived_at IS NULL",
                (str(workspace_uuid),),
            )
            return [r['source_id'] for r in cur.fetchall()]

    def create_trace(self, trace_id, request):
        with self.db.transaction() as cur:
            cur.execute("INSERT INTO query_trace(trace_id,question,actor_id,workspace_uuid,parent_trace_id,status) SELECT %s,%s,%s,workspace_uuid,%s,'RUNNING' FROM workspace WHERE workspace_id=%s AND status='ACTIVE'",
                        (str(trace_id),request.question,request.actor_id,request.metadata.get('parent_trace_id'),request.workspace_id))
            if cur.rowcount != 1: raise KeyError('Workspace not found')

    def finish_trace(self, response):
        with self.db.transaction() as cur:
            status=response.status if hasattr(response,'status') else response.context_on.status
            package=response.package if isinstance(response.package,dict) else response.package.model_dump(mode='json')
            cur.execute("UPDATE query_trace SET package_version_id=%s,status=%s,response=%s,finished_at=now() WHERE trace_id=%s AND workspace_uuid=%s",
                        (package.get('package_version_id'),status,json_param(response),str(response.trace_id),str(response.workspace.workspace_uuid)))

    def fail_trace(self, trace_id, error):
        with self.db.transaction() as cur:
            cur.execute("UPDATE query_trace SET status='FAILED',errors=%s,finished_at=now() WHERE trace_id=%s",(json_param([{'message':str(error)}]),str(trace_id)))

    def attempt(self, trace_id, branch, attempt):
        with self.db.transaction() as cur:
            cur.execute(
                """INSERT INTO sql_attempt(attempt_id,trace_id,branch,attempt_no,sql,parse_result,validation_result,guard_result,database_error,correction_guidance,status)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    str(attempt.attempt_id),
                    str(trace_id),
                    branch,
                    attempt.attempt_no,
                    attempt.sql,
                    json_param(attempt.parse_result),
                    json_param(attempt.validation_result),
                    json_param(attempt.guard_result),
                    attempt.database_error,
                    attempt.correction_guidance,
                    attempt.status,
                ),
            )

    def node(self, trace_id, name, start, end, request, result, error=None, model=None):
        with self.db.transaction() as cur:
            cur.execute(
                """INSERT INTO query_node_trace(node_trace_id,trace_id,node_name,started_at,finished_at,duration,model_name,structured_input,structured_output,error)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    str(uuid4()),
                    str(trace_id),
                    name,
                    start,
                    end,
                    (end - start).total_seconds(),
                    model,
                    json_param(request),
                    json_param(result),
                    json_param(error),
                ),
            )
