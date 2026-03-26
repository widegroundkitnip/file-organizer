#!/usr/bin/env python3
"""
app.py — Phase 3: FastAPI Web App
File Organizer & Deduper

Serves the web UI and provides API endpoints for:
- Scanning directories (wraps organizer.py)
- Browsing manifests
- Managing rules + settings
- Generating previews (via planner.py)
- Executing action plans (wraps executor.py)

Port: 3001
"""

from __future__ import annotations

import threading

import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List

# Phase 3 extended modules
from scanner import build_cross_manifest, CrossPathDuplicateFinder, StructureAnalyzer
from scanner.manifest import ExtendedManifestBuilder
from scanner.duplicate import find_similar_duplicates
from planner import plan_from_manifest, RuleManager

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.resolve()
WEB_UI_DIR = BASE_DIR / "web_ui"
SETTINGS_PATH = BASE_DIR / "settings.json"
SCANS_DIR = BASE_DIR / "scans"

SCANS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="File Organizer & Deduper", version="3.0.0")

# In-progress scan state (used by /api/scan/status)
_scan_progress_state = {
    "running": False,
    "phase": "idle",
    "current_path": "",
    "files_found": 0,
    "manifest_path": None,
    "manifest_id": None,
    "total_files": 0,
    "error": None,
    "cancel_event": None,
}
_scan_progress_lock = threading.Lock()

# In-memory manifest registry (populated by /api/scan after new-schema scans)
# Key: manifest_id (str), Value: full manifest dict
_manifest_registry: dict[str, dict] = {}
_registry_lock = threading.Lock()

# CORS — local dev, allow all
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[SETTINGS] Corrupted settings.json ({e}) — using defaults")
    return {
        "parent_folders": [],
        "rules": [],
        "exclude_patterns": [],
    }


def save_settings(data: dict) -> None:
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SETTINGS_PATH)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    path: str
    mode: str = "fast"
    include_hidden: bool = False
    exclude_dirs: Optional[list[str]] = None


class RulesUpdate(BaseModel):
    rules: list[dict]


class PreviewRequest(BaseModel):
    manifest_path: str
    rules: list[dict]
    scope_mode: Optional[str] = "preserve_parent_boundaries"
    parent_folders: Optional[list[str]] = None
    project_roots: Optional[list[dict]] = None


class ExecuteRequest(BaseModel):
    action_plan: list[dict]
    output_dir: str
    dry_run: bool = True  # default SAFE — agent testing can't accidentally delete files
    on_conflict: str = "rename"


class SettingsUpdate(BaseModel):
    # Accept any dict
    class Config:
        extra = "allow"


# ---------------------------------------------------------------------------
# Pydantic models — Duplicate Review (SPRINT-10)
# ---------------------------------------------------------------------------

class DuplicateGroupReviewRequest(BaseModel):
    """SPRINT-10: Request for detailed duplicate group review data."""
    group_id: int
    tier: str  # exact | likely | similar
    files: list[dict]  # list of file dicts with path, size, mtime, etc.


class DuplicateGroupReviewResponse(BaseModel):
    """SPRINT-10: Detailed review data for a single duplicate group."""
    group_id: int
    tier: str
    files: list[dict]  # full file metadata
    keeper_recommendation: dict  # {keeper_path, reason}
    trash_consequences: dict  # {trash_count, total_trash_size, files_affected}
    metadata_summary: dict  # per-file metadata highlights
    metadata_policy_used: str  # "keeper_wins_v1"


class DuplicateConsolidateRequest(BaseModel):
    """SPRINT-10: User's consolidate decision for a duplicate group."""
    group_id: int
    tier: str
    keeper_path: str  # path the user chose to keep
    # Other paths → moved to trash (executor receives delete actions)


class DuplicateConsolidateResponse(BaseModel):
    """SPRINT-10: Result of executing a duplicate consolidation."""
    group_id: int
    keeper_path: str
    trash_paths: list[str]
    output_dir: str
    undo_log_path: str
    action_ids: list[str]
    dry_run: bool


# ---------------------------------------------------------------------------
# API: Scan
# ---------------------------------------------------------------------------

