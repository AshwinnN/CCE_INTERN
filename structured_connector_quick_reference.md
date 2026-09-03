# Structured Connector Architecture — Quick Reference

## Directory Structure (Final)

```
project-root/
├── connectors/                                ← NEW PACKAGE
│   ├── __init__.py
│   ├── README.md
│   │
│   ├── base/                                  ← Abstract interfaces (shared)
│   │   ├── __init__.py
│   │   ├── connector.py                       # StructuredConnector ABC (60 lines)
│   │   ├── connection.py                      # StructuredConnection class (30 lines)
│   │   ├── models.py                          # ConnectionConfig dataclass (40 lines)
│   │   └── exceptions.py                      # StructuredConnectorException (10 lines)
│   │
│   ├── snowflake/                             ← Snowflake implementation
│   │   ├── __init__.py
│   │   ├── connector.py                       # SnowflakeConnector class (200 lines)
│   │   ├── config.py                          # Snowflake config validation (50 lines)
│   │   ├── errors.py                          # Snowflake-specific errors (20 lines)
│   │   └── queries.py                         # Pre-built SQL queries (50 lines, optional)
│   │
│   ├── postgres/                              ← Postgres (Phase 2)
│   │   ├── __init__.py
│   │   ├── connector.py
│   │   ├── config.py
│   │   └── errors.py
│   │
│   ├── bigquery/                              ← BigQuery (Phase 3)
│   │   ├── __init__.py
│   │   ├── connector.py
│   │   ├── config.py
│   │   └── errors.py
│   │
│   ├── factory.py                             # ConnectorFactory (50 lines)
│   ├── registry.py                            # Adapter registry (optional, Phase 2)
│   └── utils.py                               # Shared utilities (50 lines)
│
├── tests/
│   ├── connectors/                            ← Tests for connectors
│   │   ├── __init__.py
│   │   ├── test_base_connector.py             # Abstract base tests (40 lines)
│   │   ├── test_snowflake_connector.py        # Unit tests (80 lines)
│   │   ├── test_snowflake_integration.py      # Integration tests (60 lines, optional)
│   │   └── fixtures/
│   │       ├── mock_snowflake.py              # Test doubles (50 lines)
│   │       └── test_data.sql                  # Test fixtures
│   │
│   └── test_ingestion_workflow.py             # (Existing, will use new connector)
│
├── agents/
│   ├── ingestion_workflow.py                  # (Modify: fetch_structured node)
│   └── connector_agent/
│       └── ...
│
└── common/
    └── tools/
        └── ...
```

---

## One-Liner Descriptions

| File | Lines | Purpose |
|------|-------|---------|
| `base/connector.py` | 60 | `StructuredConnector` ABC — the contract |
| `base/connection.py` | 30 | `StructuredConnection` — proven-safe handle |
| `base/models.py` | 40 | `ConnectionConfig` dataclass |
| `base/exceptions.py` | 10 | `StructuredConnectorException` hierarchy |
| `snowflake/connector.py` | 200 | `SnowflakeConnector` implementation |
| `snowflake/config.py` | 50 | Snowflake-specific validation, defaults |
| `snowflake/errors.py` | 20 | Snowflake error mapping |
| `snowflake/queries.py` | 50 | Pre-built SQL templates (optional) |
| `factory.py` | 50 | `ConnectorFactory.create(config)` |
| `registry.py` | 50 | Optional: adapter registry, discovery |
| `utils.py` | 50 | Shared helpers (logging, retry, etc.) |
| Tests | 180 | Unit + integration test suite |

**Total Phase 1: ~600 lines**

---

## The One-Page Summary

### What It Does

```
Ingestion Orchestrator (doesn't know about Snowflake)
        ↓
"I need a structured source connector for adapter=snowflake"
        ↓
ConnectorFactory.create(config: ConnectionConfig)
        ↓
Returns: StructuredConnector (generic interface)
        ↓
Orchestrator calls:
  - connector.connect()           → proves read-only
  - connector.get_schema_card()   → gets table/column metadata
  - connector.execute_query(sql)  → runs SELECT
  - connector.close()             → cleanup
        ↓
Same code works for Postgres, BigQuery, anything
```

