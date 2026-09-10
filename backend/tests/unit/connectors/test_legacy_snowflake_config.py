from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from cce.sources.catalog import normalize_stored_config, source_type_definition
from cce.sources.service import SourceService
from cce.runtime.sql_executor import SQLExecutor


def legacy_config():
    return dict(account_id="account", user="reader", role="reader", warehouse="WH",
                database="ERP", schema="ERP_COS_APPAREL")


def test_saved_config_conversion_preserves_scope_and_original():
    original = legacy_config()
    before = deepcopy(original)
    converted = normalize_stored_config("snowflake", original)
    parsed = source_type_definition("snowflake").validate_config(converted)
    assert parsed.authentication == "key_pair"
    assert parsed.schema_selection.schemas == ["ERP_COS_APPAREL"]
    assert original == before
    assert normalize_stored_config("snowflake", converted) == converted


def test_new_registration_still_requires_explicit_auth_and_selection():
    with pytest.raises(ValidationError):
        source_type_definition("snowflake").validate_config(legacy_config())
    modern = normalize_stored_config("snowflake", legacy_config())
    del modern["authentication"]
    with pytest.raises(ValidationError):
        source_type_definition("snowflake").validate_config(normalize_stored_config("snowflake", modern))


def test_explicit_password_preserved_and_conflicting_scope_rejected():
    config = {**legacy_config(), "authentication": "password"}
    assert normalize_stored_config("snowflake", config)["authentication"] == "password"
    config["schema_selection"] = {"mode": "all", "schemas": []}
    with pytest.raises(ValueError, match="Conflicting"):
        normalize_stored_config("snowflake", config)


@pytest.mark.parametrize("branch", ["ON", "OFF"])
def test_runtime_branches_build_legacy_source_and_execute_count(branch):
    source = dict(source_id="source", source_type="snowflake", enabled=True,
                  config=legacy_config(), credential_ref="env://TEST_KEY")
    repository = Mock()
    repository.get_internal_source.return_value = source
    service = SourceService(source_repository=repository, metadata_repository=None,
                            checkpoint_store=None, index_client=None, ingestion_repository=None)
    connector = Mock()
    connector.execute_guarded_query.return_value = {"rows": [[42]]}
    sql = "SELECT COUNT(*) FROM ERP_COS_APPAREL.ITEM_VARIANTS"
    with patch("cce.connectors.factory.SnowflakeConnector", return_value=connector) as factory:
        result = SQLExecutor(service).execute(SimpleNamespace(source_id="source"), sql, 30, 1000)
    config = factory.call_args.args[0]
    assert config.authentication == "key_pair"
    assert config.schema == "ERP_COS_APPAREL"
    assert config.write_probe_enabled is False
    assert result == {"rows": [[42]]}
    connector.execute_guarded_query.assert_called_once_with(sql, timeout_seconds=30, max_rows=1000)
    connector.close.assert_called_once()
