#!/usr/bin/env python3
"""
executor.py — Phase 2: Execution Engine
File Organizer & Deduper

Phase 2.1 improvements:
- Auto-rename on conflict (--on-conflict skip|rename|overwrite)
- Transaction-style undo log (PENDING written at start, updated per action)
- Cross-device move detection (copy+trash fallback)
- Pre-flight permission validation (abort before touching anything)

Reads an action plan JSON and executes it safely:
- move: shutil.move with conflict detection
- delete: move to trash (never hard delete)
- skip: no-op

Safety guarantees:
- Dry-run mode: log everything, touch nothing
- Conflict handling: skip (default) | rename | overwrite
  - OVERWRITE WARNING: 'overwrite' permanently replaces the destination file.
    Use only when you are absolutely certain the destination is expendable.
- Trash folder: deletes go to <output_dir>/trash/YYYY-MM-DD_HHMMSS/
- Transaction undo log: PENDING written before any action; updated in-place as
  each action completes — survives crashes/interrupts
- Cross-device move: detected via st_dev; uses copy2 + trash fallback
- Pre-flight checks: reads src, writes to dst parent — abort if any fail
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Plan loading / validation
# ---------------------------------------------------------------------------

def load_plan(plan_path: str) -> list:
    with open(plan_path, "r") as f:
        plan = json.load(f)
    if not isinstance(plan, list):
        raise ValueError("Plan must be a JSON array")
    return plan


def validate_plan(plan: list) -> None:
    """Validate all paths are absolute and actions are known.
    Note: unknown_review is handled as a no-op by the executor and does not reach here."""
    valid_actions = {"move", "delete", "skip"}
    errors = []

    for i, entry in enumerate(plan):
        action = entry.get("action")
        if action not in valid_actions:
            # unknown_review was already filtered upstream but handle gracefully
            if action == "unknown_review":
                continue
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


# ---------------------------------------------------------------------------
# Conflict rename helper
# ---------------------------------------------------------------------------

def resolve_rename(dst: str) -> str:
    """
    Append _1, _2, _3... to filename stem (before extension) until no conflict.
    e.g. /tmp/foo.jpg → /tmp/foo_1.jpg → /tmp/foo_2.jpg ...
    """
    p = Path(dst)
    stem = p.stem
    suffix = p.suffix
    parent = p.parent
    counter = 1
    candidate = dst
    while os.path.exists(candidate):
        candidate = str(parent / f"{stem}_{counter}{suffix}")
        counter += 1
    return candidate


# ---------------------------------------------------------------------------
# Transaction undo log
# ---------------------------------------------------------------------------

class UndoLog:
    """
    Transaction-style undo log.
    - Written as PENDING at start of execution.
    - Each entry updated in-place as actions complete.
    - File is valid JSON at all times (written atomically via tmp file).
    """

    def __init__(self, output_dir: Path, dry_run: bool = False) -> None:
        self._dry_run = dry_run
        self._output_dir = output_dir
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        self._log_path = output_dir / f"undo_{ts}.json"
        self._payload: dict = {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
            "actions": [],
        }

    @property
    def path(self) -> Path:
        return self._log_path

    def init_pending(self, plan: list) -> None:
        """Write all planned actions as 'pending' before execution starts."""
        for entry in plan:
            action = entry["action"]
            if action == "move":
                self._payload["actions"].append({
                    "action": "move",
                    "src": entry["src"],
                    "dst": entry["dst"],
                    "actual_dst": None,
                    "status": "pending",
                })
            elif action == "delete":
                self._payload["actions"].append({
                    "action": "delete",
                    "src": entry["path"],
                    "trash_path": None,
                    "status": "pending",
                })
            elif action == "skip":
                self._payload["actions"].append({
                    "action": "skip",
                    "path": entry.get("path", ""),
                    "status": "pending",
                })
            elif action == "unknown_review":
                # Human-review items are no-ops in the executor
                self._payload["actions"].append({
                    "action": "unknown_review",
                    "path": entry.get("src", entry.get("path", "")),
                    "status": "pending",
                })
        self._flush()
        print(f"[LOG] Pending undo log: {self._log_path}")

    def update(self, index: int, **kwargs) -> None:
        """Update a single action record and re-flush."""
        self._payload["actions"][index].update(kwargs)
        self._flush()

    def _flush(self) -> None:
        """Write payload atomically (tmp + rename)."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._log_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self._payload, f, indent=2)
        os.replace(tmp, self._log_path)

    def finalize(self) -> None:
        self._payload["finalized_at"] = datetime.now(timezone.utc).isoformat()
        self._flush()
        print(f"[LOG] Undo log finalized: {self._log_path}")

    @property
    def records(self) -> list:
        return self._payload["actions"]


