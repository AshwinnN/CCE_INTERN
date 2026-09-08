"""Fresh configured connector for each branch; no connection sharing across threads."""


class SQLExecutor:
    def __init__(self, source_service):
        self.sources = source_service

    def execute(self, schema, sql, timeout, max_rows):
        source = self.sources._require_source(str(schema.source_id))
        connector = self.sources._build_connector(source)
        try:
            connector.connect()
            if not hasattr(connector, "execute_guarded_query"):
                raise RuntimeError(
                    "Connector does not support bounded read-only execution"
                )
            return connector.execute_guarded_query(
                sql, timeout_seconds=timeout, max_rows=max_rows
            )
        finally:
            connector.close()
