"""DB-API relational connectors with bounded SELECT execution."""
from uuid import uuid4

from sqlglot import exp

from cce.connectors.base.connection import StructuredConnection
from cce.connectors.base.connector import StructuredConnector
from cce.security.credentials import load_credential


class RelationalConnector(StructuredConnector):
    def __init__(self, source_type, config, credential_ref, *, driver_connect=None, credential_loader=load_credential):
        self.source_type = source_type
        self.config = config
        self.credential_ref = credential_ref
        self._driver_connect = driver_connect
        self._credential_loader = credential_loader
        self._connection = None
        self.dialect = {"postgresql": "postgres", "sql_server": "tsql", "mysql": "mysql"}[source_type]

    def connect(self):
        c = self.config
        secret = self._credential_loader(self.credential_ref)
        try:
            if self.source_type == "postgresql":
                import psycopg2
                self._connection = (self._driver_connect or psycopg2.connect)(host=c.host, port=c.port,
                    dbname=c.database, user=c.user, password=secret, sslmode=c.ssl_mode,
                    connect_timeout=c.connection_timeout, options="-c default_transaction_read_only=on")
            elif self.source_type == "mysql":
                if self._driver_connect is None:
                    import mysql.connector
                    connect = mysql.connector.connect
                else:
                    connect = self._driver_connect
                self._connection = connect(host=c.host, port=c.port, database=c.database, user=c.user,
                    password=secret, connection_timeout=c.connection_timeout,
                    ssl_disabled=c.ssl_mode == "disabled")
                self._command("SET SESSION TRANSACTION READ ONLY")
                if c.ssl_mode == "required":
                    rows = self._query("SHOW SESSION STATUS LIKE 'Ssl_cipher'", limit=1)
                    if not rows or not list(rows[0].values())[-1]:
                        raise ValueError("MySQL connection requires TLS")
            else:
                if self._driver_connect is None:
                    import pyodbc
                    connect = pyodbc.connect
                else:
                    connect = self._driver_connect
                def quote(value): return "{" + str(value).replace("}", "}}") + "}"
                connection_string = ";".join(f"{key}={quote(value)}" for key, value in {
                    "DRIVER": "ODBC Driver 18 for SQL Server", "SERVER": f"{c.host},{c.port}",
                    "DATABASE": c.database, "UID": c.user, "PWD": secret,
                    "Encrypt": "yes" if c.encrypt else "no",
                    "TrustServerCertificate": "yes" if c.trust_server_certificate else "no",
                    "ApplicationIntent": "ReadOnly"}.items())
                self._connection = connect(connection_string, timeout=c.connection_timeout)
                # ApplicationIntent alone does not enforce read-only credentials.
                permissions = self._query("SELECT permission_name FROM fn_my_permissions(NULL, 'DATABASE') WHERE permission_name IN ('CONTROL', 'ALTER', 'INSERT', 'UPDATE', 'DELETE', 'CREATE TABLE', 'EXECUTE')", limit=100)
                object_permissions = self._query("SELECT p.permission_name FROM sys.objects o CROSS APPLY fn_my_permissions(QUOTENAME(SCHEMA_NAME(o.schema_id)) + '.' + QUOTENAME(o.name), 'OBJECT') p WHERE o.is_ms_shipped=0 AND p.permission_name IN ('CONTROL','ALTER','INSERT','UPDATE','DELETE','EXECUTE')", limit=1)
                if permissions or object_permissions:
                    raise ValueError("SQL Server credentials must be read-only")
        except Exception:
            self.close()
            raise
        return StructuredConnection(self, str(uuid4()), read_only_verified=True)

    def _command(self, statement):
        cursor = self._connection.cursor()
        try:
            cursor.execute(statement)
        finally:
            cursor.close()

    def _query(self, statement, params=None, *, limit):
        if self._connection is None:
            raise RuntimeError("Connector is not connected")
        cursor = self._connection.cursor()
        try:
            if params:
                cursor.execute(statement, params)
            else:
                cursor.execute(statement)
            names = [col[0] for col in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchmany(limit)]
        finally:
            cursor.close()

    def list_schemas(self):
        from cce.sources.catalog import is_user_schema
        if self.source_type == "mysql":
            return [self.config.database]
        # Schema inventory is metadata, not a sample-row cap. Detect truncation.
        rows = self._query("SELECT schema_name FROM information_schema.schemata", limit=100001)
        if len(rows) > 100000:
            raise ValueError("Schema inventory exceeds supported limit")
        return sorted(str(next(iter(r.values()))) for r in rows if is_user_schema(self.source_type, str(next(iter(r.values())))))

    def _identifier(self, name):
        return exp.to_identifier(name, quoted=True).sql(dialect=self.dialect)

    def get_schema_card(self, schema, max_tables=None):
        if schema not in self.list_schemas():
            raise ValueError("Schema is outside the accessible source scope")
        marker = "?" if self.source_type == "sql_server" else "%s"
        rows = self._query(f"SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema={marker} ORDER BY table_name, ordinal_position", [schema], limit=100001)
        if len(rows) > 100000:
            raise ValueError("Column inventory exceeds supported limit")
        tables = {}
        for raw in rows:
            row = {key.lower(): value for key, value in raw.items()}
            table = tables.setdefault(row["table_name"], {"name": row["table_name"], "columns": [], "row_count": None})
            table["columns"].append({"name": row["column_name"], "type": row["data_type"], "nullable": row["is_nullable"] == "YES"})
        selected = list(tables.values())[:max_tables] if max_tables else list(tables.values())
        for table in selected:
            relation = f"{self._identifier(schema)}.{self._identifier(table['name'])}"
            statement = f"SELECT TOP 1 * FROM {relation}" if self.source_type == "sql_server" else f"SELECT * FROM {relation} LIMIT 1"
            samples = self.execute_guarded_query(statement, timeout_seconds=self.config.connection_timeout, max_rows=1)
            table["sample_row"] = samples[0] if samples else {}
        return {"schema": schema, "tables": selected}

    def execute_query(self, sql, params=None):
        if params:
            raise ValueError("Parameterized runtime SQL is not supported")
        return self.execute_guarded_query(sql, timeout_seconds=self.config.connection_timeout, max_rows=self.config.max_rows)

    def execute_guarded_query(self, sql, *, timeout_seconds, max_rows):
        from cce.runtime.sql_guard import parse_query, guard_ast
        tree = parse_query(sql, self.dialect)
        guard_ast(tree)
        if timeout_seconds < 1 or max_rows < 1:
            raise ValueError("Timeout and row limit must be positive")
        if self.source_type == "postgresql":
            self._command(f"SET LOCAL statement_timeout = {int(timeout_seconds) * 1000}")
        elif self.source_type == "mysql":
            self._command(f"SET SESSION MAX_EXECUTION_TIME = {int(timeout_seconds) * 1000}")
        else:
            self._connection.timeout = int(timeout_seconds)
        bounded = exp.select("*").from_(tree.subquery("cce_source_result")).limit(min(max_rows, self.config.max_rows)).sql(dialect=self.dialect)
        try:
            return self._query(bounded, limit=min(max_rows, self.config.max_rows))
        finally:
            self._connection.rollback()

    def close(self):
        if self._connection is not None:
            connection, self._connection = self._connection, None
            connection.close()