@app.post("/api/scan")
async def api_scan(req: ScanRequest):
    """Scan a directory using ManifestScanner (canonical scanner) directly.
    
    No subprocess, no disk artifact — fully in-process.
    """
    global _scan_progress_state

    path = os.path.expanduser(req.path)
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    # Check if a scan is already running
    with _scan_progress_lock:
        if _scan_progress_state["running"]:
            raise HTTPException(status_code=409, detail="A scan is already in progress")
        cancel_event = threading.Event()
        _scan_progress_state = {
            "running": True,
            "phase": "walking",
            "current_path": path,
            "files_found": 0,
            "manifest_path": None,
            "manifest_id": None,
            "total_files": 0,
            "error": None,
            "cancel_event": cancel_event,
        }

    timestamp_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    manifest_id = f"scan_{timestamp_str}"

    # Progress callback to update _scan_progress_state
    def progress_callback(state: dict):
        with _scan_progress_lock:
            _scan_progress_state["phase"] = state.get("phase", "walking")
            _scan_progress_state["current_path"] = state.get("current_path", path)
            _scan_progress_state["files_found"] = state.get("files_found", 0)

    try:
        # Build manifest using canonical scanner (ExtendedManifestBuilder)
        builder = ExtendedManifestBuilder(
            paths=[path],
            mode=req.mode,
            include_hidden=req.include_hidden,
            exclude_dirs=req.exclude_dirs,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

        # Update progress state to "hashing" if deep mode
        with _scan_progress_lock:
            _scan_progress_state["phase"] = "hashing" if req.mode == "deep" else "walking"

        manifest = builder.scan()

        if cancel_event.is_set():
            with _scan_progress_lock:
                _scan_progress_state["running"] = False
                _scan_progress_state["phase"] = "cancelled"
            raise HTTPException(status_code=499, detail="Scan cancelled")

        # Add schema version to manifest
        manifest["schema_version"] = "2"
        manifest["manifest_id"] = manifest_id

        # Run duplicate detection (Tier 1/2/3)
        finder = CrossPathDuplicateFinder(manifest["files"])
        dupes = finder.find()
        tier1 = dupes.get("tier1", [])
        tier2 = dupes.get("tier2", [])
        tier3 = dupes.get("tier3") or []

        # Run structure analysis
        analyzer = StructureAnalyzer(manifest, [path])
        structure = analyzer.analyze()

        # Compute empty_folders and hidden_folders
        from scanner.utils import find_empty_folders, find_hidden_folders
        empty_folders = find_empty_folders(path, req.include_hidden)
        hidden_folders = find_hidden_folders(path)

        # Unknown file summary
        unknown_files = [
            f for f in manifest["files"]
            if f.get("classification") in ("unknown", "system")
        ]

        total_files = manifest.get("scan_meta", {}).get("total_files", 0)

        # Store manifest in registry for /api/manifest/{id} compatibility
        with _registry_lock:
            _manifest_registry[manifest_id] = manifest

        return {
            "status": "ok",
            "manifest_id": manifest_id,
            "total_files": total_files,
            "manifest": manifest,
            "duplicates": tier1 + tier2 + tier3,
            "tier1": tier1,
            "tier2": tier2,
            "tier3": tier3,
            "structure": structure,
            "empty_folders": empty_folders,
            "hidden_folders": hidden_folders,
            "unknown_files": unknown_files[:100],
            "unknown_count": len(unknown_files),
            "is_empty": len(manifest["files"]) == 0,
        }

    except HTTPException:
        raise
    except Exception as e:
        with _scan_progress_lock:
            _scan_progress_state["running"] = False
            _scan_progress_state["phase"] = "done"
            _scan_progress_state["error"] = str(e)
        raise HTTPException(status_code=500, detail=f"Scan error: {e}")


@app.get("/api/scan/status")
async def api_scan_status():
    """Return current scan progress. Returns 200 even when no scan is running."""
    with _scan_progress_lock:
        state = dict(_scan_progress_state)
    # Don't expose the cancel event in the response
    response = {
        "running": state["running"],
        "phase": state["phase"],
        "current_path": state["current_path"],
        "files_found": state["files_found"],
        "total_files": state["total_files"],
        "manifest_path": state["manifest_path"],
        "manifest_id": state["manifest_id"],
        "error": state["error"],
    }
    return response


@app.post("/api/scan/cancel")
async def api_scan_cancel():
    """Cancel the currently running scan."""
    with _scan_progress_lock:
        state = dict(_scan_progress_state)
    if not state["running"]:
        return {"ok": False, "reason": "No scan in progress"}
    cancel_event = state.get("cancel_event")
    if cancel_event:
        cancel_event.set()
    return {"ok": True}


# ---------------------------------------------------------------------------
# API: Manifest
# ---------------------------------------------------------------------------

@app.get("/api/manifest/{manifest_id}")
async def api_get_manifest(manifest_id: str):
    """Return manifest JSON for a given scan id.
    
    Checks in-memory registry first (new-schema scans), then falls back to disk.
    """
    # 1. Check in-memory registry (new-schema in-process scans)
    with _registry_lock:
        if manifest_id in _manifest_registry:
            return _manifest_registry[manifest_id]
    # 2. Fall back to disk (old organizer.py-produced scans)
    manifest_path = SCANS_DIR / f"{manifest_id}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Manifest not found: {manifest_id}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/scans")
