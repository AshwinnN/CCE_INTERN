from uuid import uuid4

from cce.ingestion.orchestrator import persist_structured_metadata_node
from cce.persistence.postgres.metadata_repository import PostgreSQLMetadataRepository


def test_registered_source_catalogue_is_visible_to_package_validation(system):
    source_id = str(uuid4())
    with system.db.transaction() as cur:
        cur.execute(
            "INSERT INTO cce_source(source_id,adapter,account_id,kind) VALUES(%s,'snowflake',%s,'structured')",
            (source_id, 'catalogue-' + source_id),
        )
    repo = PostgreSQLMetadataRepository(system.db.dsn)
    try:
        state = persist_structured_metadata_node({
            'kind': 'structured', 'adapter': 'snowflake', 'source_id': source_id,
            'schema_database': 'TEST_DB', 'warnings': [], '_metadata_repository': repo,
            'raw_content': {'schema': 'PUBLIC', 'tables': [
                {'name': 'ITEMS', 'columns': [{'name': 'ITEM_ID', 'type': 'TEXT'}]}
            ]},
        })
        assert state['warnings'] == []
        schema = system.traces.schema(source_id)
        assert [(t.database, t.schema_name, t.name) for t in schema.tables] == [
            ('TEST_DB', 'PUBLIC', 'ITEMS')
        ]
        assert schema.tables[0].columns[0].name == 'ITEM_ID'
        with system.db.transaction() as cur:
            cur.execute('SELECT count(*) AS n FROM cce_source WHERE account_id=%s', (source_id,))
            assert cur.fetchone()['n'] == 0
    finally:
        repo.close()
