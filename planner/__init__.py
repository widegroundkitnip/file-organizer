"""Planner — rule engine, boundary checks, template expansion."""
import json as _json
from pathlib import Path as _Path

from .rules import RuleManager, Rule, FilterCondition
from .engine import plan_from_manifest, check_boundary_conflicts, check_unknown_files
from .templates import apply_template, format_size


def load_manifest(path: str) -> dict:
    """Load and return manifest JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return _json.load(f)


__all__ = [
    "RuleManager", "Rule", "FilterCondition",
    "plan_from_manifest", "check_boundary_conflicts", "check_unknown_files",
    "apply_template", "format_size", "load_manifest",
]