async def api_list_scans():
    """List all scan manifests (both in-memory and on-disk)."""
    scans = []
    # 1. In-memory registry entries (new-schema in-process scans)
    with _registry_lock:
        for mid, manifest in _manifest_registry.items():
            meta = manifest.get("scan_meta", {})
            scans.append({
                "id": mid,
                "filename": None,
                "path": meta.get("paths_scanned", [""])[0] if meta.get("paths_scanned") else "",
                "mode": meta.get("mode", ""),
                "timestamp": meta.get("timestamp", ""),
                "total_files": meta.get("total_files", 0),
                "total_size_bytes": meta.get("total_size_bytes", 0),
                "in_memory": True,
            })
    # 2. Disk-based scans (old organizer.py-produced manifests)
    for p in sorted(SCANS_DIR.glob("scan_*.json"), reverse=True):
        try:
            with open(p, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            meta = manifest.get("scan_meta", {})
            scans.append({
                "id": p.stem,
                "filename": p.name,
                "path": meta.get("path", ""),
                "mode": meta.get("mode", ""),
                "timestamp": meta.get("timestamp", ""),
                "total_files": meta.get("total_files", 0),
                "total_size_bytes": meta.get("total_size_bytes", 0),
                "in_memory": False,
            })
        except Exception:
            continue
    # Sort by timestamp descending
    scans.sort(key=lambda s: s.get("timestamp", ""), reverse=True)
    return scans


@app.get("/api/scans/{scan_id}")
async def api_get_scan(scan_id: str):
    """Return scan metadata including the manifest path for a given scan id."""
    manifest_path = SCANS_DIR / f"{scan_id}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Scan not found: {scan_id}")
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        meta = manifest.get("scan_meta", {})
        return {
            "id": scan_id,
            "manifest_path": str(manifest_path),
            "filename": manifest_path.name,
            "path": meta.get("path", ""),
            "mode": meta.get("mode", ""),
            "timestamp": meta.get("timestamp", ""),
            "total_files": meta.get("total_files", 0),
            "total_size_bytes": meta.get("total_size_bytes", 0),
            "scan_roots": meta.get("scan_roots", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read scan: {e}")


# ---------------------------------------------------------------------------
# API: Rules
# ---------------------------------------------------------------------------

@app.get("/api/rules")
async def api_get_rules():
    from planner import RuleManager
    rm = RuleManager(str(BASE_DIR / "rules.json"))
    return {"rules": [r.to_dict() for r in rm.rules]}


@app.put("/api/rules")
async def api_put_rules(body: RulesUpdate):
    from planner.rules import Rule
    # Load existing rules for comparison (to detect created vs modified)
    rm_existing = RuleManager(str(BASE_DIR / "rules.json"))
    existing_ids = {r.id for r in rm_existing.rules}
    rules = []
    for i, r in enumerate(body.rules):
        try:
            rules.append(Rule.from_dict(r))
        except Exception as e:
            raise HTTPException(400, detail=f"Rule #{i} ('{r.get('name','?')}'): {e}")
    rm = RuleManager(str(BASE_DIR / "rules.json"))
    try:
        # Detect rule_created vs rule_modified events
        new_ids = {r.id for r in rules}
        from planner.learner import log_rule_created, log_rule_modified
        for rule in rules:
            if rule.id in existing_ids:
                log_rule_modified(rule.to_dict())
            else:
                log_rule_created(rule.to_dict())
        rm.rules = rules
        rm.save()
    except Exception as e:
        logger.error(f"[RULES] Failed to save rules: {e}")
        raise HTTPException(500, detail=f"Failed to save rules: {e}")
    return {"status": "ok", "rules": [r.to_dict() for r in rm.rules]}


# ---------------------------------------------------------------------------
# API: Learner — Suggestions
# ---------------------------------------------------------------------------

from pydantic import BaseModel


class SuggestionActionRequest(BaseModel):
    suggestion: dict
    rule: dict  # the proposed_rule converted to a full Rule dict


class LearnerActionEvent(BaseModel):
    """Log an approved action for the learner."""
    path: str
    ext: str = ""
    category: str = "other"
    parent: str = ""
    tree: str = ""
    size_bytes: int = 0
    action_type: str = "move"
    src: str = ""
    dst: str = ""
    destination_template: str = ""
    rule_id: Optional[str] = None
    scope_mode: str = "preserve_parent_boundaries"


@app.get("/api/learner/suggestions")
async def api_get_suggestions(days_back: int = 30):
    """Return rule suggestions from pattern aggregation.

    Runs all 4 pattern types against the event log and returns suggestions
    that pass support_count >= 5 and consistency >= 0.8 thresholds.

    Query params:
        days_back: only consider events from the last N days (default 30)
    """
    try:
        from planner import RuleManager
        from planner.learner import get_suggestions, learner_stats
        rm = RuleManager(str(BASE_DIR / "rules.json"))
        suggestions = get_suggestions(days_back=days_back, active_rules=rm.rules)
        stats = learner_stats(days_back=days_back)
        return {"suggestions": suggestions, "stats": stats}
    except Exception as e:
        logger.error(f"[LEARNER] Failed to get suggestions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Learner error: {e}")


@app.post("/api/learner/suggestions/accept")
async def api_accept_suggestion(body: SuggestionActionRequest):
    """Accept a learner suggestion → log event, clear suppression, return rule dict."""
    try:
        from planner.learner import accept_suggestion
        from planner.rules import Rule
        accept_suggestion(body.suggestion)
        rule = Rule.from_dict(body.rule)
        rm = RuleManager(str(BASE_DIR / "rules.json"))
        rm.add_rule(rule)
        rm.save()
        return {"status": "ok", "rule": rule.to_dict()}
    except Exception as e:
        logger.error(f"[LEARNER] Failed to accept suggestion: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Accept error: {e}")


@app.post("/api/learner/suggestions/dismiss")
async def api_dismiss_suggestion(body: SuggestionActionRequest):
    """Dismiss a learner suggestion → log event, record suppression."""
    try:
        from planner.learner import dismiss_suggestion
        dismiss_suggestion(body.suggestion)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[LEARNER] Failed to dismiss suggestion: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Dismiss error: {e}")


@app.get("/api/learner/stats")
async def api_learner_stats(days_back: int = 30):
    """Return learner statistics: event counts, suppression state, storage path."""
    try:
        from planner.learner import learner_stats
        return learner_stats(days_back=days_back)
    except Exception as e:
        logger.error(f"[LEARNER] Failed to get stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Learner stats error: {e}")


@app.get("/api/learner/events")
async def api_learner_events(days_back: int = 30, limit: int = 100):
    """Return raw learner events (last N events, most recent first)."""
    try:
        from planner.learner import _iter_events
        events = list(_iter_events(days_back=days_back))
        events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return {"events": events[:limit], "total": len(events)}
    except Exception as e:
        logger.error(f"[LEARNER] Failed to get events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Learner events error: {e}")


@app.post("/api/learner/log-action")
async def api_log_action(event: LearnerActionEvent):
    """
    Log an approved action for the learner to observe.
    Called by the UI when user confirms a batch in Preview/Execute.

    Args:
        path:          file path
        ext:           extension (e.g. "jpg")
        category:      file category (images/documents/video/etc.)
        parent:        immediate parent folder name
        tree:          root scan tree name
        size_bytes:    file size in bytes
        action_type:   move/copy/delete/skip
        src:           source path
        dst:           destination path
        destination_template:  destination template used
        rule_id:       rule that triggered this action (if any)
        scope_mode:    current scope mode
    """
    try:
        from planner.learner import log_action_approved
        file_info = {
            "path": event.path,
            "ext": event.ext,
            "category": event.category,
            "parent": event.parent,
            "tree": event.tree,
            "size_bytes": event.size_bytes,
        }
        action_info = {
            "type": event.action_type,
            "src": event.src,
            "dst": event.dst,
            "destination_template": event.destination_template,
        }
        context_info = {
            "rule_id": event.rule_id or "",
            "scope_mode": event.scope_mode,
            "user_confirmed": True,
        }
        event_id = log_action_approved(file_info, action_info, context_info)
        return {"status": "ok", "event_id": event_id}
    except Exception as e:
        logger.error(f"[LEARNER] Failed to log action: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Log action error: {e}")


# ---------------------------------------------------------------------------
# API: Duplicate Review (SPRINT-10)
# ---------------------------------------------------------------------------

@app.post("/api/duplicates/review", response_model=DuplicateGroupReviewResponse)
async def api_duplicate_review(req: DuplicateGroupReviewRequest):
    """
    SPRINT-10: Return detailed review data for a single duplicate group.

    Shows:
    - All files in the group
    - System-recommended keeper + reason
    - Metadata summary per file
    - Trash consequences
    """
    from scanner.duplicate import recommend_keeper

    files = req.files
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Keeper recommendation
    rec = recommend_keeper(files)

    # Metadata summary per file
    metadata_summary = {}
    for f in files:
        path = f.get("path", "")
        metadata_summary[path] = {
            "size": f.get("size_bytes") or f.get("size", 0),
            "mtime": f.get("mtime", 0.0),
            "ctime": f.get("ctime", 0.0),
            "extension": f.get("extension") or f.get("ext", ""),
            "relative_path": f.get("relative_path", ""),
            "parent_tree": f.get("parent_tree", ""),
            "classification": f.get("classification", "known"),
        }

    # Trash consequences: all files except keeper
    trash_paths = [f.get("path", "") for f in files if f.get("path", "") != rec["keeper_path"]]
    total_trash_size = sum(
        (f.get("size_bytes") or f.get("size", 0))
        for f in files
        if f.get("path", "") != rec["keeper_path"]
    )

    return DuplicateGroupReviewResponse(
        group_id=req.group_id,
        tier=req.tier,
        files=files,
        keeper_recommendation={
            "keeper_path": rec["keeper_path"],
            "reason": rec["reason"],
        },
        trash_consequences={
            "trash_count": len(trash_paths),
            "total_trash_size": total_trash_size,
            "files_affected": trash_paths,
        },
        metadata_summary=metadata_summary,
        metadata_policy_used="keeper_wins_v1",
    )


@app.post("/api/duplicates/execute-review")
async def api_duplicate_execute_review(req: DuplicateConsolidateRequest):
    """
    SPRINT-10: Execute a duplicate consolidation decision.

    User chose keeper_path → executor receives: delete_to_trash for all other paths.
    Grouped transaction with single undo log entry per file.

    The plan emitted is a list of delete actions (one per duplicate to trash),
    all tagged with the same group_id for undo grouping.
    """
    import uuid

    keeper_path = req.keeper_path
    all_paths = set(f.get("path", "") for f in req.files) if req.files else set()
    trash_paths = [p for p in all_paths if p and p != keeper_path]

    if not trash_paths:
        return DuplicateConsolidateResponse(
            group_id=req.group_id,
            keeper_path=keeper_path,
            trash_paths=[],
            output_dir="",
            undo_log_path="",
            action_ids=[],
            dry_run=req.dry_run,
        )

    # Build grouped action plan — all delete actions for this group
    action_plan = []
    action_ids = []
    group_id_str = f"dup_merge_{req.group_id}_{uuid.uuid4().hex[:8]}"

    for path in trash_paths:
        action_id = str(uuid.uuid4())
        action_ids.append(action_id)
        action_plan.append({
            "action": "delete",
            "path": path,
            "plan_id": group_id_str,
            "action_id": action_id,
            "src_identity": {},
        })

    # Write plan to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir="/tmp", prefix="fo_dup_plan_"
    ) as tmp:
        json.dump(action_plan, tmp, indent=2)
        plan_path = tmp.name

    settings = load_settings()
    output_dir = os.path.expanduser(req.output_dir or settings.get("base_output_dir", "/tmp/file-organizer-output"))
    os.makedirs(output_dir, exist_ok=True)

    # Pre-flight
    missing = [p for p in trash_paths if not os.path.exists(p)]
    if missing and not req.dry_run:
        raise HTTPException(
            status_code=400,
            detail=f"Files not found (deleted since review?): {missing[:5]}"
        )

    cmd = [
        sys.executable, str(BASE_DIR / "executor.py"),
        "execute",
        "--plan", plan_path,
        "--output-dir", output_dir,
        "--on-conflict", "skip",
    ]
    if req.dry_run:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Execute timed out (600s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execute error: {e}")

    # Find the undo log path from output dir
    undo_log_path = ""
    try:
        undo_logs = sorted(Path(output_dir).glob("undo_*.json"), key=lambda p: p.stat().st_mtime)
        if undo_logs:
            undo_log_path = str(undo_logs[-1])
    except Exception:
        pass

    return DuplicateConsolidateResponse(
        group_id=req.group_id,
        keeper_path=keeper_path,
        trash_paths=trash_paths,
        output_dir=output_dir,
        undo_log_path=undo_log_path,
        action_ids=action_ids,
        dry_run=req.dry_run,
    )


# ---------------------------------------------------------------------------
# API: Run Profiles
# ---------------------------------------------------------------------------

@app.get("/api/profiles")
async def api_get_profiles():
    from planner.profiles import PROFILES
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "icon": p.icon,
            "scope_labels": p.scope_labels,  # PROF-011: user-facing scope mode labels
            "allowed_scope_modes": p.allowed_scope_modes,
            "default_scope_mode": p.default_scope_mode,
        }
        for p in PROFILES
    ]


