#!/usr/bin/env python3
"""
planner.py — Phase 3: Rule Engine
File Organizer & Deduper

Takes a manifest JSON + rules → action plan JSON.

Filter types:
  - extension: match by extension (values: list)
  - name_contains: match if filename contains substring (case-insensitive)
  - name_pattern: match by glob pattern (fnmatch)
  - size_gt: match if file size > N bytes
  - size_lt: match if file size < N bytes

Template variables:
  - {category}: Images/Documents/Videos/Audio/Code/Archives/Other
  - {subfolder}: user-defined subfolder
  - {name}: original filename without extension
  - {ext}: original extension (no dot)
  - {year}: file modified year (YYYY)
  - {month}: file modified month (MM)
  - {date}: file modified date (YYYY-MM-DD)
"""

from __future__ import annotations

import fnmatch
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Extension → Category map (mirrors organizer.py)
# ---------------------------------------------------------------------------

EXTENSION_MAP: dict[str, str] = {}
_RAW_MAP = {
    "Images":    "jpg jpeg png gif bmp tiff webp heic raw cr2 nef arw",
    "Videos":    "mp4 mov avi mkv wmv flv webm m4v",
    "Audio":     "mp3 wav flac aac ogg m4a wma",
    "Documents": "pdf doc docx xls xlsx ppt pptx odt ods",
    "Code":      "py js ts java cpp c h rs go rb php html css json yaml toml sh",
    "Archives":  "zip rar 7z tar gz bz2",
}
for _cat, _exts in _RAW_MAP.items():
    for _ext in _exts.split():
        EXTENSION_MAP[_ext.lower()] = _cat


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def load_manifest(path: str) -> dict:
    """Load and return manifest JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_rules(path: str) -> list[dict]:
    """Load rules from a JSON file (either a list directly, or {rules: [...]} shape)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "rules" in data:
        return data["rules"]
    return []


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------

def evaluate_rule(file: dict, rule: dict) -> bool:
    """
    Return True if file matches rule's filter.
    Supports: extension, name_contains, name_pattern, size_gt, size_lt
    """
    flt = rule.get("filter", {})
    ftype = flt.get("type", "")
    name = file.get("name", "")
    ext = file.get("ext", "").lower()
    size = file.get("size_bytes", 0)

    if ftype == "extension":
        values = [v.lower().lstrip(".") for v in flt.get("values", [])]
        return ext in values

    elif ftype == "name_contains":
        value = flt.get("value", "")
        return value.lower() in name.lower()

    elif ftype == "name_pattern":
        pattern = flt.get("value", "")
        return fnmatch.fnmatch(name.lower(), pattern.lower())

    elif ftype == "size_gt":
        threshold = flt.get("value", 0)
        return size > threshold

    elif ftype == "size_lt":
        threshold = flt.get("value", 0)
        return size < threshold

    return False


# ---------------------------------------------------------------------------
# Template expansion
# ---------------------------------------------------------------------------

def apply_template(
    template: str,
    file: dict,
    category: str,
    subfolder: str,
) -> str:
    """
    Expand destination template string with file metadata.
    """
    name_no_ext = Path(file.get("name", "")).stem
    ext = file.get("ext", "")

    # Parse modified timestamp
    modified_ts = file.get("modified_ts")
    year = month = date = ""
    if modified_ts:
        try:
            dt = datetime.fromisoformat(modified_ts.replace("Z", "+00:00"))
            year = dt.strftime("%Y")
            month = dt.strftime("%m")
            date = dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass

    result = template
    result = result.replace("{category}", category)
    result = result.replace("{subfolder}", subfolder)
    result = result.replace("{name}", name_no_ext)
    result = result.replace("{ext}", ext)
    result = result.replace("{year}", year)
    result = result.replace("{month}", month)
    result = result.replace("{date}", date)
    return result


# ---------------------------------------------------------------------------
# Core planner
# ---------------------------------------------------------------------------

def plan_from_manifest(
    manifest: dict,
    rules: list[dict],
    default_output_dir: str,
) -> list[dict]:
    """
    Generate action plan from manifest + rules.

    Logic:
    - For each file, evaluate rules in ORDER (first match wins)
    - If no rule matches → action: "skip"
    - Duplicate groups: first file → "skip" (keep), rest → "delete"
    - Returns list of action plan items
    """
    files = manifest.get("files", [])
    duplicate_groups = manifest.get("duplicate_groups", [])

    # Build set of paths that are duplicates, and which to keep
    # key: path → "keep" | "delete"
    dup_resolution: dict[str, str] = {}
    for group in duplicate_groups:
        group_files = group.get("files", [])
        if not group_files:
            continue
        # Keep first, delete rest
        for i, path in enumerate(group_files):
            if i == 0:
                dup_resolution[path] = "keep"
            else:
                dup_resolution[path] = "delete"

    plan: list[dict] = []

    for file in files:
        src = file.get("path", "")

        # Duplicate resolution takes priority
        dup_status = dup_resolution.get(src)
        if dup_status == "delete":
            plan.append({
                "action": "delete",
                "src": src,
                "dst": "",
                "rule_matched": "_duplicate_resolution",
                "status": "pending",
                "conflict_mode": "rename",
            })
            continue

        # Try each rule in order
        matched_rule = None
        for rule in rules:
            if not rule.get("enabled", True):
                continue
            if evaluate_rule(file, rule):
                matched_rule = rule
                break

        if matched_rule is None:
            # No rule matched — skip
            plan.append({
                "action": "skip",
                "src": src,
                "dst": "",
                "rule_matched": None,
                "status": "pending",
                "conflict_mode": "rename",
            })
            continue

        # Build destination path
        category = matched_rule.get("category", EXTENSION_MAP.get(file.get("ext", ""), "Other"))
        subfolder = matched_rule.get("subfolder", "")
        template = matched_rule.get(
            "destination_template",
            "{category}/{subfolder}/{name}.{ext}" if subfolder else "{category}/{name}.{ext}"
        )
        conflict_mode = matched_rule.get("conflict_mode", "rename")

        rel_dst = apply_template(template, file, category, subfolder)

        # Clean up double slashes from empty subfolder
        while "//" in rel_dst:
            rel_dst = rel_dst.replace("//", "/")
        rel_dst = rel_dst.strip("/")

        abs_dst = os.path.join(default_output_dir, rel_dst)

        plan.append({
            "action": "move",
            "src": src,
            "dst": abs_dst,
            "rule_matched": matched_rule.get("name", "unnamed"),
            "status": "pending",
            "conflict_mode": conflict_mode,
        })

    return plan


# ---------------------------------------------------------------------------
# CLI (optional — for testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: planner.py <manifest.json> <rules.json|settings.json> <output_dir>")
        sys.exit(1)

    manifest_path = sys.argv[1]
    rules_path = sys.argv[2]
    output_dir = sys.argv[3]

    manifest = load_manifest(manifest_path)
    rules = load_rules(rules_path)
    plan = plan_from_manifest(manifest, rules, output_dir)

    print(json.dumps(plan, indent=2))
    print(f"\n# Total: {len(plan)}", file=sys.stderr)
    moves = sum(1 for p in plan if p["action"] == "move")
    deletes = sum(1 for p in plan if p["action"] == "delete")
    skips = sum(1 for p in plan if p["action"] == "skip")
    print(f"# Moves: {moves}, Deletes: {deletes}, Skips: {skips}", file=sys.stderr)
