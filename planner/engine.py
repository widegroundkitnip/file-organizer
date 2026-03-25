import os
import uuid
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from .rules import Rule, RuleManager
from .templates import apply_template


# ---------------------------------------------------------------------------
# Planner Output Types — ARCH-003 / EXEC-001 / EXEC-002
#
# Three-layer model:
#   Signals  — what the scanner detects (project roots, protected paths, conflicts)
#   Rules    — user-defined filters and templates
#   Actions  — concrete operations (move | copy | delete | skip | merge)
#
# Preview shows statuses: protected | blocked | unknown_review | conflict_review
# Executor receives ONLY:     move | copy | delete | skip | merge
# ---------------------------------------------------------------------------

# Planner action types — the ONLY values that reach the executor (ARCH-001/003)
PLANNER_ACTION_TYPES = frozenset({"move", "copy", "delete", "skip", "merge"})

# Planner status values — cover all planner-level outcomes including
# review statuses that never reach the executor
PLANNER_STATUS_TYPES = frozenset({
    "pending",        # not yet acted on
    "ok",            # successfully executed
    "conflict",      # destination conflict detected
    "error",         # execution error
    "skipped",       # intentionally skipped
    "skipped_no_rule",  # no rule matched → skip
    "blocked",       # blocked by planner (boundary / project_safe_mode / signal)
    "protected",     # signal: file is protected by scanner signal
    "unknown_review",  # signal: file is unknown/system → needs human review
    "conflict_review", # signal: conflict needs human review
})


@dataclass
class PlannedAction:
    """
    ARCH-003 / EXEC-001: Planner's output — intent to act.

    This is what the planner produces; the executor receives a normalised
    subset (move/copy/delete/skip/merge only).

    Fields:
      action_type  — concrete operation: move | copy | delete | skip | merge
                    NOTE: "protected", "blocked", "unknown_review",
                    "conflict_review" are STATUS values, NOT action types.
      src / dst   — source path, destination path
      plan_id     — groups actions from the same planning run
      Signals are recorded in: protected (bool), protection_reason (str),
                              conflict_review (bool), conflict_reason (str)
      error_type  — EXEC-002: permissions | missing_source | checksum_mismatch |
                           disk_full | boundary_violation | project_safe_violation
      error_message / warning_message — EXEC-002: human-readable detail
    """
    # Intent
    action_type: str = "skip"   # move | copy | delete | skip | merge
    src: str = ""
    dst: str = ""
    plan_id: str = ""

    # Rule attribution
    rule_matched: str = ""
    rule_id: str = ""
    rule_name: str = ""
    rule_match_reason: str = ""

    # Planner-level signals (ARCH-003: signals layer)
    protected: bool = False
    protection_reason: str = ""
    conflict_review: bool = False
    conflict_reason: str = ""

    # Conflict handling
    conflict_mode: str = "rename"  # rename | skip | overwrite

    # Result status (set by planner or executor)
    # Values: pending | ok | conflict | error | skipped | skipped_no_rule |
    #         blocked | protected | unknown_review | conflict_review
    status: str = "pending"

    # EXEC-002: explicit error fields
    error_type: str = ""      # permissions | missing_source | checksum_mismatch |
                             # disk_full | boundary_violation | project_safe_violation
    error_message: str = ""
    warning_message: str = ""

    # Classification
    classification: str = "known"  # known | unknown | system

    # CORE-002: MD5 checksum fields
    verify_checksum: bool = False
    src_md5: str = ""
    dst_md5: str = ""
    checksum_status: str = ""   # "" | "verified" | "mismatch" | "skipped" | "error"

    def to_dict(self) -> dict:
        return asdict(self)


# Backward-compatibility alias — existing code uses `Action`
Action = PlannedAction


@dataclass
class ExecutionResult:
    """
    EXEC-001: Executor output — actual outcome of executing a PlannedAction.

    Split from intent so the planner's view of the world (signals + rules)
    is never polluted by executor implementation details.
    """
    # Which planned action this result corresponds to
    src: str = ""
    plan_id: str = ""

    # What was done
    action_type: str = ""    # move | copy | delete | skip (matches PlannedAction.action_type)
    actual_dst: str = ""     # actual destination after resolution (may differ from PlannedAction.dst)
    actual_src: str = ""     # actual source after resolution (may differ from PlannedAction.src)

    # Outcome
    # Values: ok | conflict | error | skipped | dry_run | preflight_error
    status: str = ""

    # EXEC-002: explicit error fields
    error_type: str = ""      # permissions | missing_source | checksum_mismatch |
                             # disk_full | cross_device | undo_failed
    error_message: str = ""
    warning_message: str = ""

    # MD5 result
    src_md5: str = ""
    dst_md5: str = ""
    checksum_status: str = ""

    # Cross-device flag
    cross_device_move: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def check_boundary_conflicts(actions: List[PlannedAction], parent_folders: List[str]) -> List[PlannedAction]:
    """ARCH-001/ARCH-002: Mark boundary-crossing moves as 'blocked'.
    'blocked' is a PLANNING outcome (status), NOT an executor verb.
    Executor never sees blocked moves — they are filtered before execution."""
    for pf in parent_folders:
        pf_norm = os.path.normpath(pf)
        pf_prefix = pf_norm + os.sep
        for action in actions:
            if action.action_type != "move":
                continue
            src_norm = os.path.normpath(action.src)
            dst_norm = os.path.normpath(action.dst)
            src_inside = src_norm == pf_norm or src_norm.startswith(pf_prefix)
            dst_outside = dst_norm != pf_norm and not dst_norm.startswith(pf_prefix)

            if src_inside and dst_outside:
                action.status = "blocked"
                action.error_type = "boundary_violation"
                action.error_message = f"Crosses parent boundary: {pf}"
    return actions