@app.post("/api/profiles/{profile_id}/generate-rules")
async def api_generate_rules(profile_id: str):
    from planner.profiles import get_profile
    from planner.rules import Rule
    profile = get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    added = []
    for rule_dict in profile.rule_bundle:
        rule = Rule.from_dict(rule_dict)
        rule.enabled = False
        rm = RuleManager(str(BASE_DIR / "rules.json"))
        rm.add_rule(rule)
        added.append(rule.id)
    rm.save()
    return {"added": added, "count": len(added)}


# ---------------------------------------------------------------------------
# API: Preview (planner)
# ---------------------------------------------------------------------------

@app.post("/api/preview")
async def api_preview(req: PreviewRequest):
    """Generate action plan from manifest + rules via planner.plan_from_manifest()."""
    if not os.path.exists(req.manifest_path):
        raise HTTPException(status_code=404, detail=f"Manifest not found: {req.manifest_path}")

    from planner.rules import Rule

    # Convert raw rule dicts to Rule objects using from_dict
    rules = [Rule.from_dict(r) for r in (req.rules or [])]

    settings = load_settings()
    output_dir = settings.get("base_output_dir", "/tmp/file-organizer-output")

    try:
        from planner import load_manifest, plan_from_manifest
        manifest = load_manifest(req.manifest_path)
        result = plan_from_manifest(
            manifest=manifest,
            rules=rules,
            default_output_dir=output_dir,
            scope_mode=req.scope_mode,
            parent_folders=req.parent_folders,
            project_roots=req.project_roots,
        )
        # Canonical return: {actions, stats, plan_id}
        return result
    except Exception as e:
        logger.error(f"[PREVIEW] Failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Preview failed: {e}")


