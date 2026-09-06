from cce.persistence.postgres.source_repository import PostgresSourceRepository


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if "INSERT INTO cce_source" in sql:
            config = getattr(params[5], "adapted", params[5])
            self.db["source"] = {
                "source_id": params[0],
                "adapter": params[1],
                "account_id": params[2],
                "kind": params[3],
                "credential_ref": params[4],
                "config": config,
                "enabled": params[6],
            }
            self.result = (params[0],)
        elif "SELECT source_id, adapter" in sql:
            self.result = self.db.get("source")
        elif "INSERT INTO cce_ingestion_run" in sql:
            self.db["run"] = {
                "run_id": params[0],
                "source_id": params[1],
                "status": "RUNNING",
                "objects_processed": 0,
                "objects_failed": 0,
                "error_message": None,
                "trace_id": params[2],
            }
        elif "UPDATE cce_ingestion_run" in sql:
            self.db["run"].update(
                {
                    "status": params[0],
                    "objects_processed": params[2],
                    "objects_failed": params[3],
                    "error_message": params[4],
                }
            )
        elif "SELECT run_id" in sql:
            self.result = self.db.get("run")

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self, *args, **kwargs):
        return FakeCursor(self.db)

    def commit(self):
        pass


def test_source_config_and_run_state_round_trip(monkeypatch):
    db = {}
    monkeypatch.setattr(
        "cce.persistence.postgres.source_repository.psycopg2.connect",
        lambda dsn: FakeConnection(db),
    )
    repo = PostgresSourceRepository("postgresql://test")

    saved_id = repo.save_source(
        adapter="local-fs",
        source_id="docs",
        credential_ref="env://LOCAL",
        kind="unstructured",
        config={"root_path": "/tmp/docs"},
    )
    source = repo.get_source(saved_id)
    assert source["credential_ref"] == "env://LOCAL"
    assert source["config"] == {"root_path": "/tmp/docs"}

    run_id = repo.create_ingestion_run(saved_id, trace_id="trace-1")
    repo.update_ingestion_run(run_id, "SUCCESS", objects_processed=2, objects_failed=0)
    run = repo.get_ingestion_run(run_id)
    assert run["status"] == "SUCCESS"
    assert run["objects_processed"] == 2
