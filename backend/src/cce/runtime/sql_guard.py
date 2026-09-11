"""AST-based SQL boundary shared by both branches and package validation."""

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from cce.runtime.models import SourceSchema


def parse_query(sql: str, dialect: str = "snowflake"):
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.ParseError as exc:
        raise ValueError(str(exc)) from exc
    if len(statements) != 1 or statements[0] is None:
        raise PermissionError("Exactly one SQL statement is required")
    return statements[0]


def _matches(identifier, known: str) -> bool:
    if identifier is None:
        return True
    if identifier.args.get("quoted"):
        return identifier.name == known
    return identifier.name.upper() == known.upper()


def matching_tables(reference, schema):
    return [
        table
        for table in schema.tables
        if _matches(reference.this, table.name)
        and _matches(reference.args.get("db"), table.schema_name)
        and _matches(reference.args.get("catalog"), table.database)
    ]


def validate_scope(tree, schema: SourceSchema):
    for scope in traverse_scope(tree):
        physical = {}
        for alias, (_, source) in scope.selected_sources.items():
            if not isinstance(source, exp.Table):
                continue  # CTE/subquery resolved by sqlglot scope
            matches = matching_tables(source, schema)
            if len(matches) != 1:
                raise ValueError(
                    f"Table outside selected source or ambiguous: {source.sql()}"
                )
            physical[alias.upper()] = [column.name for column in matches[0].columns]
        for column in scope.columns:
            if column.table and column.table.upper() in physical:
                if not any(
                    _matches(column.this, name)
                    for name in physical[column.table.upper()]
                ):
                    raise ValueError(f"Unknown column: {column.sql()}")
            if (
                not column.table
                and physical
                and len(physical) == len(scope.selected_sources)
            ):
                aliases = [e.alias for e in scope.expression.expressions if e.alias]
                if not any(_matches(column.this, name) for name in aliases) and not any(
                    _matches(column.this, name)
                    for names in physical.values()
                    for name in names
                ):
                    raise ValueError(f"Unknown column: {column.sql()}")


def guard_ast(tree):
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise PermissionError("Only read-only SELECT queries and CTEs are allowed")
    forbidden = {
        "Insert",
        "Update",
        "Delete",
        "Merge",
        "Create",
        "Alter",
        "Drop",
        "TruncateTable",
        "Command",
        "Copy",
        "Put",
        "Get",
        "Call",
        "Into",
        "Lock",
        "Transaction",
        "Set",
        "Use",
        "Grant",
        "Revoke",
    }
    for node in tree.walk():
        if type(node).__name__ in forbidden:
            raise PermissionError(f"Forbidden SQL operation: {type(node).__name__}")
        # Unknown/UDF/external functions can have side effects even inside SELECT.
        if isinstance(node, exp.Anonymous):
            raise PermissionError(f"Unapproved SQL function: {node.name}")
        if isinstance(node, exp.Table) and not isinstance(node.this, exp.Identifier):
            raise PermissionError("Dynamic or external table access is not allowed")


def guard_query(
    sql: str, schema: SourceSchema | None = None, max_rows: int = 1000
) -> str:
    dialect = schema.dialect if schema else "snowflake"
    tree = parse_query(sql, dialect)
    guard_ast(tree)
    if schema:
        validate_scope(tree, schema)
    # Outer limit caps UNION as well as ordinary queries, independent of model text.
    return f"SELECT * FROM ({tree.sql(dialect=dialect)}) AS cce_bounded_result LIMIT {int(max_rows)}"


def enforce_select_only(sql: str) -> None:
    guard_ast(parse_query(sql))


def referenced_tables(sql: str, schema: SourceSchema):
    result = {}
    for scope in traverse_scope(parse_query(sql, schema.dialect)):
        for _, source in scope.selected_sources.values():
            if not isinstance(source, exp.Table):
                continue
            for table in matching_tables(source, schema):
                result[(table.database, table.schema_name, table.name)] = table
    return list(result.values())
