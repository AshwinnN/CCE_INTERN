"""Short-lived transactions; never share a psycopg connection across graph workers."""

import json
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from pydantic import BaseModel


def json_value(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def json_param(value):
    return Json(json_value(value), dumps=lambda x: json.dumps(x, default=str))


class LifecycleDB:
    def __init__(self, dsn: str):
        self.dsn = dsn

    @contextmanager
    def transaction(self):
        conn = psycopg2.connect(self.dsn)
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    yield cur
        finally:
            conn.close()
