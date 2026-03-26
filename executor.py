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


# Executor action types — explicit planner→executor contract
# protected / blocked / unknown_review / conflict_review are planner statuses,
# never action types and never reach the executor
ALLOWED_ACTIONS = frozenset({"move", "copy", "delete", "skip"})


def reject_disallowed_actions(plan: list) -> None:
    for i, entry in enumerate(plan):
        action = entry.get("action")
        if action not in ALLOWED_ACTIONS:
            raise ValueError(
                f"Disallowed executor action at plan[{i}]: {action!r} "
                f"(allowed: {', '.join(sorted(ALLOWED_ACTIONS))})"
            )


def validate_plan(plan: list) -> None:
    """ARCH-001: Validate all paths are absolute and actions are known.
    Note: protected / blocked / unknown_review / conflict_review are filtered
    upstream and never reach the executor."""
    errors = []
    reject_disallowed_actions(plan)

    for i, entry in enumerate(plan):
        action = entry.get("action")

        if action == "move":
            src = entry.get("src", "")
            dst = entry.get("dst", "")
            if not os.path.isabs(src):
                errors.append(f"[{i}] move.src is not absolute: {src!r}")
            if not os.path.isabs(dst):
                errors.append(f"[{i}] move.dst is not absolute: {dst!r}")
        elif action == "copy":
            src = entry.get("src", "")
            dst = entry.get("dst", "")
            if not os.path.isabs(src):
                errors.append(f"[{i}] copy.src is not absolute: {src!r}")
            if not os.path.isabs(dst):
                errors.append(f"[{i}] copy.dst is not absolute: {dst!r}")
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
    Transaction-style undo log (SPRINT-9).
    - Written as PENDING at start of execution.
    - Each entry updated in-place as actions complete.
    - File is valid JSON at all times (written atomically via tmp file).
    - Tracks: action_id, plan_id, started_at, completed_at,
      source_revalidation_result, runtime_conflict_result.
    """

    def __init__(self, output_dir: Path, dry_run: bool = False) -> None:
        self._dry_run = dry_run
        self._output_dir = output_dir
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        self._log_path = output_dir / f"undo_{ts}.json"
        self._payload: dict = {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
            "run_status": "planned",  # SPRINT-9: planned → running → partially_completed|completed|failed|cancelled|undone
            "actions": [],
        }

    @property
    def path(self) -> Path:
        return self._log_path

    def init_pending(self, plan: list) -> None:
        """Write all planned actions as 'pending' before execution starts."""
        # SPRINT-9: transaction log with full action_id + src_identity
        for entry in plan:
            action = entry["action"]
            if action == "move":
                self._payload["actions"].append({
                    "action": "move",
                    "action_id": entry.get("action_id", ""),
                    "plan_id": entry.get("plan_id", ""),
                    "src": entry["src"],
                    "dst": entry["dst"],
                    "actual_dst": None,
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "error_type": "",
                    "error_message": "",
                    "warning_message": "",
                    "reverse_action": None,
                    "source_revalidation_result": None,
                    "runtime_conflict_result": None,
                    # EXEC-002: checksum
                    "src_md5": None,
                    "dst_md5": None,
                    "checksum_status": "",
                    # SPRINT-9: src_identity
                    "src_identity": entry.get("src_identity", {}) or {},
                })
            elif action == "copy":
                self._payload["actions"].append({
                    "action": "copy",
                    "action_id": entry.get("action_id", ""),
                    "plan_id": entry.get("plan_id", ""),
                    "src": entry["src"],
                    "dst": entry["dst"],
                    "actual_dst": None,
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "error_type": "",
                    "error_message": "",
                    "warning_message": "",
                    "reverse_action": None,
                    "source_revalidation_result": None,
                    "runtime_conflict_result": None,
                    "src_md5": None,
                    "dst_md5": None,
                    "checksum_status": "",
                    "src_identity": entry.get("src_identity", {}) or {},
                })
            elif action == "delete":
                self._payload["actions"].append({
                    "action": "delete",
                    "action_id": entry.get("action_id", ""),
                    "plan_id": entry.get("plan_id", ""),
                    "src": entry["path"],
                    "trash_path": None,
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "error_type": "",
                    "error_message": "",
                    "warning_message": "",
                    "reverse_action": None,
                    "source_revalidation_result": None,
                    "runtime_conflict_result": None,
                    "src_identity": entry.get("src_identity", {}) or {},
                })
            elif action == "skip":
                self._payload["actions"].append({
                    "action": "skip",
                    "action_id": entry.get("action_id", ""),
                    "plan_id": entry.get("plan_id", ""),
                    "path": entry.get("path", ""),
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "error_type": "",
                    "error_message": "",
                    "warning_message": "",
                    "reverse_action": None,
                    "source_revalidation_result": None,
                    "runtime_conflict_result": None,
                    "src_identity": entry.get("src_identity", {}) or {},
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
        # SPRINT-9: compute run_status from action statuses
        records = self._payload.get("actions", [])
        statuses = [r.get("status", "") for r in records]
        if all(s in ("ok", "skipped", "dry-run", "already_done") for s in statuses):
            self._payload["run_status"] = "completed"
        elif any(s in ("failed", "stale") for s in statuses):
            self._payload["run_status"] = "partially_completed"
        elif all(s == "dry-run" for s in statuses):
            self._payload["run_status"] = "completed"
        self._flush()
        print(f"[LOG] Undo log finalized: {self._log_path} [run_status={self._payload['run_status']}]")

    @property
    def records(self) -> list:
        return self._payload["actions"]


# ---------------------------------------------------------------------------
# Pre-flight permission checks
# ---------------------------------------------------------------------------

def preflight_check(plan: list, trash_dir: Path, dry_run: bool) -> list[dict]:
    """
    EXEC-002: Validate all actions before touching anything.
    Returns list of preflight errors with explicit error_type; empty = all good.
    """
    errors: list[dict] = []

    for i, entry in enumerate(plan):
        action = entry["action"]

        if action in ("move", "copy"):
            src = entry["src"]
            dst = entry["dst"]
            dst_parent = str(Path(dst).parent)

            # Can we read src?
            if not os.path.exists(src):
                errors.append({
                    "index": i,
                    "action": action,
                    "src": src,
                    "error_type": "missing_source",
                    "error_message": "src does not exist",
                    "status": "preflight_error",
                })
                continue
            if not os.access(src, os.R_OK):
                errors.append({
                    "index": i,
                    "action": action,
                    "src": src,
                    "error_type": "permissions",
                    "error_message": "no read permission on src",
                    "status": "preflight_error",
                })

            # Can we write to dst parent?
            if os.path.exists(dst_parent):
                if not os.access(dst_parent, os.W_OK):
                    errors.append({
                        "index": i,
                        "action": action,
                        "dst_parent": dst_parent,
                        "error_type": "permissions",
                        "error_message": "no write permission on dst parent",
                        "status": "preflight_error",
                    })

        elif action == "delete":
            path = entry["path"]
            if not os.path.exists(path):
                errors.append({
                    "index": i,
                    "action": "delete",
                    "src": path,
                    "error_type": "missing_source",
                    "error_message": "src does not exist",
                    "status": "preflight_error",
                })
                continue
            if not os.access(path, os.R_OK):
                errors.append({
                    "index": i,
                    "action": "delete",
                    "src": path,
                    "error_type": "permissions",
                    "error_message": "no read permission on src",
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
# Revalidation helpers (SPRINT-9)
# ---------------------------------------------------------------------------

def revalidate_source(entry: dict) -> dict:
    """
    SPRINT-9: Pre-execute revalidation of source file.

    Returns a dict with keys:
        valid (bool)
        error_type (str)   — "" if valid
        error_message (str)
        src_md5 (str)      — computed if available + required
    """
    src = entry.get("src") or entry.get("path", "")
    src_identity = entry.get("src_identity", {}) or {}

    # Source still exists
    if not os.path.exists(src):
        return {
            "valid": False,
            "error_type": "missing_source",
            "error_message": f"Source no longer exists: {src!r}",
            "src_md5": "",
        }

    # Source still has expected size
    expected_size = src_identity.get("size_at_plan_time", 0)
    if expected_size and os.path.exists(src):
        actual_size = os.path.getsize(src)
        if actual_size != expected_size:
            return {
                "valid": False,
                "error_type": "size_changed",
                "error_message": (
                    f"Source size changed since plan was created: "
                    f"expected {expected_size} bytes, now {actual_size} bytes"
                ),
                "src_md5": "",
            }

    # Hash check if required by policy or available
    verify_checksum = entry.get("verify_checksum", False)
    planned_hash = src_identity.get("hash_if_available", "")
    src_md5 = ""
    if verify_checksum and os.path.exists(src):
        src_md5 = compute_md5(src)
        print(f"[MD5:src] {src_md5}  {src!r}")
        if planned_hash and src_md5 != planned_hash:
            return {
                "valid": False,
                "error_type": "checksum_mismatch",
                "error_message": (
                    f"Source checksum mismatch: plan-time={planned_hash}, "
                    f"current={src_md5}"
                ),
                "src_md5": src_md5,
            }

    # Destination parent still writable
    if entry.get("action") in ("move", "copy"):
        dst = entry.get("dst", "")
        if dst:
            dst_parent = str(Path(dst).parent)
            if os.path.exists(dst_parent) and not os.access(dst_parent, os.W_OK):
                return {
                    "valid": False,
                    "error_type": "permissions",
                    "error_message": f"Destination parent not writable: {dst_parent!r}",
                    "src_md5": src_md5,
                }

    return {"valid": True, "error_type": "", "error_message": "", "src_md5": src_md5}


def check_runtime_conflict(entry: dict) -> dict:
    """
    SPRINT-9: Runtime conflict recheck immediately before executing an action.

    Checks:
    - Destination now exists unexpectedly
    - Source moved/renamed externally
    - Permissions changed

    Returns dict with keys:
        has_conflict (bool)
        reason (str)
        resolution (str)  — "proceed" | "skip" | "rename"
    """
    action = entry.get("action", "")
    src = entry.get("src") or entry.get("path", "")
    dst = entry.get("dst", "")
    on_conflict = entry.get("on_conflict", "skip")

    reason = ""
    resolution = "proceed"

    # Source moved/renamed externally (but still exists)
    # If src still exists but is in a different location than planned, warn
    src_identity = entry.get("src_identity", {}) or {}
    planned_src_path = src_identity.get("path_at_plan_time", src)
    if src != planned_src_path and os.path.exists(src):
        # File was renamed/moved externally — treat as stale
        reason = (
            f"Source moved externally: planned at {planned_src_path!r}, "
            f"now at {src!r}"
        )
        resolution = "skip"

    # Destination now exists when we expected it not to
    if action in ("move", "copy") and dst:
        if os.path.exists(dst):
            # Check if dst is the same file (hardlink or already done)
            try:
                if os.path.exists(src):
                    src_stat = os.stat(src)
                    dst_stat = os.stat(dst)
                    if src_stat.st_ino == dst_stat.st_ino:
                        reason = "Source and destination are the same file (already done)"
                        resolution = "skip"
                    elif on_conflict == "skip":
                        reason = f"Destination already exists at runtime: {dst!r}"
                        resolution = "skip"
                    elif on_conflict == "rename":
                        reason = f"Destination exists at runtime, will rename: {dst!r}"
                        resolution = "rename"
                    elif on_conflict == "overwrite":
                        reason = f"Destination exists at runtime, will overwrite: {dst!r}"
                        resolution = "proceed"
            except OSError:
                pass

    return {
        "has_conflict": resolution == "skip" and bool(reason),
        "reason": reason,
        "resolution": resolution,
    }


def check_already_done(entry: dict, src_md5: str) -> dict:
    """
    SPRINT-9: Check if this action was already completed in a previous run.

    Signals:
    - Source missing + destination has expected file identity
    - Transaction log shows action completed

    Returns dict with keys:
        already_done (bool)
        reason (str)
    """
    src = entry.get("src") or entry.get("path", "")
    dst = entry.get("dst", "")
    src_identity = entry.get("src_identity", {}) or {}

    # Source is gone but destination exists with matching identity
    if not os.path.exists(src) and dst and os.path.exists(dst):
        # Verify size if we have planned size
        expected_size = src_identity.get("size_at_plan_time", 0)
        if expected_size:
            dst_size = os.path.getsize(dst)
            if dst_size == expected_size:
                return {
                    "already_done": True,
                    "reason": (
                        f"Source moved to destination (size match: {expected_size} bytes); "
                        f"action already completed"
                    ),
                }
        else:
            # No size — assume already done if src gone and dst exists
            return {
                "already_done": True,
                "reason": "Source no longer exists; destination is present; assuming already done",
            }

    # Source still exists — not already done
    return {"already_done": False, "reason": ""}


# ---------------------------------------------------------------------------
# Execute plan (SPRINT-9: revalidation, continue-on-error, already_done)
# ---------------------------------------------------------------------------

def execute_plan(
    plan: list,
    output_dir: Path,
    dry_run: bool,
    on_conflict: str,
    undo_log: UndoLog,
) -> list:
    """
    SPRINT-9: Execute the action plan with idempotency & concurrency support.

    - Undo log must already be initialized (PENDING).
    - Updates each entry as it completes.
    - Continue-on-error by default (one action failure does not stop the run).
    - Pre-execute revalidation before every action.
    - Runtime conflict recheck before every action.
    - already_done detection for rerun safety.

    Executor actions: move | copy | delete | skip
    NOTE: protected / blocked / unknown_review / conflict_review are
    planner statuses — these never reach execute_plan() (filtered upstream).

    on_conflict: 'skip' | 'rename' | 'overwrite'
    """
    reject_disallowed_actions(plan)
    trash_dir = None if dry_run else make_trash_dir(output_dir)

    for idx, entry in enumerate(plan):
        action = entry["action"]
        action_id = entry.get("action_id", f"action-{idx}")
        plan_id = entry.get("plan_id", "")
        started_at = datetime.now(timezone.utc).isoformat()

        # Inject on_conflict from entry (set by planner from rule.conflict_mode)
        entry_on_conflict = entry.get("conflict_mode", on_conflict)

        # Mark as running
        undo_log.update(idx,
            action_id=action_id,
            plan_id=plan_id,
            started_at=started_at,
            status="running",
        )

        # ── SPRINT-9: Pre-execute revalidation ─────────────────────────────
        rev_result = revalidate_source(entry)
        undo_log.update(idx, source_revalidation_result=rev_result)
        if not rev_result["valid"]:
            print(f"[STALE] action {idx} ({action}): {rev_result['error_message']}")
            undo_log.update(idx,
                status="stale",
                error_type=rev_result["error_type"],
                error_message=rev_result["error_message"],
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            continue  # SPRINT-9: continue-on-error

        src_md5 = rev_result["src_md5"]

        # ── SPRINT-9: already_done detection ───────────────────────────────
        done_check = check_already_done(entry, src_md5)
        if done_check["already_done"]:
            print(f"[ALREADY_DONE] action {idx}: {done_check['reason']}")
            undo_log.update(idx,
                status="already_done",
                warning_message=done_check["reason"],
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            continue  # SPRINT-9: already_done skips but doesn't fail

        # ── SPRINT-9: Runtime conflict recheck ─────────────────────────────
        rt_conflict = check_runtime_conflict({**entry, "on_conflict": entry_on_conflict})
        undo_log.update(idx, runtime_conflict_result=rt_conflict)
        if rt_conflict["has_conflict"]:
            if rt_conflict["resolution"] == "skip":
                print(f"[RUNTIME_CONFLICT] action {idx}: {rt_conflict['reason']}")
                undo_log.update(idx,
                    status="failed",
                    error_type="runtime_conflict",
                    error_message=rt_conflict["reason"],
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                continue  # SPRINT-9: continue-on-error

        dst = entry.get("dst", "")
        src = entry.get("src") or entry.get("path", "")

        # ── DRY-RUN ──────────────────────────────────────────────────────────
        if dry_run:
            print(f"[DRY-RUN] {action} {src!r} → {dst!r}")
            undo_log.update(idx,
                status="dry-run",
                actual_dst=dst,
                src_md5=src_md5 if src_md5 else None,
                checksum_status="skipped" if entry.get("verify_checksum") else "",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            continue

        # ── CONFLICT RESOLUTION ─────────────────────────────────────────────
        if action in ("move", "copy") and dst and os.path.exists(dst):
            if rt_conflict["resolution"] == "rename":
                dst = resolve_rename(dst)
                print(f"[RENAME] conflict resolved → {dst!r}")
            elif rt_conflict["resolution"] == "skip":
                undo_log.update(idx,
                    status="conflict",
                    error_type="conflict",
                    error_message=f"dst exists — skipped by on-conflict={entry_on_conflict}",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                continue
            elif rt_conflict["resolution"] == "proceed":
                print(f"[OVERWRITE] WARNING: replacing {dst!r}")

        dst_parent = str(Path(dst).parent) if dst else ""

        # ── EXECUTE ─────────────────────────────────────────────────────────
        error_type = ""
        error_message = ""
        checksum_status = ""
        dst_md5 = ""
        actual_dst = dst
        cross_device_move_flag = False

        try:
            # Disk space check
            try:
                import shutil as _shutil
                total, used, free = _shutil.disk_usage(dst_parent)
                src_size = os.path.getsize(src) if os.path.exists(src) else 0
                if free < src_size * 1.1:
                    raise OSError(f"Disk full on {dst_parent!r}: {free} bytes free, need ~{src_size}")
            except OSError as e:
                raise  # re-raise for handling below

            if action == "move":
                Path(dst_parent).mkdir(parents=True, exist_ok=True)
                cross = is_cross_device(src, dst_parent)

                if cross:
                    cross_device_move(src, dst, trash_dir)
                    cross_device_move_flag = True
                    print(f"[OK:cross_device] move {src!r} → {dst!r}")
                    undo_log.update(idx,
                        status="ok",
                        actual_dst=dst,
                        cross_device_move=True,
                        src_md5=src_md5 if src_md5 else None,
                        checksum_status="skipped",
                    )
                else:
                    shutil.move(src, dst)
                    print(f"[OK] move {src!r} → {dst!r}")

                    if entry.get("verify_checksum") and os.path.exists(dst):
                        dst_md5 = compute_md5(dst)
                        print(f"[MD5:dst] {dst_md5}  {dst!r}")
                        if src_md5 and dst_md5 == src_md5:
                            checksum_status = "verified"
                            print(f"[MD5:OK] checksums match — {src_md5}")
                        elif dst_md5.startswith("error:"):
                            checksum_status = "error"
                        else:
                            checksum_status = "mismatch"
                            print(f"[MD5:WARN] checksum mismatch — src={src_md5} dst={dst_md5}")
                            error_type = "checksum_mismatch"
                            error_message = f"MD5 mismatch: src={src_md5} dst={dst_md5}"

                    undo_log.update(idx,
                        status="ok",
                        actual_dst=dst,
                        src_md5=src_md5 if src_md5 else None,
                        dst_md5=dst_md5 if dst_md5 else None,
                        checksum_status=checksum_status if entry.get("verify_checksum") else "",
                        error_type=error_type,
                        error_message=error_message,
                    )

            elif action == "copy":
                Path(dst_parent).mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                print(f"[OK] copy {src!r} → {dst!r}")
                undo_log.update(idx, status="ok", actual_dst=dst)

            elif action == "delete":
                path = entry["path"]
                filename = os.path.basename(path)
                trash_path = str(trash_dir / filename)
                if os.path.exists(trash_path):
                    base, ext = os.path.splitext(filename)
                    trash_path = str(trash_dir / f"{base}_{datetime.now().strftime('%f')}{ext}")
                shutil.move(path, trash_path)
                print(f"[OK] delete {path!r} → {trash_path!r}")
                undo_log.update(idx, status="ok", trash_path=trash_path)

            elif action == "skip":
                print(f"[SKIP] {src!r}")
                undo_log.update(idx, status="skipped")

        except OSError as e:
            err_type = "permissions" if e.errno in (1, 13, 21) else "error"
            print(f"[ERROR] {action} failed: {e}")
            undo_log.update(idx,
                status="failed",
                error_type=err_type,
                error_message=str(e),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            continue  # SPRINT-9: continue-on-error

        except Exception as e:
            print(f"[ERROR] {action} failed: {e}")
            undo_log.update(idx,
                status="failed",
                error_type="error",
                error_message=str(e),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            continue  # SPRINT-9: continue-on-error

        # Mark completed for successful actions
        undo_log.update(idx, completed_at=datetime.now(timezone.utc).isoformat())

    return undo_log.records


class Executor:
    """Compatibility wrapper for import-based callers."""

    ALLOWED_ACTIONS = ALLOWED_ACTIONS

    @staticmethod
    def validate(plan: list) -> None:
        validate_plan(plan)

    @staticmethod
    def execute(
        plan: list,
        output_dir: str | Path,
        dry_run: bool = True,
        on_conflict: str = "skip",
    ) -> list:
        resolved_output_dir = Path(output_dir).resolve()
        validate_plan(plan)
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        undo_log = UndoLog(resolved_output_dir, dry_run=dry_run)
        undo_log.init_pending(plan)
        undo_log._payload["run_status"] = "running"
        undo_log._flush()
        execute_plan(plan, resolved_output_dir, dry_run, on_conflict, undo_log)
        undo_log.finalize()
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
    # SPRINT-9: mark run as running
    undo_log._payload["run_status"] = "running"
    undo_log._flush()
    records = execute_plan(plan, output_dir, dry_run, on_conflict, undo_log)
    undo_log.finalize()

    # --- SPRINT-9 Summary ---
    ok = sum(1 for r in records if r.get("status") == "ok")
    skipped = sum(1 for r in records if r.get("status") == "skipped")
    conflicts = sum(1 for r in records if r.get("status") == "conflict")
    dry = sum(1 for r in records if r.get("status") == "dry-run")
    # SPRINT-9: new statuses
    errors = sum(1 for r in records if r.get("status") == "failed")
    stale = sum(1 for r in records if r.get("status") == "stale")
    already_done = sum(1 for r in records if r.get("status") == "already_done")
    cross = sum(1 for r in records if r.get("cross_device_move"))

    run_status = undo_log._payload.get("run_status", "unknown")

    print(
        f"\n[DONE] run_status={run_status} ok={ok} skipped={skipped}"
        f" conflicts={conflicts} errors={errors} stale={stale} already_done={already_done}"
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
