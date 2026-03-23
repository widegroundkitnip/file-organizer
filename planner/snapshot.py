import json
import hashlib
import os
from datetime import datetime
from pathlib import Path

SNAPSHOT_DIR = Path("data/snapshots")
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

def create_snapshot(manifest: dict, plan: dict, rules: list, profile_id: str = None) -> str:
    """Create a pre-run snapshot. Returns snapshot_id."""
    snapshot_id = hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:12]
    snap = {
        "id": snapshot_id,
        "created_at": datetime.now().isoformat(),
        "profile": profile_id,
        "file_count": len(manifest.get("files", [])),
        "rules": [{"id": r.id, "name": r.name, "action": r.action} for r in rules],
        "plan_actions": len(plan.get("actions", [])),
        "scanned_paths": manifest.get("scanned_paths", []),
    }
    path = SNAPSHOT_DIR / f"{snapshot_id}.json"
    with open(path, "w") as f:
        json.dump(snap, f, indent=2)
    return snapshot_id

def get_snapshot(snapshot_id: str) -> dict:
    path = SNAPSHOT_DIR / f"{snapshot_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)

def verify_plan(snapshot_id: str, after_manifest: dict) -> dict:
    snap = get_snapshot(snapshot_id)
    if not snap:
        return {"error": "Snapshot not found"}

    result = {
        "snapshot_id": snapshot_id,
        "planned_actions": snap["plan_actions"],
        "scanned_paths": snap["scanned_paths"],
        "planned_files": snap["file_count"],
        "moved_as_expected": 0,
        "deleted_as_expected": 0,
        "unchanged_as_expected": 0,
        "blocked_as_expected": 0,
        "unexpected_changes": [],
    }
    return result
