import json
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

SNAPSHOT_DIR = Path(__file__).parent.parent / "data" / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

def create_snapshot(manifest: dict, plan: dict, rules: list, profile_id: str = None) -> str:
    """Create a pre-run snapshot. Returns snapshot_id."""
    snapshot_id = hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:12]

    # Normalize rules: handle both Rule objects and plain dicts (e.g. from JSON API)
    normalized_rules = []
    for r in rules:
        if isinstance(r, dict):
            normalized_rules.append({
                "id": r.get("id"),
                "name": r.get("name"),
                "action": r.get("action"),
            })
        else:
            # Assume Rule-like object with .id, .name, .action attributes
            normalized_rules.append({
                "id": getattr(r, "id", None),
                "name": getattr(r, "name", None),
                "action": getattr(r, "action", None),
            })

    snap = {
        "id": snapshot_id,
        "created_at": datetime.now().isoformat(),
        "profile": profile_id,
        "file_count": len(manifest.get("files", [])),
        "rules": normalized_rules,
        "plan_actions": len(plan.get("actions", [])),
        "scanned_paths": manifest.get("scanned_paths", []),
    }
    path = SNAPSHOT_DIR / f"{snapshot_id}.json"
    with open(path, "w") as f:
        json.dump(snap, f, indent=2)

    # Also save the plan so verify_plan can load it later
    if plan:
        plan_path = SNAPSHOT_DIR / f"{snapshot_id}_plan.json"
        with open(plan_path, "w") as f:
            json.dump(plan, f)

    return snapshot_id

def get_snapshot(snapshot_id: str) -> dict:
    path = SNAPSHOT_DIR / f"{snapshot_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)

def verify_plan(snapshot_id: str, after_manifest: dict, plan: Optional[dict] = None) -> dict:
    """
    Verify a plan against actual filesystem state post-execution.

    Compares planned actions (move/delete/skip) against the actual
    state of files recorded in after_manifest (a post-execution scan).
    """
    snap = get_snapshot(snapshot_id)
    if not snap:
        return {"error": "Snapshot not found"}

    # Load the plan if not provided (look it up from snapshot if stored)
    if plan is None:
        plan_path = SNAPSHOT_DIR / f"{snapshot_id}_plan.json"
        if plan_path.exists():
            with open(plan_path) as f:
                plan = json.load(f)
        else:
            plan = {}

    actions = plan.get("actions", []) if isinstance(plan, dict) else (plan or [])

    # Build a set of paths from the after-manifest for fast lookup
    after_paths: dict[str, dict] = {}
    for f in after_manifest.get("files", []):
        p = f.get("path")
        if p:
            after_paths[p] = f

    moved_ok = 0
    deleted_ok = 0
    unchanged_ok = 0
    blocked_ok = 0
    unexpected: list[dict] = []

    # ARCH-001: planner uses action_type; snapshot may have old "action" key (backward compat)
    for action in actions:
        act = action.get("action_type") or action.get("action", "")
        status = action.get("status", "")
        src = action.get("src") or action.get("path", "")
        dst = action.get("dst", "")

        # Files that should remain unchanged (skip, or any status indicating blocked/no-action)
        unchanged_statuses = {"skipped", "skipped_no_rule", "blocked", "protected",
                             "unknown_review", "conflict_review"}
        if act == "skip" or status in unchanged_statuses:
            if src in after_paths:
                unchanged_ok += 1
                if status == "blocked":
                    blocked_ok += 1
            else:
                unexpected.append({
                    "type": "should_exist",
                    "path": src,
                    "expected": "unchanged",
                    "found": "absent",
                    "action": act,
                    "status": status,
                })
        elif act == "move":
            src_gone = src not in after_paths
            dst_exists = dst in after_paths
            if src_gone and dst_exists:
                moved_ok += 1
            elif src_gone and not dst_exists:
                unexpected.append({
                    "type": "move_incomplete",
                    "src": src,
                    "dst": dst,
                    "expected": "file at dst",
                    "found": "absent",
                })
            elif not src_gone:
                unexpected.append({
                    "type": "move_not_executed",
                    "src": src,
                    "dst": dst,
                    "expected": "src removed",
                    "found": "src still present",
                })
        elif act == "delete":
            if src not in after_paths:
                deleted_ok += 1
            else:
                unexpected.append({
                    "type": "delete_not_executed",
                    "path": src,
                    "expected": "absent",
                    "found": "present",
                })

    return {
        "snapshot_id": snapshot_id,
        "planned_actions": len(actions),
        "scanned_paths": snap.get("scanned_paths", []),
        "planned_files": snap.get("file_count", 0),
        "moved_as_expected": moved_ok,
        "deleted_as_expected": deleted_ok,
        "unchanged_as_expected": unchanged_ok,
        "blocked_as_expected": blocked_ok,
        "unexpected_changes": unexpected,
    }