# ---------------------------------------------------------------------------
# API: Execute
# ---------------------------------------------------------------------------

@app.post("/api/execute")
async def api_execute(req: ExecuteRequest):
    """Execute action plan via executor.py.
    
    SAFETY: dry_run defaults to True. Agents/testing: NEVER set dry_run=False.
    """
    if not req.dry_run:
        logger.warning("[SECURITY] /api/execute called with dry_run=False — this will modify real files!")
    output_dir = os.path.expanduser(req.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Write plan to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir="/tmp", prefix="fo_plan_"
    ) as tmp:
        json.dump(req.action_plan, tmp, indent=2)
        plan_path = tmp.name

    # ARCH-001: Filter planner-only statuses — these NEVER reach the executor.
    # protected / blocked / unknown_review / conflict_review are PLANNING outcomes.
    planner_statuses = {"protected", "blocked", "unknown_review", "conflict_review"}
    executable_plan = [
        item for item in req.action_plan
        if item.get("status") not in planner_statuses
        and item.get("action") not in planner_statuses
    ]

    # Normalize plan to executor field names:
    # planner returns: action_type, src, dst, plan_id, ...
    # executor expects: action (not action_type), path (for delete/skip), src/dst (for move/copy/merge)
    normalized_plan = []
    for item in executable_plan:
        action = item.get("action_type") or item.get("action", "skip")

        if action == "delete":
            normalized_plan.append({
                "action": "delete",
                "path": item.get("src", item.get("path", "")),
                "plan_id": item.get("plan_id", ""),
                # SPRINT-9: action identity
                "action_id": item.get("action_id", ""),
                "src_identity": item.get("src_identity", {}) or {},
            })
        elif action == "skip":
            normalized_plan.append({
                "action": "skip",
                "path": item.get("src", item.get("path", "")),
                "plan_id": item.get("plan_id", ""),
                "action_id": item.get("action_id", ""),
                "src_identity": item.get("src_identity", {}) or {},
            })
        elif action in ("move", "copy", "merge"):
            normalized_plan.append({
                "action": action,
                "src": item.get("src", ""),
                "dst": item.get("dst", ""),
                "plan_id": item.get("plan_id", ""),
                "verify_checksum": item.get("verify_checksum", False),
                "conflict_mode": item.get("conflict_mode", "rename"),
                # SPRINT-9: action identity
                "action_id": item.get("action_id", ""),
                "src_identity": item.get("src_identity", {}) or {},
            })
        else:
            # Unknown action — skip it (shouldn't happen after status filter)
            continue

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(normalized_plan, f, indent=2)

    # Pre-flight: verify all source files exist before touching anything
    missing = []
    for item in normalized_plan:
        if item.get("action") in ("move", "delete"):
            src = item.get("src") or item.get("path", "")
            if not os.path.exists(src):
                missing.append(src)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Source files not found (deleted since scan?): {missing[:5]}"
        )

    cmd = [
        sys.executable, str(BASE_DIR / "executor.py"),
        "execute",
        "--plan", plan_path,
        "--output-dir", output_dir,
        "--on-conflict", req.on_conflict,
    ]
    if req.dry_run:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Execute timed out (600s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execute error: {e}")
    finally:
        try:
            os.unlink(plan_path)
        except OSError:
            pass

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Execute failed: {result.stderr or result.stdout}"
        )

    # Find the undo log
    undo_log = None
    out_path = Path(output_dir)
    undo_files = sorted(out_path.glob("undo_*.json"), reverse=True)
    if undo_files:
        undo_log = str(undo_files[0])

    # Parse summary from stdout
    stdout = result.stdout or ""
    completed = 0
    failed = 0
    already_done = 0
    stale = 0
    run_status = "unknown"
    for line in stdout.splitlines():
        if "[DONE]" in line:
            import re
            m = re.search(r"run_status=(\w+)", line)
            if m:
                run_status = m.group(1)
            m = re.search(r"ok=(\d+)", line)
            if m:
                completed = int(m.group(1))
            m = re.search(r"errors=(\d+)", line)
            if m:
                failed = int(m.group(1))
            m = re.search(r"already_done=(\d+)", line)
            if m:
                already_done = int(m.group(1))
            m = re.search(r"stale=(\d+)", line)
            if m:
                stale = int(m.group(1))

    return {
        "status": "ok",
        "undo_log": undo_log,
        "run_status": run_status,
        "completed": completed,
        "failed": failed,
        "already_done": already_done,
        "stale": stale,
        "stdout": stdout[-2000:],  # last 2kb of output
    }


