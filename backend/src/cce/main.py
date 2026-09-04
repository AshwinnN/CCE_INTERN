"""CCE backend entry point."""

from cce.bootstrap import build_application
from cce.config.settings import load_settings
from cce.rpc.server import serve


def main() -> None:
    settings = load_settings()
    app = build_application(settings)
    serve(app)


if __name__ == "__main__":
    main()
