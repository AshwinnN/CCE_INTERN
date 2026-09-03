# Structured Source Connector Architecture
## Abstraction Layer for Any Database (Snowflake, Postgres, BigQuery, etc.)

---

## Design Principle

**One interface, many implementations.**

```
┌─────────────────────────────────────────────────────────┐
│ Ingestion Orchestrator (LangGraph)                      │
│ Doesn't know: Snowflake, Postgres, BigQuery exist      │
└────────────────┬────────────────────────────────────────┘
                 │
                 ↓
        ┌─────────────────────┐
        │ StructuredConnector │  ← Interface (abstract)
        │ (ABC)               │
        │                     │
        │ - connect()         │
        │ - get_schema()      │
        │ - get_sample_row()  │
        │ - probe_write()     │
        │ - execute_query()   │
        │ - close()           │
        └────────┬────────────┘
                 │
        ┌────────┴─────────────────────┬─────────────────┐
        ↓                              ↓                 ↓
  ┌──────────────┐          ┌────────────────┐    ┌────────────┐
  │ Snowflake    │          │ Postgres       │    │ BigQuery   │
  │ Connector    │          │ Connector      │    │ Connector  │
  │              │          │                │    │            │
  │ (impl)       │          │ (impl)         │    │ (impl)     │
  └──────────────┘          └────────────────┘    └────────────┘
```

The orchestrator calls `StructuredConnector.connect()` and gets back a connection.
It doesn't know which concrete implementation it got — doesn't care.
Adding a new database: new folder, new implementation, register it, done.

---

## Directory Structure

```
connectors/                                    ← NEW PACKAGE
├── __init__.py
├── README.md
│
├── base/                                      ← Abstract interfaces
│   ├── __init__.py
│   ├── connector.py                           # StructuredConnector ABC
│   ├── connection.py                          # Connection interface
│   ├── models.py                              # Shared data models
│   └── exceptions.py                          # Base exception classes
│
├── snowflake/                                 ← Snowflake implementation
│   ├── __init__.py
│   ├── connector.py                           # SnowflakeConnector class
│   ├── connection.py                          # SnowflakeConnection class
│   ├── config.py                              # Snowflake-specific config
│   ├── errors.py                              # Snowflake-specific errors
│   └── queries.py                             # Pre-built SQL queries
│
├── postgres/                                  ← Postgres (for future)
│   ├── __init__.py
│   ├── connector.py
│   ├── connection.py
│   ├── config.py
│   └── errors.py
│
├── bigquery/                                  ← BigQuery (for future)
│   ├── __init__.py
│   ├── connector.py
│   ├── connection.py
│   ├── config.py
│   └── errors.py
│
├── factory.py                                 ← ConnectorFactory (instantiation)
├── registry.py                                ← Connector registry (discovery)
├── models.py                                  ← Shared data models
└── utils.py                                   ← Shared utilities

tests/
├── connectors/                                ← Tests for connectors
│   ├── __init__.py
│   ├── test_base_connector.py
│   ├── test_snowflake_connector.py
│   ├── test_snowflake_integration.py          # Live test (optional)
│   └── fixtures/
│       ├── mock_snowflake.py
│       └── test_data.sql
```

---

## Core Architecture (Top → Bottom)

### Layer 1: Abstract Base Class

**`connectors/base/connector.py`** (60 lines)

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

@dataclass
class ConnectionConfig:
    """Credential + connection metadata, database-agnostic."""
    adapter: str                    # "snowflake", "postgres", "bigquery"
    account_id: str                 # account/project identifier
    user: str
    credential_ref: str             # "env://...", "vault://..."
    database: str
    schema: str
    role: Optional[str] = None
    warehouse: Optional[str] = None # Snowflake-specific
    timeout_ms: int = 30000

class StructuredConnectorException(Exception):
    """Base for all connector exceptions."""
    pass

class StructuredConnector(ABC):
    """
    Abstract interface every structured source must implement.
    
    No Snowflake names here, no BigQuery-specific methods.
    Pure contract: what can you do with any database?
    """
    
    @abstractmethod
    async def connect(self) -> "StructuredConnection":
        """
        Establish a connection and prove it's read-only.
        
        Returns: StructuredConnection (proven safe to use)
        Raises: StructuredConnectorException on any failure
        """
        pass
    
    @abstractmethod
    async def get_schema_card(self, schema: str) -> Dict[str, Any]:
        """
        Fetch schema metadata: tables, columns, types, nullability.
        
        Returns: {
            "schema": str,
            "tables": [
                {
                    "name": str,
                    "columns": [{name, type, nullable, comment}, ...],
                    "row_count": int,
                    "sample_row": {...}
                },
                ...
            ]
        }
        """
        pass
    
    @abstractmethod
    async def execute_query(self, sql: str, params: List = None) -> List[Dict]:
        """Execute a read-only query (SELECT only)."""
        pass
    
    @abstractmethod
    async def close(self):
        """Close connection, release resources."""
        pass

