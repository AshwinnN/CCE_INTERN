"""Structural validation only; human reviewers determine business truth."""

from cce.context_packages.models.assets import GovernedAsset, asset_adapter
from cce.runtime.sql_guard import guard_query


def validate_effective(assets: list[GovernedAsset], schema_lookup) -> list[str]:
    errors = []
    keys = {a.payload.canonical_key for a in assets}
    entities = {
        a.payload.canonical_key for a in assets if a.payload.asset_type == "ENTITY"
    }
    identities = set()
    for asset in assets:
        p = asset_adapter.validate_python(asset.payload.model_dump())
        identity = (p.asset_type, p.canonical_key)
        if identity in identities:
            errors.append(f"Duplicate asset: {identity}")
        identities.add(identity)
        for key in p.dependencies:
            if key not in keys:
                errors.append(f"{p.canonical_key}: missing dependency {key}")
        if (
            p.asset_type == "RELATIONSHIP"
            and not {p.from_entity, p.to_entity} <= entities
        ):
            errors.append(f"{p.canonical_key}: unknown graph entity")
        if p.asset_type == "POLICY_RULE" and not set(p.entity_keys) <= entities:
            errors.append(f"{p.canonical_key}: unknown policy entity")
        if p.asset_type == "SEMANTIC_MAPPING":
            schemas = schema_lookup(p.source_id)
            matches = [
                t
                for t in schemas.tables
                if t.database == p.database
                and t.schema_name == p.schema_name
                and t.name == p.table
            ]
            if not matches or not set(p.columns) <= {
                c.name for c in matches[0].columns
            }:
                errors.append(f"{p.canonical_key}: unknown source/table/column mapping")
        if p.asset_type == "VERIFIED_SQL":
            try:
                guard_query(p.sql, schema_lookup(p.source_id), max_rows=1000)
            except (ValueError, PermissionError) as exc:
                errors.append(f"{p.canonical_key}: {exc}")
    return errors
