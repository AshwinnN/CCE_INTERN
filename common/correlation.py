#!/usr/bin/env python3
"""Trace/correlation ID generation. Orchestration-only utility -- no Skill
generates its own trace ID (every skill in this repo echoes what it's given,
per e.g. skill-strucutred_source_connect's downstream consumers); this is
the one place a fresh trace ID may be minted, at the start of an Agent run.
"""
import uuid


def new_trace_id():
    return "trc_%s" % uuid.uuid4().hex[:16]


def new_event_id():
    return str(uuid.uuid4())