# ---------------------------------------------------------------------------
# Pre-flight permission checks
# ---------------------------------------------------------------------------

def preflight_check(plan: list, trash_dir: Path, dry_run: bool) -> list[dict]:
    """
    Validate all actions before touching anything.
    Returns list of preflight_error dicts; empty = all good.
    """
    errors: list[dict] = []

    for i, entry in enumerate(plan):
        action = entry["action"]

        if action == "move":
            src = entry["src"]
            dst = entry["dst"]
            dst_parent = str(Path(dst).parent)

            # Can we read src?
            if not os.path.exists(src):
                errors.append({
                    "index": i,
                    "action": "move",
                    "src": src,
                    "error": "src does not exist",
                    "status": "preflight_error",
                })
                continue
            if not os.access(src, os.R_OK):
                errors.append({
                    "index": i,
                    "action": "move",
                    "src": src,
                    "error": "no read permission on src",
                    "status": "preflight_error",
                })

            # Can we write to dst parent?
            if os.path.exists(dst_parent):
                if not os.access(dst_parent, os.W_OK):
                    errors.append({
                        "index": i,
                        "action": "move",
                        "dst_parent": dst_parent,
                        "error": "no write permission on dst parent",
                        "status": "preflight_error",
                    })
            # If dst_parent doesn't exist we'll create it — check its nearest ancestor

        elif action == "delete":
            path = entry["path"]
            if not os.path.exists(path):
                errors.append({
                    "index": i,
                    "action": "delete",
                    "src": path,
                    "error": "src does not exist",
                    "status": "preflight_error",
                })
                continue
            if not os.access(path, os.R_OK):
                errors.append({
                    "index": i,
                    "action": "delete",
                    "src": path,
                    "error": "no read permission on src",
                    "status": "preflight_error",
                })

    return errors


# ---------------------------------------------------------------------------
# Trash directory
# ---------------------------------------------------------------------------

def make_trash_dir(output_dir: Path) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    trash = output_dir / "trash" / ts
    trash.mkdir(parents=True, exist_ok=True)
    return trash


# ---------------------------------------------------------------------------
# Cross-device move detection
# ---------------------------------------------------------------------------

def is_cross_device(src: str, dst_parent: str) -> bool:
    """Return True if src and dst are on different filesystems."""
    try:
        src_dev = os.stat(src).st_dev
        # dst_parent may not exist yet; walk up until we find an existing ancestor
        p = dst_parent
        while p and not os.path.exists(p):
            parent = os.path.dirname(p)
            if parent == p:
                break
            p = parent
        if not p or not os.path.exists(p):
            return False
        dst_dev = os.stat(p).st_dev
        return src_dev != dst_dev
    except OSError:
        return False


def cross_device_move(src: str, dst: str, trash_dir: Path) -> None:
    """
    Copy src to dst with shutil.copy2, then move src to trash.
    Used when src and dst are on different devices.
    """
    shutil.copy2(src, dst)
    filename = os.path.basename(src)
    trash_path = str(trash_dir / filename)
    if os.path.exists(trash_path):
        base, ext = os.path.splitext(filename)
        trash_path = str(trash_dir / f"{base}_{datetime.now().strftime('%f')}{ext}")
    shutil.move(src, trash_path)


# ---------------------------------------------------------------------------
# MD5 checksum helper (CORE-002)
# ---------------------------------------------------------------------------

def compute_md5(file_path: str, chunk_size: int = 65536) -> str:
    """Compute MD5 hex digest of a file, reading in chunks to handle large files."""
    md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                md5.update(chunk)
        return md5.hexdigest()
    except OSError as e:
        return f"error:{e}"


# ---------------------------------------------------------------------------
# Execute plan
# ---------------------------------------------------------------------------

