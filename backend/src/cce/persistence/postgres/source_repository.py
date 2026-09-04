"""PostgreSQL source repository placeholder for cce_control.registry."""

from cce.core.errors import NotImplementedCCEError


class PostgresSourceRepository:
    def save_source(self, *args, **kwargs):
        raise NotImplementedCCEError("source persistence is not implemented yet")