### Why It Works

1. **Interface-based** — orchestrator sees `StructuredConnector` (abstract), not `SnowflakeConnector` (concrete)
2. **Factory pattern** — instantiation is hidden behind a factory function
3. **Same method signatures** — `get_schema_card()` returns identical shape for Snowflake, Postgres, BigQuery
4. **Extensible** — add Postgres: 1 new folder, ~150 lines, register in factory
5. **Testable** — mock `StructuredConnector`, unit test orchestrator, never need Snowflake for those tests

### The Key Insight

```python
# Orchestrator code (same for all databases):
connector = ConnectorFactory.create(config)  # Could be Snowflake, Postgres, anything
schema = await connector.get_schema_card(schema_name)

# Snowflake-specific code (only in connectors/snowflake/):
class SnowflakeConnector(StructuredConnector):
    async def get_schema_card(self, schema: str) -> Dict:
        cursor.execute("""SELECT ... FROM information_schema.columns...""")
        # Snowflake SQL syntax here
```

Swapping Snowflake for Postgres:
- Change config.adapter = "postgres"
- Add `connectors/postgres/connector.py`
- **Orchestrator code: zero changes**

---

## Implementation Phases

### Phase 1 (Week 1): Snowflake Only

**Create:**
- 4 files in `connectors/base/` (abstract layer, ~140 lines)
- 4 files in `connectors/snowflake/` (implementation, ~320 lines)
- 2 files in `connectors/` root (`factory.py`, `utils.py`, ~100 lines)
- 3 test files (~180 lines)

**Total: ~740 lines**

**Deliverable:** Ingestion workflow can connect to any Snowflake instance via `StructuredConnector` interface

**Test it:**
```bash
pytest tests/connectors/test_snowflake_connector.py -v
# All tests pass
```

---

### Phase 2 (Week 2): Add Postgres

**Create:**
- 4 files in `connectors/postgres/` (~320 lines, copy-paste from Snowflake with SQL changes)
- 2 test files (~180 lines)

**Modify:**
- `connectors/factory.py` — add 1 line to register PostgresConnector
- `.env` — add Postgres config vars (same pattern as Snowflake)

**Total new lines: ~500**

**Deliverable:** Same orchestrator code now works for Postgres, no changes needed

**Test it:**
```bash
pytest tests/connectors/test_postgres_connector.py -v
# All tests pass (same tests as Snowflake, different adapter)
```

---

### Phase 3 (Week 3): Add BigQuery

Same as Phase 2, but with BigQuery's REST API instead of SQL driver.

---

## Key Files to Implement First

**Do in this order:**

1. **`connectors/base/connector.py`**
   - Define `StructuredConnector` ABC
   - 4 abstract methods: `connect()`, `get_schema_card()`, `execute_query()`, `close()`
   - No Snowflake names, pure contract

2. **`connectors/base/models.py`**
   - `ConnectionConfig` dataclass (adapter, account_id, user, credential_ref, database, schema, role)
   - Optional Snowflake-specific fields (warehouse, cluster) — but in dataclass with defaults=None

3. **`connectors/snowflake/connector.py`**
   - Implement every method from `StructuredConnector` ABC
   - Write-probe logic (CREATE TEMPORARY TABLE, catch permission error)
   - Schema discovery (query information_schema.columns)

4. **`connectors/factory.py`**
   - `ConnectorFactory.create(config: ConnectionConfig) → StructuredConnector`
   - Registry dict: `{"snowflake": SnowflakeConnector}`

5. **`agents/ingestion_workflow.py`** (modify)
   - `fetch_structured()` node: use factory to create connector, call interface methods

6. **Tests** (parallel with implementation)
   - Mock `StructuredConnector` for unit tests
   - Real Snowflake for integration tests (optional, can run live)

---