# ---------------------------------------------------------------------------
# API: Multi-path scan (Sprint 3)
# ---------------------------------------------------------------------------

from typing import List

from scanner import build_cross_manifest, CrossPathDuplicateFinder, StructureAnalyzer
from planner import plan_from_manifest, RuleManager


class MultiPathScanRequest(BaseModel):
    paths: List[str]
    mode: str = "fast"
    include_hidden: bool = False
    exclude_dirs: Optional[List[str]] = None
    parent_folders: Optional[List[str]] = None


class PlanRequest(BaseModel):
    manifest: dict
    rules: Optional[list] = None
    rules_path: str = "rules.json"
    output_dir: str = "/tmp/file-organizer-output"
    parent_folders: Optional[List[str]] = None
    default_category: str = "Other"


class BoundaryRequest(BaseModel):
    action: str  # add | remove | list
    path: Optional[str] = None
    settings_path: str = "settings.json"


class RulesRequest(BaseModel):
    rules: list
    rules_path: str = "rules.json"


@app.post("/api/scan/multi")
async def scan_multi(req: MultiPathScanRequest):
    """Scan multiple specific paths. Returns full manifest with structure + duplicate analysis."""
    manifest = build_cross_manifest(
        paths=req.paths,
        mode=req.mode,
        include_hidden=req.include_hidden,
        exclude_dirs=req.exclude_dirs or [],
    )

    # Run duplicate detection
    finder = CrossPathDuplicateFinder(manifest["files"])
    dupes = finder.find()
    tier1 = dupes.get("tier1", [])
    tier2 = dupes.get("tier2", [])
    tier3 = dupes.get("tier3") or find_similar_duplicates(manifest["files"])

    # Run structure analysis
    analyzer = StructureAnalyzer(manifest, req.paths)
    structure = analyzer.analyze()

    # Unknown file summary
    unknown_files = [f for f in manifest["files"] if f.get("classification") in ("unknown", "system")]

    return {
        "manifest": manifest,
        "duplicates": tier1 + tier2 + tier3,
        "tier1": tier1,
        "tier2": tier2,
        "tier3": tier3,
        "total_groups": len(tier1) + len(tier2) + len(tier3),
        "structure": structure,
        "unknown_files": unknown_files[:100],
        "unknown_count": len(unknown_files),
        "is_empty": len(manifest["files"]) == 0,
    }


@app.post("/api/plan")
async def create_plan(req: PlanRequest):
    """Generate action plan from manifest + rules."""
    if req.rules is not None:
        from planner.rules import Rule
        rules = [Rule.from_dict(r) for r in list(req.rules)]
    else:
        rm = RuleManager(req.rules_path)
        rules = rm.rules

    plan = plan_from_manifest(
        manifest=req.manifest,
        rules=rules,
        default_output_dir=req.output_dir,
        parent_folders=req.parent_folders or [],
        default_category=req.default_category,
    )
    return plan


@app.get("/api/settings/parent-folders")
async def list_parent_folders(settings_path: str = "settings.json"):
    """Return current parent folder boundaries."""
    sp = Path(settings_path) if not Path(settings_path).is_absolute() else Path(settings_path)
    if not sp.exists():
        sp = BASE_DIR / settings_path
    if not sp.exists():
        return {"parent_folders": []}
    with open(sp) as f:
        settings = json.load(f)
    return {"parent_folders": settings.get("parent_folders", [])}


