#!/usr/bin/env python3
"""CCE structured-metadata repository. One interface
(repository.base.MetadataRepository), one implementation today
(repository.postgresql_metadata_repository.PostgreSQLMetadataRepository) --
same interface/factory discipline as connectors/ (see connectors/__init__.py).
"""
from repository.base import MetadataRepository, SchemaChange, SchemaSnapshot

__all__ = ["MetadataRepository", "SchemaSnapshot", "SchemaChange"]
