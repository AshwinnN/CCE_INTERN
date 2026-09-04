#!/usr/bin/env python3
"""Dynamic loader for skill scripts.

Skill folders (skill-source-registry, skill-strucutred_source_connect, ...)
are not importable Python packages -- hyphens and mixed underscore/hyphen
naming make a normal `import` impossible, and every skill script is designed
to be run standalone. This loader is pure plumbing: it loads a skill's real
script file and returns the named function from it, unmodified. It contains
no business logic of its own.
"""
import importlib.util
import os

SKILLS_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "skills")
)

_CACHE = {}


def load_skill_function(skill_dir_name, script_name, func_name):
    """skill_dir_name: e.g. 'skill-source-registry'
    script_name: e.g. 'validate_registry_entry.py'
    func_name: e.g. 'validate'
    """
    cache_key = (skill_dir_name, script_name, func_name)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    path = os.path.join(SKILLS_ROOT, skill_dir_name, "scripts", script_name)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            "skill script not found: %s (looked under %s)" % (path, SKILLS_ROOT)
        )
    spec = importlib.util.spec_from_file_location(
        "%s.%s" % (skill_dir_name, script_name), path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    func = getattr(module, func_name)
    _CACHE[cache_key] = func
    return func


def load_skill_module(skill_dir_name, script_name):
    """Returns the whole module, for skills whose script exposes more than
    one useful attribute (e.g. metadata_store.py's do_store/do_retrieve, or
    validate_source_profile.py's DEFAULT_REGISTRY)."""
    path = os.path.join(SKILLS_ROOT, skill_dir_name, "scripts", script_name)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            "skill script not found: %s (looked under %s)" % (path, SKILLS_ROOT)
        )
    spec = importlib.util.spec_from_file_location(
        "%s.%s" % (skill_dir_name, script_name), path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