@app.post("/api/settings/parent-folders")
async def manage_parent_folders(req: BoundaryRequest):
    """Add or remove a parent folder boundary."""
    sp = Path(req.settings_path) if Path(req.settings_path).is_absolute() else BASE_DIR / req.settings_path
    if not sp.exists():
        settings: dict = {"parent_folders": []}
    else:
        with open(sp) as f:
            settings = json.load(f)

    if "parent_folders" not in settings:
        settings["parent_folders"] = []

    if req.action == "add" and req.path:
        if req.path not in settings["parent_folders"]:
            settings["parent_folders"].append(req.path)
        with open(sp, "w") as f:
            json.dump(settings, f, indent=2)
        return {"parent_folders": settings["parent_folders"], "added": req.path}

    elif req.action == "remove" and req.path:
        settings["parent_folders"] = [p for p in settings["parent_folders"] if p != req.path]
        with open(sp, "w") as f:
            json.dump(settings, f, indent=2)
        return {"parent_folders": settings["parent_folders"], "removed": req.path}

    elif req.action == "list":
        return {"parent_folders": settings.get("parent_folders", [])}

    raise HTTPException(status_code=400, detail="Invalid action. Use: add | remove | list")


# ---------------------------------------------------------------------------
# API: Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
async def api_get_settings():
    return load_settings()


@app.put("/api/settings")
async def api_put_settings(body: dict):
    save_settings(body)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# API: Mock Data Generator
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# API: Native OS Folder Picker (SA-001)
# ---------------------------------------------------------------------------

@app.post("/api/dialog/folder")
async def api_folder_picker(req: dict):
    """Open native OS folder dialog. Returns selected path or null.
    Uses kdialog on Linux/KDE, or falls back to Python input()."""
    import subprocess, shlex

    start_dir = os.path.expanduser(req.get("start_dir", os.path.expanduser("~")))

    # Try kdialog (KDE) first
    try:
        result = subprocess.run(
            ["kdialog", "--getexistingdirectory", start_dir, "--title", "Select Folder"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", "")}
        )
        if result.returncode == 0 and result.stdout.strip():
            path = result.stdout.strip()
            return {"ok": True, "path": path}
        # User cancelled
        return {"ok": False, "path": None}
    except FileNotFoundError:
        pass

    # Fallback: use zenity if available
    try:
        result = subprocess.run(
            ["zenity", "--file-selection", "--directory", "--filename", start_dir + "/"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"ok": True, "path": result.stdout.strip()}
        return {"ok": False, "path": None}
    except FileNotFoundError:
        pass

    return {"ok": False, "path": None, "error": "No native folder picker available (install kdialog or zenity)"}


# ---------------------------------------------------------------------------
# API: Mock Data Generator
# ---------------------------------------------------------------------------

@app.post("/api/mock/create")
async def api_mock_create(req: dict):
    """Generate mock test workspace. Body: {path: str, size_gb: int, categories: list[str]}"""
    categories = req.get("categories", [])
    # Generator requires int ≥ 1 — round floats to nearest int, min 1
    size_gb = max(1, round(req.get("size_gb", 10)))
    output_dir = os.path.expanduser(req.get("path", "~/test_workspace"))

    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "test_workspace_generator.py"),
         "--output", output_dir,
         "--size-gb", str(size_gb),
         "--categories", json.dumps(categories)],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise HTTPException(500, detail=result.stderr or "Generator failed")
    return {"ok": True, "output": result.stdout.strip()}


@app.post("/api/mock/delete")
async def api_mock_delete(req: dict):
    """Delete mock workspace. Body: {path: str}"""
    path = os.path.expanduser(req.get("path", ""))
    if not path:
        raise HTTPException(400, detail="path required")
    if not os.path.exists(path):
        return {"ok": True, "note": "already gone"}
    shutil.rmtree(path)
    return {"ok": True}


# ---------------------------------------------------------------------------
# API: Snapshot (pre-run + verification)
# ---------------------------------------------------------------------------

@app.post("/api/snapshot/create")
async def api_create_snapshot(req: dict):
    from planner.snapshot import create_snapshot
    snap_id = create_snapshot(req["manifest"], req["plan"], req.get("rules", []), req.get("profile_id"))
    return {"snapshot_id": snap_id}

