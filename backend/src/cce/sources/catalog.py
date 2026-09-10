"""Typed production source configuration; credentials never belong in config."""
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SchemaSelection(Config):
    mode: Literal["all", "selected"]
    schemas: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_selection(self):
        if self.mode == "all" and self.schemas:
            raise ValueError("All-schema selection requires an empty schemas list")
        if self.mode == "selected" and not self.schemas:
            raise ValueError("Select at least one schema")
        if any(not s.strip() or s == "*" for s in self.schemas):
            raise ValueError("Schema names must be explicit, nonempty names")
        if len(set(self.schemas)) != len(self.schemas):
            raise ValueError("Duplicate schema selection")
        return self


class SnowflakeSourceConfig(Config):
    account_id: str = Field(min_length=1, title="Account Identifier")
    user: str = Field(min_length=1)
    authentication: Literal["key_pair", "password"]
    role: str = Field(min_length=1)
    warehouse: str = Field(min_length=1)
    database: str = Field(min_length=1)
    schema_selection: SchemaSelection | None = None
    max_rows: int = Field(default=1000, ge=1, le=100000)
    login_timeout_s: int = Field(default=20, ge=1)
    network_timeout_s: int = Field(default=30, ge=1)


class RelationalConfig(Config):
    host: str = Field(min_length=1)
    database: str = Field(min_length=1)
    user: str = Field(min_length=1)
    max_rows: int = Field(default=1000, ge=1, le=100000)
    connection_timeout: int = Field(default=20, ge=1)


class PostgreSQLSourceConfig(RelationalConfig):
    port: int = Field(default=5432, ge=1, le=65535)
    ssl_mode: Literal["require", "verify-ca", "verify-full", "disable"] = "require"
    schema_selection: SchemaSelection | None = None


class SQLServerSourceConfig(RelationalConfig):
    port: int = Field(default=1433, ge=1, le=65535)
    encrypt: bool = True
    trust_server_certificate: bool = False
    schema_selection: SchemaSelection | None = None


class MySQLSourceConfig(RelationalConfig):
    port: int = Field(default=3306, ge=1, le=65535)
    ssl_mode: Literal["required", "preferred", "disabled"] = "required"


class AzureBlobSourceConfig(Config):
    authentication: Literal["connection_string", "service_principal"]
    container: str = Field(min_length=1)
    prefix: str = ""
    recursive: bool = True
    account_url: str | None = None
    tenant_id: str | None = None
    client_id: str | None = None

    @model_validator(mode="after")
    def validate_auth(self):
        fields = (self.account_url, self.tenant_id, self.client_id)
        if self.authentication == "service_principal" and not all(fields):
            raise ValueError("Service principal requires account_url, tenant_id and client_id")
        if self.authentication == "connection_string" and any(fields):
            raise ValueError("Service principal fields are not used with connection-string authentication")
        return self


class GoogleDriveSourceConfig(Config):
    scope: Literal["folder", "shared_drive"]
    folder_id: str | None = None
    shared_drive_id: str | None = None
    recursive: bool = True

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope == "folder" and (not self.folder_id or self.shared_drive_id):
            raise ValueError("Folder scope requires only folder_id")
        if self.scope == "shared_drive" and (not self.shared_drive_id or self.folder_id):
            raise ValueError("Shared-drive scope requires only shared_drive_id")
        return self


@dataclass(frozen=True)
class SourceTypeDefinition:
    source_type: str
    label: str
    kind: Literal["structured", "unstructured"]
    config_model: type[Config]
    schema_capable: bool = False

    def validate_config(self, value, *, draft=False):
        config = self.config_model.model_validate(value)
        if self.schema_capable and not draft and config.schema_selection is None:
            raise ValueError("Discover and select schemas before registration")
        return config

    def public(self):
        schema = self.config_model.model_json_schema()
        return dict(source_type=self.source_type, label=self.label, kind=self.kind,
                    status="READY", schema_capable=self.schema_capable, config_schema=schema)


SOURCE_TYPES = {
    item.source_type: item for item in (
        SourceTypeDefinition("snowflake", "Snowflake", "structured", SnowflakeSourceConfig, True),
        SourceTypeDefinition("postgresql", "PostgreSQL", "structured", PostgreSQLSourceConfig, True),
        SourceTypeDefinition("sql_server", "SQL Server", "structured", SQLServerSourceConfig, True),
        SourceTypeDefinition("mysql", "MySQL", "structured", MySQLSourceConfig),
        SourceTypeDefinition("azure_blob", "Azure Blob", "unstructured", AzureBlobSourceConfig),
        SourceTypeDefinition("google_drive", "Google Drive", "unstructured", GoogleDriveSourceConfig),
    )
}


def source_type_definition(source_type):
    try:
        return SOURCE_TYPES[source_type]
    except KeyError:
        raise ValueError(f"Unsupported production source type: {source_type}") from None


def is_user_schema(source_type, name):
    lower = name.lower()
    excluded = {"snowflake": {"information_schema"}, "postgresql": {"information_schema"},
                "sql_server": {"sys", "information_schema", "guest", "db_owner", "db_datareader", "db_datawriter"}}
    return lower not in excluded.get(source_type, set()) and not (source_type == "postgresql" and lower.startswith("pg_"))


def selected_schemas(source_type, config, connector):
    if source_type == "mysql":
        return [config.database]
    selection = config.schema_selection
    if selection is None:
        raise ValueError("Schema selection is required")
    available = [s for s in connector.list_schemas() if is_user_schema(source_type, s)]
    if selection.mode == "all":
        return sorted(available)
    missing = set(selection.schemas) - set(available)
    if missing:
        raise ValueError(f"Selected schemas unavailable: {', '.join(sorted(missing))}")
    return selection.schemas