## Success Criteria

- ✅ `connector = ConnectorFactory.create(config)` returns a `StructuredConnector`
- ✅ `connector.connect()` proves read-only via write-probe
- ✅ `connector.get_schema_card()` returns table/column metadata
- ✅ `connector.execute_query("SELECT ...")` runs and returns rows
- ✅ All tests pass
- ✅ Ingestion workflow uses connector without knowing it's Snowflake
- ✅ Adding Postgres later requires no changes to orchestrator or tests

---

## Abstract vs Concrete — The Golden Rule

| Belongs in `base/` (abstract) | Belongs in `snowflake/` (concrete) |
|---|---|
| `StructuredConnector` class | `SnowflakeConnector` class |
| `connect()` method signature | Snowflake connection logic (key-pair auth) |
| `get_schema_card()` return type | Snowflake SQL: `SELECT ... FROM information_schema` |
| `ConnectionConfig` dataclass | `warehouse` field (Snowflake-specific) |
| Exception hierarchy | Mapping Snowflake permission errors → `StructuredConnectorException` |

If you find yourself writing Snowflake-specific code in `base/`, move it to `snowflake/`.  
If you find yourself hardcoding "Snowflake" in `base/`, you've gone wrong.

---

## Copy-Paste Checklist

```python
# base/connector.py
from abc import ABC, abstractmethod
from typing import Dict, List, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ConnectionConfig:
    adapter: str
    account_id: str
    user: str
    credential_ref: str
    database: str
    schema: str
    role: Optional[str] = None
    warehouse: Optional[str] = None
    timeout_ms: int = 30000

class StructuredConnectorException(Exception):
    pass

class StructuredConnector(ABC):
    @abstractmethod
    async def connect(self) -> "StructuredConnection": ...
    
    @abstractmethod
    async def get_schema_card(self, schema: str) -> Dict[str, Any]: ...
    
    @abstractmethod
    async def execute_query(self, sql: str, params: List = None) -> List[Dict]: ...
    
    @abstractmethod
    async def close(self): ...

class StructuredConnection:
    def __init__(self, connector: StructuredConnector, connection_id: str):
        self.connector = connector
        self.connection_id = connection_id
        self.read_only_verified = True
        self.created_at = datetime.utcnow()
```

```python
# snowflake/connector.py
from connectors.base.connector import StructuredConnector, StructuredConnection, ConnectionConfig

class SnowflakeConnector(StructuredConnector):
    def __init__(self, config: ConnectionConfig):
        self.config = config
        self._connection = None
    
    async def connect(self) -> StructuredConnection:
        # Load credential
        # Connect to Snowflake
        # Run write-probe
        # Return StructuredConnection
        pass
    
    async def get_schema_card(self, schema: str) -> Dict:
        # Query information_schema.columns
        # Return schema + tables + columns
        pass
    
    async def execute_query(self, sql: str, params: List = None) -> List[Dict]:
        # Run SELECT, return rows
        pass
    
    async def close(self):
        # Close Snowflake connection
        pass
```

```python
# factory.py
from connectors.base.connector import StructuredConnector, ConnectionConfig
from connectors.snowflake.connector import SnowflakeConnector

class ConnectorFactory:
    _connectors = {"snowflake": SnowflakeConnector}
    
    @staticmethod
    def create(config: ConnectionConfig) -> StructuredConnector:
        cls = ConnectorFactory._connectors[config.adapter]
        return cls(config)
```

---

## Recommended Reading Order

1. **This file** (5 min) — overview + directory structure
2. **`structured_connector_architecture.md`** (30 min) — full design + code examples
3. **Implement `base/connector.py`** — abstract base is foundation
4. **Implement `snowflake/connector.py`** — concrete implementation
5. **Implement `factory.py`** — glue
6. **Write tests** — validate everything works
7. **Integrate with ingestion workflow** — wire it up

---

Done. This is a production-grade abstraction that scales from Snowflake today to 10 databases tomorrow without touching the orchestrator.
