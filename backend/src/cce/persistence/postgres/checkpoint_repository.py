"""PostgreSQL checkpoint repository placeholder for cce_control.registry."""

from cce.core.errors import NotImplementedCCEError


class PostgresCheckpointRepository:
    def save_checkpoint(self, *args, **kwargs):
        raise NotImplementedCCEError("checkpoint persistence is not implemented yet")
