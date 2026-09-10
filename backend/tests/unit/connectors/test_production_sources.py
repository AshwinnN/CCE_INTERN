from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cce.sources.catalog import (SOURCE_TYPES, SchemaSelection, PostgreSQLSourceConfig,
    SQLServerSourceConfig, MySQLSourceConfig, GoogleDriveSourceConfig, selected_schemas)
from cce.connectors.structured.relational import RelationalConnector
from cce.connectors.unstructured.google_drive.connector import GoogleDriveConnector, EXPORTS
from cce.connectors.structured.snowflake.connector import SnowflakeConnector
from cce.connectors.base.models import ConnectionConfig


def test_catalog_is_exact_and_contains_form_schemas():
    assert set(SOURCE_TYPES) == {"snowflake", "postgresql", "sql_server", "mysql", "azure_blob", "google_drive"}
    for definition in SOURCE_TYPES.values():
        item = definition.public()
        assert item["status"] == "READY"
        assert item["config_schema"]["additionalProperties"] is False
        assert "password" not in item["config_schema"]["properties"]


@pytest.mark.parametrize("value", [{"mode":"all","schemas":["A"]}, {"mode":"selected","schemas":[]}, {"mode":"selected","schemas":["*"]}])
def test_schema_selection_validation(value):
    with pytest.raises(ValueError): SchemaSelection(**value)


def test_all_schema_selection_rediscovers_and_excludes_internal():
    config = PostgreSQLSourceConfig(host="h", database="d", user="u", schema_selection={"mode":"all"})
    connector = Mock()
    connector.list_schemas.side_effect = [["public", "pg_catalog", "pg_temp_1", "information_schema"], ["public", "sales", "pg_toast"]]
    assert selected_schemas("postgresql", config, connector) == ["public"]
    assert selected_schemas("postgresql", config, connector) == ["public", "sales"]


def test_registration_requires_schema_but_draft_does_not():
    definition = SOURCE_TYPES["postgresql"]
    raw = dict(host="h", database="d", user="u")
    definition.validate_config(raw, draft=True)
    with pytest.raises(ValueError): definition.validate_config(raw)
    with pytest.raises(ValueError): definition.validate_config({**raw, "password":"never store"}, draft=True)


class Driver:
    def __init__(self): self.statements=[]; self.closed=False; self.rollbacks=0; self.timeout=None
    def cursor(self): return Cursor(self)
    def rollback(self): self.rollbacks += 1
    def close(self): self.closed=True


class Cursor:
    def __init__(self, driver): self.driver=driver; self.description=[("value",)]; self.statement=""
    def execute(self, sql, params=None): self.statement=sql; self.driver.statements.append((sql,params))
    def fetchmany(self, count):
        if "fn_my_permissions" in self.statement: return []
        if "Ssl_cipher" in self.statement: return [("TLS_AES_256_GCM_SHA384",)]
        return [(i,) for i in range(count)]
    def close(self): pass


@pytest.mark.parametrize("source_type,model,dialect", [("postgresql",PostgreSQLSourceConfig,"LIMIT"),("mysql",MySQLSourceConfig,"LIMIT"),("sql_server",SQLServerSourceConfig,"TOP")])
def test_relational_driver_timeout_cap_and_guard(source_type, model, dialect):
    driver=Driver(); calls=[]
    def connect(*args,**kwargs): calls.append((args,kwargs)); return driver
    connector=RelationalConnector(source_type, model(host="h",database="d",user="u",max_rows=3), "opaque", driver_connect=connect, credential_loader=lambda _:"secret")
    assert connector.connect().read_only_verified
    rows=connector.execute_guarded_query("SELECT 1 AS value",timeout_seconds=2,max_rows=8)
    assert len(rows)==3
    assert dialect in driver.statements[-1][0]
    assert driver.rollbacks == 1
    for sql in ["DELETE FROM t", "SELECT 1; SELECT 2", "SELECT * INTO copied FROM t", "SELECT arbitrary_function()"]:
        with pytest.raises((ValueError, PermissionError)): connector.execute_guarded_query(sql,timeout_seconds=2,max_rows=3)
    if source_type=="postgresql": assert calls[0][1]["options"] == "-c default_transaction_read_only=on"
    if source_type=="sql_server": assert driver.timeout==2
    connector.close(); assert driver.closed