@app.get("/api/snapshot/{snapshot_id}")
async def api_get_snapshot(snapshot_id: str):
    from planner.snapshot import get_snapshot
    snap = get_snapshot(snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    return snap

@app.post("/api/snapshot/{snapshot_id}/verify")
async def api_verify_snapshot(snapshot_id: str, req: dict):
    from planner.snapshot import verify_plan
    # Pass the plan if provided in the request body; otherwise verify_plan
    # will try to load it from the saved _plan.json file
    result = verify_plan(
        snapshot_id,
        req.get("after_manifest", {}),
        plan=req.get("plan"),
    )
    return result


# ---------------------------------------------------------------------------
# API: Open Folder (OS file manager)
# ---------------------------------------------------------------------------

@app.get("/api/open-folder")
async def api_open_folder(path: str):
    """Open the containing folder of the given path in the OS file manager.

    If path is a file: opens the parent directory.
    If path is a directory: opens that directory directly.
    Works even if the path doesn't exist (uses the parent).
    """
    if not path:
        raise HTTPException(400, detail="path query parameter required")

    file_path = os.path.expanduser(path)
    abs_path = os.path.abspath(file_path)

    # Always try to open the folder — even for non-existent paths.
    # If the path itself exists as a dir, open it directly.
    # Otherwise try to open its parent (covers non-existent files).
    if os.path.isdir(abs_path):
        folder = abs_path
    elif os.path.exists(abs_path) and (os.path.isfile(abs_path) or os.path.islink(abs_path)):
        folder = os.path.dirname(abs_path)
        if not folder:
            folder = abs_path
    else:
        # Path doesn't exist or is unknown type: open its parent directory
        folder = os.path.dirname(abs_path)
        if not folder:
            folder = abs_path

    folder = os.path.normpath(folder) or abs_path
    system = platform.system()

    try:
        if system == "Darwin":       # macOS
            subprocess.run(["open", folder], check=True, capture_output=True)
        elif system == "Windows":    # Windows
            subprocess.run(["explorer", folder], check=True, capture_output=True)
        elif system == "Linux":      # Linux — try common file managers
            managers = ["xdg-open", "nautilus", "dolphin", "thunar", "pcmanfm", "nemo"]
            opened = False
            for mgr in managers:
                try:
                    subprocess.run([mgr, folder], check=True, capture_output=True)
                    opened = True
                    break
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
            if not opened:
                # Last resort: xdg-open (should exist on any X desktop)
                subprocess.run(["xdg-open", folder], check=True, capture_output=True)
        else:
            raise HTTPException(400, detail=f"Unsupported OS: {system}")
    except FileNotFoundError:
        raise HTTPException(400, detail=f"No file manager found for path: {folder}")
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, detail=f"Failed to open folder: {e}")

    return {"ok": True, "folder": folder}


@app.post("/api/open-path")
async def api_open_path(body: dict):
    """Open the containing folder of a given path in the OS file manager.

    Accepts POST with JSON body {path: string}.
    Mirrors GET /api/open-folder but uses POST body for long path safety.
    """
    path = body.get("path", "")
    if not path:
        raise HTTPException(400, detail="path is required")

    file_path = os.path.expanduser(path)
    abs_path = os.path.abspath(file_path)

    if os.path.isdir(abs_path):
        folder = abs_path
    elif os.path.exists(abs_path) and (os.path.isfile(abs_path) or os.path.islink(abs_path)):
        folder = os.path.dirname(abs_path)
        if not folder:
            folder = abs_path
    else:
        folder = os.path.dirname(abs_path)
        if not folder:
            folder = abs_path

    folder = os.path.normpath(folder) or abs_path
    system = platform.system()

    try:
        if system == "Darwin":
            subprocess.run(["open", folder], check=True, capture_output=True)
        elif system == "Windows":
            subprocess.run(["explorer", folder], check=True, capture_output=True)
        elif system == "Linux":
            managers = ["xdg-open", "nautilus", "dolphin", "thunar", "pcmanfm", "nemo"]
            opened = False
            for mgr in managers:
                try:
                    subprocess.run([mgr, folder], check=True, capture_output=True)
                    opened = True
                    break
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
            if not opened:
                subprocess.run(["xdg-open", folder], check=True, capture_output=True)
        else:
            raise HTTPException(400, detail=f"Unsupported OS: {system}")
    except FileNotFoundError:
        raise HTTPException(400, detail=f"No file manager found for path: {folder}")
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, detail=f"Failed to open folder: {e}")

    return {"ok": True, "folder": folder}


# ---------------------------------------------------------------------------
# API: Project Detection
# ---------------------------------------------------------------------------

@app.post("/api/detect-projects")
async def api_detect_projects(req: dict):
    from scanner.project_detect import scan_for_project_roots
    paths = req.get("paths", [])
    include_hidden = req.get("include_hidden", False)
    projects = scan_for_project_roots(paths, include_hidden=include_hidden)
    return {"projects": [p.to_dict() for p in projects]}

# ---------------------------------------------------------------------------
# API: Run Configs (saved configurations)
# ---------------------------------------------------------------------------

@app.get("/api/configs")
async def api_list_configs():
    configs = []
    path = Path("data/run_configs.json")
    if path.exists():
        with open(path) as f:
            configs = json.load(f)
    return configs[-10:]  # last 10

@app.post("/api/configs")
async def api_save_config(req: dict):
    from datetime import datetime
    path = Path("data/run_configs.json")
    Path("data").mkdir(parents=True, exist_ok=True)
    configs = []
    if path.exists():
        with open(path) as f:
            configs = json.load(f)
    cfg = {
        "id": hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8],
        "created": datetime.now().isoformat(),
        "paths": req.get("paths", []),
        "profile_id": req.get("profile_id"),
        "intent_mode": req.get("intent_mode"),
        "scope_mode": req.get("scope_mode"),
        "dry_run": req.get("dry_run", True),
    }
    configs.append(cfg)
    with open(path, "w") as f:
        json.dump(configs[-20:], f, indent=2)  # keep last 20
    return cfg

# ---------------------------------------------------------------------------
# Static file serving (web UI)
# ---------------------------------------------------------------------------

if WEB_UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_UI_DIR)), name="static")


@app.get("/")
async def root():
    index = WEB_UI_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"status": "File Organizer API v3", "docs": "/docs"})


@app.get("/{path:path}")
async def serve_static(path: str):
    """Serve static files from web_ui/."""
    file_path = WEB_UI_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    # Fall back to index.html for SPA routing
    index = WEB_UI_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    raise HTTPException(status_code=404, detail="Not found")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=3001, reload=True)
