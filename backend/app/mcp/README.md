# MCP Integration Boundary

CCE is intended to be served to other agents through MCP. The MVP route
registry exposes `/api/v1/mcp/manifest` as a REST-side placeholder only.

The actual MCP server/transport is intentionally not implemented in this
packaging step so current CCE behavior is unchanged.
