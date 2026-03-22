#!/usr/bin/env python3
"""
executor.py — Phase 2: Execution Engine
File Organizer & Deduper

Reads an action plan JSON and executes it safely:
- move: shutil.move with conflict detection
- delete: move to trash (never hard delete)
- skip: no-op

Safety guarantees:
- Dry-run mode: log everything, touch nothing
- Conflict detection: never overwrite existing dst
- Trash folder: deletes go to <output_dir>/trash/YYYY-MM-DD_HHMMSS/
- Undo log: written after every real execution
- Atomic-ish: stop on first error
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_plan(plan_path: str) -> list:
    with open(plan_path, "r") as f:
        plan = json.load(f)
    if not isinstance(plan, list):
        raise ValueError("Plan must be a JSON array")
    return plan


def validate_plan(plan: list) -> None:
    """Validate all paths are absolute and actions are known."""
    valid_actions = {"move", "delete", "skip"}
    errors = []

    for i, entry in enumerate(plan):
        action = entry.get("action")
        if action not in valid_actions:
            errors.append(f"[{i}] Unknown action: {action!r}")
            continue

        if action == "move":
            src = entry.get("src", "")
            dst = entry.get("dst", "")
            if not os.path.isabs(src):
                errors.append(f"[{i}] move.src is not absolute: {src!r}")
            if not os.path.isabs(dst):
                errors.append(f"[{i}] move.dst is not absolute: {dst!r}")
        elif action == "delete":
            path = entry.get("path", "")
            if not os.path.isabs(path):
                errors.append(f"[{i}] delete.path is not absolute: {path!r}")
        elif action == "skip":
            path = entry.get("path", "")
            if not os.path.isabs(path):
                errors.append(f"[{i}] skip.path is not absolute: {path!r}")

    if errors:
        raise ValueError("Plan validation failed:\n" + "\n".join(errors))


def make_trash_dir(output_dir: Path) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    trash = output_dir / "trash" / ts
    trash.mkdir(parents=True, exist_ok=True)
    return trash


def execute_plan(plan: list, output_dir: Path, dry_run: bool) -> list:
    """
    Execute the action plan. Returns list of action records for undo log.
    Stops on first error (atomic-ish).
    """
    trash_dir = None if dry_run else make_trash_dir(output_dir)
    records = []

    for entry in plan:
        action = entry["action"]

        if action == "move":
            src = entry["src"]
            dst = entry["dst"]

            # Conflict check
            if os.path.exists(dst):
                rec = {
                    "action": "move",
                    "src": src,
                    "dst": dst,
                    "status": "conflict",
                    "reason": "dst exists",
                }
                print(f"[CONFLICT] move {src!r} → {dst!r} (dst exists, skipped)")
                records.append(rec)
                continue

            if dry_run:
                print(f"[DRY-RUN] move {src!r} → {dst!r}")
                records.append({"action": "move", "src": src, "dst": dst, "status": "dry-run"})
            else:
                if not os.path.exists(src):
                    rec = {
                        "action": "move",
                        "src": src,
                        "dst": dst,
                        "status": "error",
                        "reason": "src not found",
                    }
                    records.append(rec)
                    print(f"[ERROR] move: src not found: {src!r}")
                    _write_undo_log(output_dir, records)
                    sys.exit(1)

                try:
                    Path(dst).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(src, dst)
                    print(f"[OK] move {src!r} → {dst!r}")
                    records.append({"action": "move", "src": src, "dst": dst, "status": "ok"})
                except Exception as e:
                    rec = {
                        "action": "move",
                        "src": src,
                        "dst": dst,
                        "status": "error",
                        "reason": str(e),
                    }
                    records.append(rec)
                    print(f"[ERROR] move failed: {e}")
                    _write_undo_log(output_dir, records)
                    sys.exit(1)

        elif action == "delete":
            path = entry["path"]
            filename = os.path.basename(path)

            if dry_run:
                print(f"[DRY-RUN] delete {path!r} → trash")
                records.append({"action": "delete", "src": path, "trash_path": "<dry-run>", "status": "dry-run"})
            else:
                if not os.path.exists(path):
                    rec = {
                        "action": "delete",
                        "src": path,
                        "trash_path": None,
                        "status": "error",
                        "reason": "src not found",
                    }
                    records.append(rec)
                    print(f"[ERROR] delete: src not found: {path!r}")
                    _write_undo_log(output_dir, records)
                    sys.exit(1)

                trash_path = str(trash_dir / filename)
                # Handle name collision in trash
                if os.path.exists(trash_path):
                    base, ext = os.path.splitext(filename)
                    trash_path = str(trash_dir / f"{base}_{datetime.now().strftime('%f')}{ext}")

                try:
                    shutil.move(path, trash_path)
                    print(f"[OK] delete {path!r} → {trash_path!r}")
                    records.append({"action": "delete", "src": path, "trash_path": trash_path, "status": "ok"})
                except Exception as e:
                    rec = {
                        "action": "delete",
                        "src": path,
                        "trash_path": trash_path,
                        "status": "error",
                        "reason": str(e),
                    }
                    records.append(rec)
                    print(f"[ERROR] delete failed: {e}")
                    _write_undo_log(output_dir, records)
                    sys.exit(1)

        elif action == "skip":
            path = entry["path"]
            print(f"[SKIP] {path!r}")
            records.append({"action": "skip", "path": path, "status": "skipped"})

    return records


def _write_undo_log(output_dir: Path, records: list) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    log_path = output_dir / f"undo_{ts}.json"
    payload = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "actions": records,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[LOG] Undo log written: {log_path}")
    return str(log_path)


def cmd_execute(args):
    plan_path = args.plan
    output_dir = Path(args.output_dir).resolve()
    dry_run = args.dry_run

    if not os.path.isfile(plan_path):
        print(f"[ERROR] Plan file not found: {plan_path!r}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Loading plan: {plan_path}")
    plan = load_plan(plan_path)
    print(f"[INFO] {len(plan)} action(s) found")

    print("[INFO] Validating plan...")
    validate_plan(plan)
    print("[INFO] Validation OK")

    if dry_run:
        print("[INFO] DRY-RUN mode — no files will be changed")

    records = execute_plan(plan, output_dir, dry_run)

    ok = sum(1 for r in records if r.get("status") == "ok")
    skipped = sum(1 for r in records if r.get("status") == "skipped")
    conflicts = sum(1 for r in records if r.get("status") == "conflict")
    dry = sum(1 for r in records if r.get("status") == "dry-run")

    if not dry_run:
        _write_undo_log(output_dir, records)

    print(
        f"\n[DONE] ok={ok} skipped={skipped} conflicts={conflicts}"
        + (f" dry-run={dry}" if dry_run else "")
    )


def main():
    parser = argparse.ArgumentParser(
        description="executor.py — Phase 2 execution engine for file-organizer"
    )
    sub = parser.add_subparsers(dest="command")

    exec_parser = sub.add_parser("execute", help="Execute an action plan")
    exec_parser.add_argument("--plan", required=True, help="Path to action plan JSON")
    exec_parser.add_argument("--output-dir", required=True, help="Output directory for trash + undo log")
    exec_parser.add_argument("--dry-run", action="store_true", help="Simulate execution, touch nothing")

    args = parser.parse_args()

    if args.command == "execute":
        cmd_execute(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
