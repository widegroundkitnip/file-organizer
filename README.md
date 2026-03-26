# File Organizer & Deduper

A fast, local-first file intelligence platform. Scan, understand, deduplicate, organize, and get AI-powered suggestions on your file ecosystem.

**Status:** v1.0 — All sprints complete | [SPEC.md](SPEC.md) for full architecture

## Quick Start

```bash
pip3 install -r requirements.txt --break-system-packages
uvicorn app:app --host 0.0.0.0 --port 3001 --reload
# → http://localhost:3001
```

## What It Does

1. **Scan** — walk any directory, build a manifest with hashes, categories, and metadata
2. **Detect** — find duplicates (3 tiers), project roots, empty folders, unknown files
3. **Plan** — template-based rules generate an action plan with full conflict detection
4. **Preview** — visual before/after tree, see exactly what will change
5. **Execute** — safe moves with undo, checksum verification, crash recovery

---

## Architecture

```
scanner/          — Canonical scan engine
  manifest.py     — ManifestScanner, ExtendedManifestBuilder
  project_detect.py — Project root detection (confidence scoring)
  duplicate.py    — Tier 1/2/3 duplicate detection + keeper recommendation
  structure.py    — Path structure analysis
  exif.py         — EXIF metadata extraction

planner/          — Planning + rules engine
  engine.py       — plan_from_manifest, template parsing
  templates.py    — Template engine (fallback syntax, sanitization)
  rules.py        — RuleManager with profile support
  profiles.py     — 8 built-in goal-driven profiles
  learner.py      — Local deterministic pattern learner

executor/         — Execution engine
  executor.py     — Safe move/copy/delete with undo log
```

---

## Scan Engine

```bash
POST /api/scan
{
  "path": "/some/dir",
  "mode": "fast",          # fast = size+name, deep = full hash
  "include_hidden": false,
  "exclude_dirs": []
}
```

Returns: inline manifest with duplicates, structure analysis, detected project roots, empty/hidden folders.

### Manifest Schema (v2)

```json
{
  "scan_meta": {"path": "/some/dir", "mode": "fast", "schema_version": "2"},
  "files": [...],
  "detected_project_roots": [
    {
      "path": "/some/dir/.git",
      "confidence_label": "high",
      "confidence_score": 1.5,
      "markers": [".git", "package.json"],
      "recommended_handling": "protect_in_project_safe_mode"
    }
  ],
  "duplicate_groups": [
    {
      "group_id": 0,
      "tier": "definite",
      "keeper_recommendation": {"path": "...", "reason": "newest mtime + largest size"},
      "files": ["...a.jpg", "...b.jpg"]
    }
  ],
  "stats": {"total_files": 1234, "by_category": {...}}
}
```

---

## Duplicate Detection

| Tier | Meaning | Keeper Logic |
|------|---------|-------------|
| `definite` | Exact SHA256 hash match | User chooses at review |
| `likely` | Same filename + size | User chooses at review |
| `possible` | Similar name + size range | Informational only |

**Duplicate review workflow:** scan → review button → see keeper recommendation + reason + metadata → choose keeper → consolidate to trash.

---

## Project Detection

Automatically detects project roots using marker confidence scoring:

| Tier | Markers | Weight |
|------|---------|--------|
| Strong | `.git`, `Cargo.toml`, `go.mod`, `*.xcodeproj` | 1.5 |
| Medium | `package.json`, `pyproject.toml`, `requirements.txt` | 0.5 |
| Weak | `__pycache__`, `node_modules`, `.venv` | supporting only |

**Scope modes:**
- `project_safe_mode` — protect detected project roots
- `preserve_parent_boundaries` — no project protection (default)

---

## Profiles (8 Built-in)

| Profile | What It Does |
|---------|---------------|
| `general_organize` | Default rules for common file types |
| `downloads_cleanup` | Recent Downloads by type/age |
| `duplicates_review` | Cross-path duplicate scan |
| `screenshots` | By-month screenshot gatherer |
| `camera_import` | RAW + JPG + video, date-based naming |
| `project_safe` | Broad rules with project protection on |
| `mixed_sort` | Per-type by-month across all folders |
| `review_only` | Scan only, no rules fire |

---

## Template Engine

Full variable support with fallback syntax:

```
{taken_year|created_year|year|Unknown}
{name}.{ext}
{original_path}
{hash:8}
{counter:03}
{parent}
{size_bucket}
```