class StructuredConnection:
    """
    A proven, safe connection to a structured source.
    Returned after write-probe passes.
    """
    
    def __init__(self, connector: StructuredConnector, connection_id: str):
        self.connector = connector
        self.connection_id = connection_id
        self.read_only_verified = True  # Proven by write-probe
        self.created_at = datetime.utcnow()
```

---

### Layer 2: Snowflake Concrete Implementation

**`connectors/snowflake/connector.py`** (200 lines)

```python
from connectors.base.connector import (
    StructuredConnector, StructuredConnection, 
    ConnectionConfig, StructuredConnectorException
)
import snowflake.connector
from snowflake.connector import DictCursor

class SnowflakeConnector(StructuredConnector):
    """
    Concrete implementation for Snowflake.
    
    Every method is Snowflake-specific, but the interface
    is generic — swappable with SnowflakeConnector → PostgresConnector
    without the caller knowing.
    """
    
    def __init__(self, config: ConnectionConfig):
        """
        Initialize with connection parameters.
        Does NOT connect yet — connect() does that.
        """
        self.config = config
        self._connection = None
        self._write_probe_passed = False
    
    async def connect(self) -> StructuredConnection:
        """
        Establish Snowflake connection + real write-probe.
        
        1. Parse credential_ref (e.g., env://CCE_SNOWFLAKE_PRIVATE_KEY)
        2. Load credential from secret backend
        3. Establish connection
        4. Run write-probe (attempt CREATE TEMPORARY TABLE)
        5. If probe FAILS (permission denied), return READY connection
        6. If probe SUCCEEDS (table created), DELETE it and REJECT
        """
        try:
            # Step 1-2: Resolve credential
            from common.tools.credential_loader import load_credential
            credential = await load_credential(self.config.credential_ref)
            
            # Step 3: Connect to Snowflake
            self._connection = snowflake.connector.connect(
                account=self.config.account_id,
                user=self.config.user,
                private_key_content=credential["private_key"],
                private_key_passphrase=credential.get("passphrase"),
                role=self.config.role,
                warehouse=self.config.warehouse,
                database=self.config.database,
                schema=self.config.schema,
                login_timeout=self.config.timeout_ms // 1000,
            )
            
            # Step 4-6: Write-probe
            await self._run_write_probe()
            
            if not self._write_probe_passed:
                raise StructuredConnectorException(
                    "Write-probe failed: role has write permissions"
                )
            
            # Connection proven read-only
            connection_id = f"conn_{self.config.account_id}_{int(time.time())}"
            return StructuredConnection(self, connection_id)
        
        except snowflake.connector.errors.ProgrammingError as e:
            raise StructuredConnectorException(f"Snowflake connection failed: {str(e)}")
    
    async def _run_write_probe(self):
        """
        Attempt to CREATE TEMPORARY TABLE.
        If denied (403/permission error) → read-only (PASS)
        If succeeds → has write access (FAIL, delete table)
        """
        cursor = self._connection.cursor(DictCursor)
        probe_table = "__cce_write_probe__"
        
        try:
            # Attempt write
            cursor.execute(f"CREATE TEMPORARY TABLE {probe_table} (x INT)")
            cursor.execute(f"DROP TABLE {probe_table}")
            # If we got here, write succeeded — this is BAD
            self._write_probe_passed = False
            raise StructuredConnectorException(
                "Write probe succeeded — role is NOT read-only"
            )
        except snowflake.connector.errors.ProgrammingError as e:
            if "permission denied" in str(e).lower() or "lack privilege" in str(e).lower():
                # Write was denied — this is GOOD (read-only proven)
                self._write_probe_passed = True
            else:
                # Some other error
                raise StructuredConnectorException(f"Write-probe error: {str(e)}")
        finally:
            cursor.close()
    
    async def get_schema_card(self, schema: str) -> Dict[str, Any]:
        """Fetch schema metadata."""
        if not self._connection:
            raise StructuredConnectorException("Not connected")
        
        cursor = self._connection.cursor(DictCursor)
        
        # Fetch tables + columns
        cursor.execute(f"""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
        """, (schema.upper(),))
        
        columns = cursor.fetchall()
        
        # Group by table
        tables_dict = {}
        for col in columns:
            table_name = col["TABLE_NAME"]
            if table_name not in tables_dict:
                tables_dict[table_name] = {
                    "name": table_name,
                    "columns": []
                }
            tables_dict[table_name]["columns"].append({
                "name": col["COLUMN_NAME"],
                "type": col["DATA_TYPE"],
                "nullable": col["IS_NULLABLE"] == "YES",
            })
        
        # Fetch row counts
        for table_name in tables_dict.keys():
            try:
                cursor.execute(f"SELECT COUNT(*) as cnt FROM {schema}.{table_name}")
                count = cursor.fetchone()
                tables_dict[table_name]["row_count"] = count["CNT"]
            except:
                tables_dict[table_name]["row_count"] = None
        
        # Fetch 1 sample row per table
        for table_name in tables_dict.keys():
            try:
                cursor.execute(f"SELECT * FROM {schema}.{table_name} LIMIT 1")
                sample = cursor.fetchone()
                tables_dict[table_name]["sample_row"] = dict(sample) if sample else None
            except:
                tables_dict[table_name]["sample_row"] = None
        
        cursor.close()
        
        return {
            "schema": schema,
            "tables": list(tables_dict.values())
        }
    
    async def execute_query(self, sql: str, params: List = None) -> List[Dict]:
        """Execute a SELECT query."""
        if not self._connection:
            raise StructuredConnectorException("Not connected")
        
        cursor = self._connection.cursor(DictCursor)
        try:
            cursor.execute(sql, params or [])
            return cursor.fetchall()
        finally:
            cursor.close()
    
    async def close(self):
        """Close connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
```

---

### Layer 3: Factory (How to instantiate the right connector)

**`connectors/factory.py`** (50 lines)

```python
from connectors.base.connector import StructuredConnector, ConnectionConfig
from connectors.snowflake.connector import SnowflakeConnector
# from connectors.postgres.connector import PostgresConnector  # Future
# from connectors.bigquery.connector import BigQueryConnector   # Future

class ConnectorFactory:
    """
    Factory pattern: given a config, return the right connector.
    
    Orchestrator never imports SnowflakeConnector.
    It just calls ConnectorFactory.create(config) and gets back
    a StructuredConnector (could be Snowflake, could be anything).
    """
    
    _connectors = {
        "snowflake": SnowflakeConnector,
        # "postgres": PostgresConnector,
        # "bigquery": BigQueryConnector,
    }
    
    @staticmethod
    def create(config: ConnectionConfig) -> StructuredConnector:
        """
        Create the right connector for this adapter.
        
        connector_class = ConnectorFactory.create(
            ConnectionConfig(
                adapter="snowflake",
                account_id="WGNPVQM-BI98485",
                user="SVC_...",
                credential_ref="env://...",
                database="SNOWFLAKE_PUBLIC_DATA_FREE",
                schema="PUBLIC_DATA_FREE",
            )
        )
        connection = await connector.connect()
        """
        connector_class = ConnectorFactory._connectors.get(config.adapter)
        if not connector_class:
            raise ValueError(
                f"Unsupported adapter: {config.adapter}. "
                f"Supported: {list(ConnectorFactory._connectors.keys())}"
            )
        return connector_class(config)
    
    @staticmethod
    def register(adapter: str, connector_class: type):
        """
        Register a new connector at runtime.
        Useful for testing or third-party adapters.
        """
        ConnectorFactory._connectors[adapter] = connector_class
```

---

### Layer 4: Integration with Ingestion Workflow

**`agents/ingestion_workflow.py`** (Modify `fetch_structured` node)

```python
async def fetch_structured(state: IngestionState) -> IngestionState:
    """
    Fetch schema card from any structured source.
    Adapter abstraction: same code for Snowflake, Postgres, BigQuery, etc.
    """
    try:
        from connectors.factory import ConnectorFactory
        from connectors.base.connector import ConnectionConfig
        
        config = ConnectionConfig(
            adapter=state["adapter"],  # "snowflake", "postgres", etc.
            account_id=os.environ.get("CCE_ACCOUNT_ID"),
            user=os.environ.get("CCE_USER"),
            credential_ref=os.environ.get("CCE_CREDENTIAL_REF"),
            database=os.environ.get("CCE_DATABASE"),
            schema=os.environ.get("CCE_SCHEMA"),
            role=os.environ.get("CCE_ROLE"),
            warehouse=os.environ.get("CCE_WAREHOUSE"),  # Snowflake-specific
        )
        
        # Factory pattern: returns SnowflakeConnector, PostgresConnector, etc.
        # Orchestrator doesn't know which
        connector = ConnectorFactory.create(config)
        
        # Connect (proves read-only via write-probe)
        connection = await connector.connect()
        
        # Fetch schema card (interface is same for all adapters)
        schema_card = await connector.get_schema_card(config.schema)
        
        state["parsed_doc"] = schema_card
        state["connection_handle"] = {
            "connector": connector,
            "connection": connection,
            "connection_id": connection.connection_id,
        }
        
        await connector.close()
    
    except Exception as e:
        state["errors"].append(f"fetch_structured: {str(e)}")
    
    return state
```

---

## Implementation Roadmap

### Phase 1 (Week 1): Snowflake Connector

**Files to create:**
- `connectors/base/connector.py` — Abstract interface
- `connectors/base/connection.py` — Connection interface
- `connectors/base/models.py` — Shared data models
- `connectors/base/exceptions.py` — Base exceptions
- `connectors/snowflake/connector.py` — Snowflake impl
- `connectors/snowflake/config.py` — Snowflake config
- `connectors/snowflake/errors.py` — Snowflake errors
- `connectors/factory.py` — Factory
- `connectors/registry.py` — Registry (for discovery)
- `tests/connectors/test_snowflake_connector.py` — Tests

**Total:** ~600 lines, fully agnostic

---

### Phase 2 (Week 2): Add Postgres Connector

**Add:**
- `connectors/postgres/connector.py` — Postgres impl
- `connectors/postgres/config.py`
- `connectors/postgres/errors.py`
- `tests/connectors/test_postgres_connector.py`

**No changes to:**
- Abstract base classes
- Ingestion workflow
- Orchestrator

Just copy the Snowflake pattern, adapt SQL syntax.

---

### Phase 3 (Week 3): Add BigQuery Connector

Same as Phase 2 — copy pattern, adapt to BigQuery's REST API.

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Async methods** | Connection pooling, concurrent ingestion later |
| **ConnectionConfig dataclass** | Single source of truth for params, type-safe |
| **Factory pattern** | Orchestrator depends on interface, not impl |
| **Write-probe in connect()** | Fail-fast: proves read-only before returning handle |
| **One schema_card method** | Same output shape for Snowflake, Postgres, BigQuery |
| **No adapter-specific fields in interface** | If it's Snowflake-only (warehouse, cluster), it's in SnowflakeConnector only |
| **Exceptions hierarchy** | Base exception, then adapter-specific subclasses |

---

## What Orchestrator Sees (Agnostic)

```python
# The orchestrator doesn't change when you add Postgres

async def fetch_structured(state):
    config = ConnectionConfig(
        adapter=state["adapter"],  # Could be "snowflake", "postgres", anything
        ...
    )
    connector = ConnectorFactory.create(config)  # Magic: returns right impl
    connection = await connector.connect()       # Always same interface
    schema = await connector.get_schema_card()   # Always same output shape
    return schema
```

Swapping Snowflake for Postgres:
- Change `state["adapter"]` from "snowflake" to "postgres"
- Change env vars (database name, etc.)
- **No code changes to orchestrator, factory, interface**

---

## Testing Strategy

**Unit tests** (no DB needed):
- Mock StructuredConnection
- Test factory instantiation
- Test error handling

**Integration tests** (with real Snowflake):
- `test_snowflake_integration.py`
- Connect, schema discovery, write-probe
- Run once per commit, flag failures

**Abstract base tests**:
- Every concrete impl must pass the same test suite
- Add `test_postgres_connector.py` later, it runs same tests against Postgres

---

## File Checklist (Phase 1)

```
✅ connectors/__init__.py
✅ connectors/base/__init__.py
✅ connectors/base/connector.py (abstract)
✅ connectors/base/connection.py (interface)
✅ connectors/base/models.py (dataclasses)
✅ connectors/base/exceptions.py (exception hierarchy)
✅ connectors/snowflake/__init__.py
✅ connectors/snowflake/connector.py (200 lines, Snowflake impl)
✅ connectors/snowflake/config.py (validation, defaults)
✅ connectors/snowflake/errors.py (Snowflake-specific errors)
✅ connectors/factory.py (instantiation)
✅ connectors/registry.py (discovery, optional for Phase 1)
✅ connectors/models.py (ConnectionConfig, if not in base/)
✅ tests/connectors/__init__.py
✅ tests/connectors/test_snowflake_connector.py (60 lines)
✅ tests/connectors/fixtures/mock_snowflake.py (test doubles)
```

**Total files: 16**  
**Total lines: ~600**  
**Fully agnostic, Snowflake-specific only in `snowflake/` folder**

---

## Why This Design Wins

| Aspect | What happens |
|--------|--------------|
| **Add new database (Phase 2+)** | 1 new folder, ~150 lines, register in factory, done |
| **Change Snowflake config** | Only touches `snowflake/config.py`, no orchestrator impact |
| **Test new database** | Copy test suite, run against new adapter, no changes needed |
| **Debug connectivity** | Trace logs show which connector was used (class name), not guessed |
| **Onboard new engineer** | "Read `connectors/base/connector.py` to understand the contract. Snowflake is in `connectors/snowflake/`" |
| **Swappable in production** | `config.adapter="postgres"` instead of `"snowflake"`, that's it |

---

Done. Start with Phase 1 (Snowflake), then Phase 2 (Postgres), then Phase 3 (BigQuery).
Each phase adds 1 folder, reuses the whole base architecture. Agnostic from day 1.
