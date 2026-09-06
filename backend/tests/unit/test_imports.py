import importlib


def test_server_import_chain_loads():
    for module_name in [
        "cce.bootstrap",
        "cce.rpc.server",
        "cce.http.app",
        "cce.main",
    ]:
        importlib.import_module(module_name)