def execute_plan(
    plan: list,
    output_dir: Path,
    dry_run: bool,
    on_conflict: str,
    undo_log: UndoLog,
) -> list:
    """
    Execute the action plan. Undo log must already be initialized (PENDING).
    Updates each entry as it completes.
    on_conflict: 'skip' | 'rename' | 'overwrite'
    """
    trash_dir = None if dry_run else make_trash_dir(output_dir)

    for idx, entry in enumerate(plan):
        action = entry["action"]

        if action == "move":
            src = entry["src"]
            dst = entry["dst"]
            dst_parent = str(Path(dst).parent)

            # Conflict handling
            if os.path.exists(dst) and not dry_run:
                if on_conflict == "skip":
                    print(f"[CONFLICT] move {src!r} → {dst!r} (dst exists, skipped)")
                    undo_log.update(idx,
                        status="conflict",
                        reason="dst exists — skipped",
                        actual_dst=None,
                    )
                    continue
                elif on_conflict == "rename":
                    dst = resolve_rename(dst)
                    print(f"[RENAME] conflict resolved → {dst!r}")
                elif on_conflict == "overwrite":
                    print(f"[OVERWRITE] WARNING: replacing {dst!r}")
                    # Will proceed; os.rename / shutil.move handles it

            # CORE-002: MD5 checksum — compute before move if requested
            verify_md5 = entry.get("verify_checksum", False)
            src_md5 = ""
            if verify_md5 and os.path.exists(src):
                src_md5 = compute_md5(src)
                print(f"[MD5:src] {src_md5}  {src!r}")

            if dry_run:
                print(f"[DRY-RUN] move {src!r} → {dst!r}")
                undo_log.update(idx, status="dry-run", actual_dst=dst,
                                src_md5=src_md5 if verify_md5 else None,
                                checksum_status="skipped" if verify_md5 else "")
                continue

            if not os.path.exists(src):
                print(f"[ERROR] move: src not found: {src!r}")
                undo_log.update(idx, status="error", reason="src not found")
                undo_log.finalize()
                sys.exit(1)

            try:
                # Disk space check before write
                try:
                    import shutil as _shutil
                    total, used, free = _shutil.disk_usage(dst_parent)
                    src_size = os.path.getsize(src) if os.path.exists(src) else 0
                    if free < src_size * 1.1:  # need 10% headroom
                        print(f"[ERROR] disk full on {dst_parent!r}: {free} bytes free, need ~{src_size}")
                        undo_log.update(idx, status="error", reason="disk full")
                        continue  # skip this file instead of crashing
                except Exception:
                    pass  # don't let space check failures block the move

                Path(dst_parent).mkdir(parents=True, exist_ok=True)

                cross = is_cross_device(src, dst_parent)
                checksum_status = ""
                dst_md5 = ""
                if cross:
                    cross_device_move(src, dst, trash_dir)
                    print(f"[OK:cross_device] move {src!r} → {dst!r}")
                    undo_log.update(idx,
                        status="ok",
                        actual_dst=dst,
                        cross_device_move=True,
                        src_md5=src_md5,
                        checksum_status="skipped",  # cross-device: src was moved to trash, can't re-verify
                        note="src copied to dst; original moved to trash",
                    )
                else:
                    shutil.move(src, dst)
                    print(f"[OK] move {src!r} → {dst!r}")

                    # CORE-002: MD5 verification after move
                    if verify_md5 and os.path.exists(dst):
                        dst_md5 = compute_md5(dst)
                        print(f"[MD5:dst] {dst_md5}  {dst!r}")
                        if src_md5 and dst_md5 and src_md5 == dst_md5:
                            checksum_status = "verified"
                            print(f"[MD5:OK] checksums match — {src_md5}")
                        elif dst_md5.startswith("error:"):
                            checksum_status = "error"
                            print(f"[MD5:ERROR] could not compute dst MD5: {dst_md5}")
                        else:
                            checksum_status = "mismatch"
                            print(f"[MD5:WARN] checksum mismatch — src={src_md5} dst={dst_md5}")

                    undo_log.update(idx,
                        status="ok",
                        actual_dst=dst,
                        src_md5=src_md5 if verify_md5 else None,
                        dst_md5=dst_md5 if verify_md5 else None,
                        checksum_status=checksum_status if verify_md5 else "",
                    )

            except Exception as e:
                print(f"[ERROR] move failed: {e}")
                undo_log.update(idx, status="error", reason=str(e))
                undo_log.finalize()
                sys.exit(1)

        elif action == "delete":
            path = entry["path"]
            filename = os.path.basename(path)

            if dry_run:
                print(f"[DRY-RUN] delete {path!r} → trash")
                undo_log.update(idx, status="dry-run", trash_path="<dry-run>")
                continue

            if not os.path.exists(path):
                print(f"[ERROR] delete: src not found: {path!r}")
                undo_log.update(idx, status="error", reason="src not found")
                undo_log.finalize()
                sys.exit(1)

            trash_path = str(trash_dir / filename)
            if os.path.exists(trash_path):
                base, ext = os.path.splitext(filename)
                trash_path = str(trash_dir / f"{base}_{datetime.now().strftime('%f')}{ext}")

            try:
                shutil.move(path, trash_path)
                print(f"[OK] delete {path!r} → {trash_path!r}")
                undo_log.update(idx, status="ok", trash_path=trash_path)
            except Exception as e:
                print(f"[ERROR] delete failed: {e}")
                undo_log.update(idx, status="error", reason=str(e))
                undo_log.finalize()
                sys.exit(1)

        elif action == "skip":
            path = entry.get("path", "")
            print(f"[SKIP] {path!r}")
            undo_log.update(idx, status="skipped")

    return undo_log.records


