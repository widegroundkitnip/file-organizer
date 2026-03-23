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

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List

# Phase 3 extended modules
from scanner import build_cross_manifest, CrossPathDuplicateFinder, StructureAnalyzer
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
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


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


class RulesUpdate(BaseModel):
    rules: list[dict]


class PreviewRequest(BaseModel):
    manifest_path: str
    rules: list[dict]


class ExecuteRequest(BaseModel):
    action_plan: list[dict]
    output_dir: str
    dry_run: bool = False
    on_conflict: str = "rename"


class SettingsUpdate(BaseModel):
    # Accept any dict
    class Config:
        extra = "allow"


# ---------------------------------------------------------------------------
# API: Scan
# ---------------------------------------------------------------------------

@app.post("/api/scan")
async def api_scan(req: ScanRequest):
    """Run organizer.py scan via subprocess."""
    path = os.path.expanduser(req.path)
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    timestamp_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    manifest_filename = f"scan_{timestamp_str}.json"
    manifest_path = str(SCANS_DIR / manifest_filename)

    cmd = [
        sys.executable, str(BASE_DIR / "organizer.py"),
        "--path", path,
        "--mode", req.mode,
        "--output-dir", str(SCANS_DIR),
    ]
    if req.include_hidden:
        cmd.append("--include-hidden")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Scan timed out (300s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan error: {e}")

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Scan failed: {result.stderr or result.stdout}"
        )

    # Find the actual output file (organizer.py uses timestamp in filename)
    scan_files = sorted(SCANS_DIR.glob("scan_*.json"))
    if not scan_files:
        raise HTTPException(status_code=500, detail="Scan produced no manifest")
    latest = scan_files[-1]

    # Read total_files from manifest
    try:
        with open(latest, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        total_files = manifest.get("scan_meta", {}).get("total_files", 0)
    except Exception:
        total_files = 0

    return {
        "status": "ok",
        "manifest_path": str(latest),
        "manifest_id": latest.stem,  # e.g. scan_2024-01-15_120000
        "total_files": total_files,
    }


# ---------------------------------------------------------------------------
# API: Manifest
# ---------------------------------------------------------------------------

@app.get("/api/manifest/{manifest_id}")
async def api_get_manifest(manifest_id: str):
    """Return manifest JSON for a given scan id."""
    # manifest_id is the stem, e.g. scan_2024-01-15_120000
    manifest_path = SCANS_DIR / f"{manifest_id}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Manifest not found: {manifest_id}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/scans")
async def api_list_scans():
    """List all scan manifests."""
    scans = []
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
            })
        except Exception:
            continue
    return scans


# ---------------------------------------------------------------------------
# API: Rules
# ---------------------------------------------------------------------------

@app.get("/api/rules")
async def api_get_rules():
    settings = load_settings()
    return {"rules": settings.get("rules", [])}


@app.put("/api/rules")
async def api_put_rules(body: RulesUpdate):
    settings = load_settings()
    settings["rules"] = body.rules
    save_settings(settings)
    return {"status": "ok", "rules": body.rules}


# ---------------------------------------------------------------------------
# API: Preview (planner)
# ---------------------------------------------------------------------------

