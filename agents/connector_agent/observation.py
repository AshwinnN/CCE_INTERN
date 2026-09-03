#!/usr/bin/env python3
"""Source-agnostic change-observation abstraction.

The Agent owns this lifecycle. Provider-specific behavior lives behind
deterministic connector/lister implementations, never here -- this module
contains no vendor names and no vendor-specific API calls.
"""
from abc import ABC, abstractmethod


class ChangeObserver(ABC):
    @abstractmethod
    def start(self, connection_handle: dict, checkpoint: str = None) -> dict:
        """Begin observation. Returns {"observation_handle": ..., "checkpoint": ...}."""

    @abstractmethod
    def poll(self, connection_handle: dict, checkpoint: str) -> dict:
        """Poll once. Returns {"events": [SourceChangeEvent-shaped dicts], "checkpoint": ...}."""

    @abstractmethod
    def stop(self, observation_handle: str) -> None:
        """Stop observation for providers with webhook/subscription state."""
