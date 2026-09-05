# ADR-004: Thin JSON Adapter

CCE may expose a thin JSON/HTTP adapter over the same `Application` services
used by gRPC and MCP.

It is not a second reasoning engine, not a REST redesign, and not a parallel
domain implementation.

Each endpoint maps one request into an existing application service call and
maps one service response back to JSON.
