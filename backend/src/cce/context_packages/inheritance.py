"""Global to domain to region to account override placeholder."""


def resolve_overrides(*layers):
    resolved = {}
    for layer in layers:
        resolved.update(layer or {})
    return resolved