def check_unknown_files(manifest_files: List[dict], actions: List[PlannedAction]) -> List[PlannedAction]:
    """Ensure unknown/system files are never auto-actioned. Route to 'unknown_review' status."""
    unknown_paths = {f["path"] for f in manifest_files if f.get("classification") in ("unknown", "system")}
    for action in actions:
        if action.src in unknown_paths:
            # ARCH-001: unknown_review is a STATUS, not an action type.
            # The action type stays what it was (move/skip/etc.) but status overrides.
            action.status = "unknown_review"
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
    default_category: str = "Other",
    project_roots: Optional[List[dict]] = None,
    scope_mode: str = "preserve_parent_boundaries"
) -> dict:
    """
    ARCH-003: Generate action plan from manifest + rules using the Signals/Rules/Actions model.

    Signals  — what the scanner detects: project roots, protected paths, conflicts
    Rules     — user-defined filters and templates
    Actions   — concrete operations: move | copy | delete | skip | merge

    Preview shows statuses: protected | blocked | unknown_review | conflict_review
    Executor receives ONLY:   move | copy | delete | skip | merge

    Key rules enforced:
    1. Unknown/system files → status=unknown_review (never auto-moved/deleted)
    2. Parent folder boundaries → status=blocked (executor never sees these)
    3. Protected files (signals) → status=protected (executor never sees these)
    4. First matching rule wins
    5. Unmatched known files → action=skip
    """
    files = manifest.get("files", [])
    parent_folders = parent_folders or []
    actions: List[PlannedAction] = []
    plan_id = str(uuid.uuid4())

    matched_paths = set()

    for file in files:
        classification = file.get("classification", "known")
        path = file.get("path", "")

        # RULE 1: Unknown/system files — route to unknown_review status (ARCH-001)
        if classification in ("unknown", "system"):
            actions.append(PlannedAction(
                action_type="skip",
                src=path,
                plan_id=plan_id,
                rule_matched="[auto: unknown file]",
                status="unknown_review",
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

            rule_match_reason = _build_match_reason(rule.filter, file)

            if rule.destinations:
                dests = rule.destinations
            elif rule.destination_template:
                dests = [rule.destination_template]
            else:
                dests = []

            # Fan-out: one PlannedAction per destination
            for dest_tpl in dests:
                dst = apply_template(dest_tpl, file, default_category)
                if not dst.startswith("/"):
                    dst = os.path.join(default_output_dir, dst)

                # CORE-002: MD5 verification for move actions
                verify_md5 = (rule.action == "move")

                actions.append(PlannedAction(
                    action_type=rule.action,
                    src=path,
                    dst=dst,
                    plan_id=plan_id,
                    rule_matched=rule.name,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    rule_match_reason=rule_match_reason,
                    status="pending",
                    conflict_mode=rule.conflict_mode,
                    classification="known",
                    verify_checksum=verify_md5,
                ))

            # Record action even when no destinations (skip/delete rules)
            if not dests:
                actions.append(PlannedAction(
                    action_type=rule.action,
                    src=path,
                    dst="",
                    plan_id=plan_id,
                    rule_matched=rule.name,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    rule_match_reason=rule_match_reason,
                    status="pending",
                    conflict_mode=rule.conflict_mode,
                    classification="known",
                    verify_checksum=False,
                ))

            matched_paths.add(path)
            action_taken = True
            break

        # No rule matched → skip
        if not action_taken:
            actions.append(PlannedAction(
                action_type="skip",
                src=path,
                plan_id=plan_id,
                rule_matched="[none]",
                status="skipped_no_rule",
                classification="known",
            ))
            matched_paths.add(path)

    # RULE 2: Boundary checks → status=blocked (ARCH-001/002)
    actions = check_boundary_conflicts(actions, parent_folders)

    # RULE 2b: Project-safe scope enforcement
    if scope_mode == "project_safe_mode" and project_roots:
        for action in actions:
            if action.action_type != "move" or not action.src:
                continue
            src_norm = os.path.normpath(action.src)
            dst_norm = os.path.normpath(action.dst)
            for proj in project_roots:
                proj_path = os.path.normpath(proj["path"])
                proj_prefix = proj_path + os.sep
                if (src_norm == proj_path or src_norm.startswith(proj_prefix)) and \
                   (dst_norm != proj_path and not dst_norm.startswith(proj_prefix)):
                    # ARCH-002: "blocked" is a PLANNING outcome, NOT an executor verb
                    action.status = "blocked"
                    action.error_type = "project_safe_violation"
                    action.error_message = "project_safe_mode: would move file out of detected project"
                    break

    # RULE 3: Unknown file enforcement (double-check)
    actions = check_unknown_files(files, actions)

    # Stats — ARCH-001: executor-only actions vs planner statuses
    stats = {
        "total": len(actions),
        # Executor actions (what the executor will receive)
        "moves": sum(1 for a in actions if a.action_type == "move"),
        "deletes": sum(1 for a in actions if a.action_type == "delete"),
        "skips": sum(1 for a in actions if a.action_type == "skip"),
        "copies": sum(1 for a in actions if a.action_type == "copy"),
        "merges": sum(1 for a in actions if a.action_type == "merge"),
        # Planner statuses (what the preview shows as badges)
        "unknown_review": sum(1 for a in actions if a.status == "unknown_review"),
        "protected": sum(1 for a in actions if a.status == "protected"),
        "blocked": sum(1 for a in actions if a.status == "blocked"),
        "conflict_review": sum(1 for a in actions if a.status == "conflict_review"),
        "conflicts": sum(1 for a in actions if a.status == "conflict"),
    }

    return {
        "actions": [a.to_dict() for a in actions],
        "stats": stats,
        "plan_id": plan_id,
    }
