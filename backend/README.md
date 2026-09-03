# CCE Backend

`app/` is the complete CCE server-side implementation. It contains the
existing working CCE code plus the REST/MCP/agent integration boundaries.

Start the REST server from this directory:

```powershell
cd app
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```
