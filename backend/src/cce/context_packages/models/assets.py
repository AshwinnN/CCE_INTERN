"""Validated, domain-neutral governed asset contracts."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetPayload(Model):
    canonical_key: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Glossary(AssetPayload):
    asset_type: Literal["GLOSSARY"] = "GLOSSARY"
    term: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    synonyms: list[str] = Field(default_factory=list)


class PolicyRule(AssetPayload):
    asset_type: Literal["POLICY_RULE"] = "POLICY_RULE"
    rule: str = Field(min_length=1)
    entity_keys: list[str] = Field(default_factory=list)
    valid_from: str | None = None
    valid_until: str | None = None
    conditions: list[str] = Field(default_factory=list)


class SemanticMapping(AssetPayload):
    asset_type: Literal["SEMANTIC_MAPPING"] = "SEMANTIC_MAPPING"
    concept: str = Field(min_length=1)
    source_id: UUID
    database: str
    schema_name: str
    table: str
    columns: list[str] = Field(min_length=1)


class Entity(AssetPayload):
    asset_type: Literal["ENTITY"] = "ENTITY"
    name: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    source_keys: list[str] = Field(default_factory=list)


class Relationship(AssetPayload):
    asset_type: Literal["RELATIONSHIP"] = "RELATIONSHIP"
    from_entity: str
    to_entity: str
    relation_type: str


class VerifiedSQL(AssetPayload):
    asset_type: Literal["VERIFIED_SQL"] = "VERIFIED_SQL"
    source_id: UUID
    sql: str = Field(min_length=1)
    description: str
    dialect: str = "snowflake"


class Ambiguity(AssetPayload):
    asset_type: Literal["AMBIGUITY"] = "AMBIGUITY"
    description: str
    alternatives: list[str] = Field(min_length=2)
    resolution: str | None = None


Asset = Annotated[
    Glossary
    | PolicyRule
    | SemanticMapping
    | Entity
    | Relationship
    | VerifiedSQL
    | Ambiguity,
    Field(discriminator="asset_type"),
]
asset_adapter = TypeAdapter(Asset)


class Evidence(Model):
    evidence_id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    source_item_id: UUID
    source_uri: str
    document_id: str
    element_id: str | None = None
    agentic_memory_id: str | None = None
    ingestion_run_id: UUID
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernedAsset(Model):
    asset_id: UUID
    asset_revision_id: UUID
    domain_id: UUID
    revision_no: int
    payload: Asset
    evidence: list[Evidence] = Field(default_factory=list)
    approved_by: str | None = None


class PackageSnapshot(Model):
    package_id: UUID
    domain_id: UUID
    package_version_id: UUID
    version: int
    status: str = "ACTIVE"
    assets: list[GovernedAsset] = Field(default_factory=list)