**Example:** `Images/{taken_year|Unknown}/{name}.{ext}`

**Features:**
- Filename sanitization (Windows-safe, reserved names, max 255 chars)
- Traversal risk detection (`../` blocked)
- Unknown variable warnings at save/preview
- strftime support: `{date:%Y-%m-%d}`

---

## Learner

Local deterministic pattern aggregator — no cloud, no API calls.

**How it works:**
- Logs approved actions from the preview/execute flow
- Aggregates patterns (extension → template, category → template)
- Suggests new rules when threshold met (≥5 actions, ≥80% consistency)
- User reviews, accepts or dismisses suggestions

**Suggestion schema:**
```json
{
  "type": "rule_suggestion",
  "title": "Create rule for JPG images",
  "support_count": 7,
  "consistency": 0.875,
  "confidence": 0.84,
  "examples": ["...photo1.jpg → Images/2026/photo1.jpg"],
  "proposed_rule": {"filter": {"type": "extension", "value": "jpg"}, ...}
}
```

---

## Execution Safety

- **Dry-run mode** — preview every action, no files touched
- **Checksum verification** — MD5 before/after every move
- **Undo log** — full transaction record, reversible
- **Trash** — no hard deletes, files go to `<output>/trash/YYYY-MM-DD_HHMMSS/`
- **Idempotency** — reruns skip already-done actions
- **Crash recovery** — transaction log survives partial completion
- **Pre-execute revalidation** — checks source exists, size matches, dest writable
- **Runtime conflict recheck** — destination exists, permissions unchanged at execution time

---

## API Endpoints

| Endpoint | Method | What |
|----------|--------|------|
| `/api/scan` | POST | Scan a path |
| `/api/scan/multi` | POST | Scan multiple paths |
| `/api/detect-projects` | POST | Detect project roots |
| `/api/manifest/{id}` | GET | Retrieve stored manifest |
| `/api/preview` | POST | Generate action plan |
| `/api/execute` | POST | Execute plan |
| `/api/undo/{run_id}` | POST | Undo a run |
| `/api/rules` | GET/PUT | Manage rules |
| `/api/profiles` | GET | List profiles |
| `/api/learner/suggestions` | GET | Get rule suggestions |
| `/api/learner/suggestions/accept` | POST | Accept suggestion |
| `/api/learner/suggestions/dismiss` | POST | Dismiss suggestion |
| `/api/duplicates/review` | POST | Duplicate review details |
| `/api/duplicates/execute-review` | POST | Execute duplicate consolidation |

---

## Extension Coverage

50+ formats supported out of the box:

**Images:** jpg, jpeg, png, gif, bmp, webp, svg, heic, dng, arw, cr2, nef, tiff, raw, avif, av1
**Video:** mp4, mov, avi, mkv, wmv, webm, m4v, mpeg, flv
**Audio:** mp3, wav, flac, aac, ogg, m4a, wma, alac
**Documents:** pdf, doc, docx, txt, rtf, odt, xls, xlsx, csv, ppt, pptx, epub, mobi
**Code:** py, js, ts, html, css, json, xml, yaml, md, ipynb, rs, rb, php, go, java, cpp, c, h, sh, sql
**Archives:** zip, tar, gz, rar, 7z, iso, dmg
**Other:** ico, pdf, ttf, otf, wasm

---

## File Structure

```
file-organizer/
├── app.py                    # FastAPI web app (port 3001)
├── executor.py               # Execution engine
├── organizer.py             # ⚠️ Deprecated — CLI reference only
├── scanner/
│   ├── manifest.py          # Canonical scan engine
│   ├── project_detect.py     # Project root detection
│   ├── duplicate.py          # Duplicate detection + keeper rec
│   ├── structure.py          # Structure analysis
│   ├── exif.py               # EXIF metadata extraction
│   └── utils.py             # Shared utilities
├── planner/
│   ├── engine.py            # plan_from_manifest
│   ├── templates.py          # Template engine
│   ├── rules.py              # RuleManager
│   ├── profiles.py           # Built-in profiles
│   ├── learner.py           # Pattern learner
│   └── snapshot.py           # Pre/post snapshots
├── web_ui/
│   ├── index.html            # Web UI
│   └── js/app.js            # Frontend JS
├── settings.json             # User settings
├── rules.json                # User rules
└── requirements.txt
```