@pytest.mark.parametrize("mime", list(EXPORTS))
def test_drive_native_export_checks_scope_and_remains_transient(mime):
    session=Mock(); calls=[]
    def get(url,params=None,timeout=None):
        calls.append((url,params))
        result=Mock(); result.content=b"transient office bytes"
        result.json.return_value = {"mimeType":"application/vnd.google-apps.folder"} if url.endswith("/root") else {"id":"file", "mimeType":mime,"parents":["root"]}
        return result
    session.get.side_effect=get
    connector=GoogleDriveConnector(GoogleDriveSourceConfig(scope="folder",folder_id="root"),"ref","source",session_factory=lambda _:session,credential_loader=lambda _:"{}")
    connector.connect()
    assert connector.fetch_object("file") == b"transient office bytes"
    assert calls[-1][0].endswith("/export")
    assert calls[-1][1]["mimeType"] == EXPORTS[mime][0]
    connector.close(); session.close.assert_called_once()


def test_drive_rejects_unscoped_file():
    connector=GoogleDriveConnector(GoogleDriveSourceConfig(scope="folder",folder_id="root",recursive=False),"ref","s")
    with pytest.raises(PermissionError): connector._assert_scope({"parents":["elsewhere"]})
    with pytest.raises(ValueError): GoogleDriveSourceConfig(scope="folder")


def test_drive_shared_drive_pagination_and_nonrecursive_scope():
    session=Mock()
    responses = [
        {"id":"drive"},
        {"nextPageToken":"next", "files":[{"id":"folder","name":"Folder","mimeType":"application/vnd.google-apps.folder"}]},
        {"files":[{"id":"file","name":"notes.txt","mimeType":"text/plain"}]},
    ]
    def get(url,params=None,timeout=None):
        response=Mock(); response.json.return_value=responses.pop(0); return response
    session.get.side_effect=get
    connector=GoogleDriveConnector(GoogleDriveSourceConfig(scope="shared_drive",shared_drive_id="drive",recursive=False),"ref","s",session_factory=lambda _:session,credential_loader=lambda _:"{}")
    connector.connect()
    objects=connector.list_objects()["objects"]
    assert [item["object_id"] for item in objects]==["file"]
    params=session.get.call_args.kwargs["params"]
    assert params["driveId"]=="drive" and params["corpora"]=="drive" and params["pageToken"]=="next"
    assert "'drive' in parents" in params["q"]
    connector.close()


def test_sql_guard_emits_tsql_limit():
    from uuid import uuid4
    from cce.runtime.models import SourceSchema
    from cce.runtime.sql_guard import guard_query
    sql=guard_query("SELECT 1 AS value", SourceSchema(source_id=uuid4(), dialect="tsql"), max_rows=5)
    assert "TOP 5" in sql and "LIMIT" not in sql


def test_snowflake_password_does_not_load_private_key(monkeypatch):
    monkeypatch.setattr("cce.connectors.structured.snowflake.connector.load_credential", lambda _:"password-value")
    key_loader=Mock(side_effect=AssertionError("key loader invoked"))
    monkeypatch.setattr("cce.connectors.structured.snowflake.connector.load_snowflake_keypair_credential",key_loader)
    driver=Driver(); connect=Mock(return_value=driver)
    config=ConnectionConfig(adapter="snowflake",account_id="a",user="u",credential_ref="ref",database="d",schema="s",authentication="password",write_probe_enabled=False)
    connector=SnowflakeConnector(config,driver_connect=connect)
    connector.connect()
    assert connect.call_args.kwargs["password"]=="password-value"
    assert "private_key" not in connect.call_args.kwargs
    connector.close()