# ---------------------------------------------------------------------------
# cmd_execute
# ---------------------------------------------------------------------------

def cmd_execute(args):
    plan_path = args.plan
    output_dir = Path(args.output_dir).resolve()
    dry_run = args.dry_run
    on_conflict = args.on_conflict

    if on_conflict not in ("skip", "rename", "overwrite"):
        print(f"[ERROR] --on-conflict must be skip|rename|overwrite (got {on_conflict!r})", file=sys.stderr)
        sys.exit(1)

    if on_conflict == "overwrite" and not dry_run:
        print("[WARNING] --on-conflict=overwrite will PERMANENTLY REPLACE destination files. Proceed with caution.")

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

    # --- Pre-flight checks ---
    print("[INFO] Running pre-flight checks...")
    trash_dir_check = output_dir / "trash" / "preflight_check"
    preflight_errors = preflight_check(plan, trash_dir_check, dry_run)
    if preflight_errors:
        print(f"[ERROR] Pre-flight check failed with {len(preflight_errors)} error(s):")
        for err in preflight_errors:
            print(f"  [{err['index']}] {err['action']}: {err['error']} — {err.get('src') or err.get('dst_parent')}")
        print("[ABORT] No files were touched.")
        sys.exit(1)
    print("[INFO] Pre-flight OK")

    # --- Initialize transaction undo log ---
    output_dir.mkdir(parents=True, exist_ok=True)
    undo_log = UndoLog(output_dir, dry_run=dry_run)
    undo_log.init_pending(plan)

    # --- Execute ---
    records = execute_plan(plan, output_dir, dry_run, on_conflict, undo_log)
    undo_log.finalize()

    # --- Summary ---
    ok = sum(1 for r in records if r.get("status") == "ok")
    skipped = sum(1 for r in records if r.get("status") == "skipped")
    conflicts = sum(1 for r in records if r.get("status") == "conflict")
    dry = sum(1 for r in records if r.get("status") == "dry-run")
    errors = sum(1 for r in records if r.get("status") == "error")
    cross = sum(1 for r in records if r.get("cross_device_move"))

    print(
        f"\n[DONE] ok={ok} skipped={skipped} conflicts={conflicts} errors={errors}"
        + (f" cross_device={cross}" if cross else "")
        + (f" dry-run={dry}" if dry_run else "")
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="executor.py — Phase 2 execution engine for file-organizer"
    )
    sub = parser.add_subparsers(dest="command")

    exec_parser = sub.add_parser("execute", help="Execute an action plan")
    exec_parser.add_argument("--plan", required=True, help="Path to action plan JSON")
    exec_parser.add_argument("--output-dir", required=True, help="Output directory for trash + undo log")
    exec_parser.add_argument("--dry-run", action="store_true", help="Simulate execution, touch nothing")
    exec_parser.add_argument(
        "--on-conflict",
        default="skip",
        choices=["skip", "rename", "overwrite"],
        help=(
            "Conflict resolution strategy: "
            "skip (default) = leave dst untouched; "
            "rename = append _1, _2, ... to filename stem; "
            "overwrite = REPLACE dst (DANGEROUS — use with caution)"
        ),
    )

    args = parser.parse_args()

    if args.command == "execute":
        cmd_execute(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
