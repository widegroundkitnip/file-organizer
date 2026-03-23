import os
import uuid
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from .rules import Rule, RuleManager
from .templates import apply_template


@dataclass
class Action:
    action: str  # move | delete | skip | unknown_review
    src: str = ""
    dst: str = ""
    rule_matched: str = ""      # human-readable rule name (e.g. "Screenshots")
    rule_id: str = ""            # rule UUID
    rule_name: str = ""          # alias for rule_matched (frontend uses this)
    rule_match_reason: str = ""  # e.g. "name_contains: 'Screenshot'"
    status: str = "pending"      # pending | ok | conflict | error | blocked_boundary | blocked_unknown
    conflict_mode: str = "rename"
    error_reason: str = ""
    classification: str = "known"  # known | unknown | system

    def to_dict(self) -> dict:
        return asdict(self)


def check_boundary_conflicts(actions: List[Action], parent_folders: List[str]) -> List[Action]:
    """Check all actions against parent folder boundaries. Block cross-boundary moves/deletes."""
    for pf in parent_folders:
        pf_norm = os.path.normpath(pf)
        for action in actions:
            if action.action not in ("move", "delete"):
                continue
            target = action.dst if action.action == "move" else action.src
            target_norm = os.path.normpath(target)
            # Is target inside a parent boundary?
            is_inside = target_norm.startswith(pf_norm + os.sep) or target_norm == pf_norm
            # Is source inside a parent boundary?
            src_norm = os.path.normpath(action.src)
            src_inside = src_norm.startswith(pf_norm + os.sep) or src_norm == pf_norm

            if is_inside or src_inside:
                action.status = "blocked_boundary"
                action.error_reason = f"Crosses parent boundary: {pf}"
    return actions


def check_unknown_files(manifest_files: List[dict], actions: List[Action]) -> List[Action]:
    """Ensure unknown/system files are never auto-actioned. Add to unknown_review."""
    unknown_paths = {f["path"] for f in manifest_files if f.get("classification") in ("unknown", "system")}
    for action in actions:
        if action.src in unknown_paths:
            action.action = "unknown_review"
            action.status = "pending"
            action.classification = "unknown"
    return actions


def _build_match_reason(filter_cond, file: dict) -> str:
    """Build a human-readable string describing why a filter matched."""
    if not filter_cond:
        return "no filter"
    t = filter_cond.type
    if t == "extension":
        vals = filter_cond.values or []
        return f"extension: .{', .'.join(v.lstrip('.') for v in vals)}"
    elif t == "name_contains":
        vals = filter_cond.values or []
        return f"name contains: {vals!r}"
    elif t == "name_pattern":
        vals = filter_cond.values or []
        return f"name pattern: {vals[0] if vals else ''}"
    elif t == "path_contains":
        vals = filter_cond.values or []
        return f"path contains: {vals!r}"
    elif t == "size_gt":
        return f"size > {filter_cond.value} bytes"
    elif t == "size_lt":
        return f"size < {filter_cond.value} bytes"
    elif t == "modified_after":
        return f"modified after {filter_cond.value}"
    elif t == "modified_before":
        return f"modified before {filter_cond.value}"
    elif t == "created_after":
        return f"created after {filter_cond.value}"
    elif t == "created_before":
        return f"created before {filter_cond.value}"
    elif t == "modified_within_days":
        return f"modified within {filter_cond.value} days"
    elif t == "all_of":
        parts = [_build_match_reason(c, file) for c in (filter_cond.values or [])]
        return f"all_of({', '.join(parts)})"
    elif t == "any_of":
        parts = [_build_match_reason(c, file) for c in (filter_cond.values or [])]
        return f"any_of({', '.join(parts)})"
    elif t == "none_of":
        parts = [_build_match_reason(c, file) for c in (filter_cond.values or [])]
        return f"none_of({', '.join(parts)})"
    elif t == "duplicate":
        return "is duplicate"
    elif t == "no_extension":
        return "no extension"
    elif t == "default":
        return "default rule"
    return f"filter:{t}"


def plan_from_manifest(
    manifest: dict,
    rules: List[Rule],
    default_output_dir: str,
    parent_folders: Optional[List[str]] = None,
    default_category: str = "Other"
) -> dict:
    """
    Generate action plan from manifest + rules.

    Key rules enforced:
    1. Unknown/system files → unknown_review (never auto-moved/deleted)
    2. Parent folder boundaries → blocked_boundary
    3. First matching rule wins
    4. Unmatched known files → skip
    """
    files = manifest.get("files", [])
    parent_folders = parent_folders or []
    actions: List[Action] = []

    matched_paths = set()

    for file in files:
        classification = file.get("classification", "known")
        path = file.get("path", "")

        # RULE 1: Unknown/system files — force to unknown_review, skip rule matching
        if classification in ("unknown", "system"):
            actions.append(Action(
                action="unknown_review",
                src=path,
                rule_matched="[auto: unknown file]",
                status="pending",
                classification=classification,
            ))
            matched_paths.add(path)
            continue

        # Normal rule matching — first win
        action_taken = False
        for rule in rules:
            if not rule.enabled:
                continue
            if rule.filter and not rule.filter.matches(file):
                continue

            # Rule matched — build a human-readable match reason
            rule_match_reason = _build_match_reason(rule.filter, file)

            dst = apply_template(rule.destination_template, file, default_category)
            if not dst.startswith("/"):
                dst = os.path.join(default_output_dir, dst)

            actions.append(Action(
                action="move",
                src=path,
                dst=dst,
                rule_matched=rule.name,
                rule_id=rule.id,
                rule_name=rule.name,
                rule_match_reason=rule_match_reason,
                status="pending",
                conflict_mode=rule.conflict_mode,
                classification="known",
            ))
            matched_paths.add(path)
            action_taken = True
            break

        # No rule matched → skip
        if not action_taken:
            actions.append(Action(
                action="skip",
                src=path,
                rule_matched="[none]",
                status="skipped_no_rule",
                classification="known",
            ))
            matched_paths.add(path)

    # RULE 2: Boundary checks
    actions = check_boundary_conflicts(actions, parent_folders)

    # RULE 3: Unknown file enforcement (double-check, already applied above)
    actions = check_unknown_files(files, actions)

    # Count actions
    stats = {
        "total": len(actions),
        "moves": sum(1 for a in actions if a.action == "move"),
        "deletes": sum(1 for a in actions if a.action == "delete"),
        "skips": sum(1 for a in actions if a.action == "skip"),
        "unknown_review": sum(1 for a in actions if a.action == "unknown_review"),
        "blocked_boundary": sum(1 for a in actions if a.status == "blocked_boundary"),
        "conflicts": sum(1 for a in actions if a.status == "conflict"),
    }

    return {
        "actions": [a.to_dict() for a in actions],
        "stats": stats,
        "plan_id": str(uuid.uuid4()),
    }
