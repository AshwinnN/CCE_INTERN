"""CCE backend entry point."""

from threading import Thread

from cce.bootstrap import build_application
from cce.config.settings import load_settings
from cce.rpc.server import serve


def _serve_http(app) -> None:
    import uvicorn

    from cce.http.app import create_app

    uvicorn.run(
        create_app(app),
        host="0.0.0.0",
        port=app.settings.http_port,
        log_level="info",
    )


def main() -> None:
    settings = load_settings()
    app = build_application(settings)
    if settings.http_enabled:
        Thread(target=_serve_http, args=(app,), daemon=True).start()
    serve(app)


if __name__ == "__main__":
    main()
