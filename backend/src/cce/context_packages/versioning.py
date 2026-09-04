"""Immutable package version helpers."""


def next_patch_version(version: str) -> str:
    major, minor, patch = (int(part) for part in version.split("."))
    return "%d.%d.%d" % (major, minor, patch + 1)
