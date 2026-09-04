"""Glossary term model."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    definition: str
    synonyms: list[str] = field(default_factory=list)