@app.post("/api/preview")
async def api_preview(req: PreviewRequest):
    """Generate action plan from manifest + rules via planner.plan_from_manifest()."""
    # Import planner directly (same process)
    try:
        from planner import load_manifest, plan_from_manifest
    except ImportError:
        raise HTTPException(status_code=500, detail="planner.py not found")

    if not os.path.exists(req.manifest_path):
        raise HTTPException(status_code=404, detail=f"Manifest not found: {req.manifest_path}")

    settings = load_settings()
    output_dir = settings.get("base_output_dir", "/tmp/file-organizer-output")

    try:
        manifest = load_manifest(req.manifest_path)
        plan = plan_from_manifest(manifest, req.rules, output_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planner error: {e}")

    stats = {
        "total": len(plan),
        "to_move": sum(1 for a in plan if a["action"] == "move"),
        "to_delete": sum(1 for a in plan if a["action"] == "delete"),
        "to_skip": sum(1 for a in plan if a["action"] == "skip"),
    }

    return {"actions": plan, "stats": stats}


# ---------------------------------------------------------------------------
# API: Execute
# ---------------------------------------------------------------------------

@app.post("/api/execute")
async def api_execute(req: ExecuteRequest):
    """Execute action plan via executor.py."""
    output_dir = os.path.expanduser(req.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Write plan to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir="/tmp", prefix="fo_plan_"
    ) as tmp:
        json.dump(req.action_plan, tmp, indent=2)
        plan_path = tmp.name

    # Map action plan items to executor's expected format:
    # executor expects "delete" items to have "path" key, not "src"
    normalized_plan = []
    for item in req.action_plan:
        if item["action"] == "delete":
            normalized_plan.append({
                "action": "delete",
                "path": item.get("src", item.get("path", "")),
            })
        elif item["action"] == "skip":
            normalized_plan.append({
                "action": "skip",
                "path": item.get("src", item.get("path", "")),
            })
        else:
            normalized_plan.append(item)

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(normalized_plan, f, indent=2)

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
    for line in stdout.splitlines():
        if "[DONE]" in line:
            import re
            m = re.search(r"ok=(\d+)", line)
            if m:
                completed = int(m.group(1))
            m = re.search(r"errors=(\d+)", line)
            if m:
                failed = int(m.group(1))

    return {
        "status": "ok",
        "undo_log": undo_log,
        "completed": completed,
        "failed": failed,
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

    # Run structure analysis
    analyzer = StructureAnalyzer(manifest, req.paths)
    structure = analyzer.analyze()

    # Unknown file summary
    unknown_files = [f for f in manifest["files"] if f.get("classification") in ("unknown", "system")]

    return {
        "manifest": manifest,
        "duplicates": dupes,
        "structure": structure,
        "unknown_files": unknown_files[:100],
        "unknown_count": len(unknown_files),
    }


@app.post("/api/plan")
async def create_plan(req: PlanRequest):
    """Generate action plan from manifest + rules."""
    if req.rules is not None:
        from planner.rules import Rule, FilterCondition
        rules = []
        for r in list(req.rules):
            r = dict(r)
            if r.get("filter"):
                r["filter"] = FilterCondition(**r["filter"])
            rules.append(Rule(**r))
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


@app.get("/api/rules")
async def get_rules(rules_path: str = "rules.json"):
    """Return current rules."""
    rp = Path(rules_path) if Path(rules_path).is_absolute() else BASE_DIR / rules_path
    rm = RuleManager(str(rp))
    return {"rules": [r.to_dict() for r in rm.rules]}


@app.post("/api/rules")
async def save_rules(req: RulesRequest):
    """Save rules."""
    from planner.rules import Rule, FilterCondition
    rules = []
    for r in req.rules:
        r = dict(r)
        if r.get("filter"):
            r["filter"] = FilterCondition(**r["filter"])
        rules.append(Rule(**r))
    rp = Path(req.rules_path) if Path(req.rules_path).is_absolute() else BASE_DIR / req.rules_path
    rm = RuleManager(str(rp))
    rm.rules = rules
    rm.save()
    return {"rules": [r.to_dict() for r in rm.rules]}


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
# Phase 3 extended endpoints
# ---------------------------------------------------------------------------

@app.post("/api/plan")
async def create_plan(req: PlanRequest):
    """Generate action plan from manifest + rules with boundary + unknown guards."""
    try:
        if req.rules is not None:
            from planner.rules import Rule, FilterCondition
            rules = []
            for r in req.rules:
                d = dict(r)
                if d.get("filter"):
                    d["filter"] = FilterCondition(**d["filter"])
                rules.append(Rule(**d))
        else:
            rm = RuleManager()
            rules = rm.rules
        return plan_from_manifest(
            manifest=req.manifest,
            rules=rules,
            default_output_dir=req.output_dir,
            parent_folders=req.parent_folders or [],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/parent-folders")
async def list_parent_folders():
    settings = load_settings()
    return {"parent_folders": settings.get("parent_folders", [])}


@app.post("/api/settings/parent-folders")
async def manage_parent_folders(req: BoundaryRequest):
    settings = load_settings()
    if "parent_folders" not in settings:
        settings["parent_folders"] = []

    if req.action == "add" and req.path:
        if req.path not in settings["parent_folders"]:
            settings["parent_folders"].append(req.path)
        save_settings(settings)
        return {"parent_folders": settings["parent_folders"], "added": req.path}
    elif req.action == "remove" and req.path:
        settings["parent_folders"] = [p for p in settings["parent_folders"] if p != req.path]
        save_settings(settings)
        return {"parent_folders": settings["parent_folders"], "removed": req.path}
    elif req.action == "list":
        return {"parent_folders": settings.get("parent_folders", [])}
    raise HTTPException(status_code=400, detail="Invalid action. Use: add | remove | list")

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
