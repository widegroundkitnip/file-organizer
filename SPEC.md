# File Organizer & Deduper — Product Specification
**Version 3.1** | **2026-03-23**
**Phase 3.1 + v2 Vision**

---

## Implemented

### Architecture
- `organizer.py` — Phase 1 scan engine
- `executor.py` — Phase 2 execution engine
- `planner/` — Phase 3 rule engine (`engine.py`, `templates.py`, `rules.py`)
- `scanner/` — Phase 3 cross-path scan engine (`manifest.py`, `duplicate.py`, `structure.py`)
- `app.py` — FastAPI web app (Phase 3)
- `web_ui/` — Web frontend (vanilla JS SPA)
- `settings.json` — User settings persistence
- `rules.json` — Rule definitions persistence

### File Type Classification ✓
Every file is classified as **Known**, **Unknown**, or **System**.
- **Known** files: recognized extension → subject to normal rules and auto-actions
- **Unknown** files: no extension or unrecognised → never auto-moved/deleted, surfaced for review
- **System** files: `.pyc`, `.DS_Store`, `.lock`, `.tmp` etc. → protected

### Unknown File Behavior ✓
- Never included in auto-action plans
- Listed in "Unknown" page of UI
- Keep/Delete buttons per file (approve → Unknown/Approved, reject → Trash)
- Preview shows "⚠ Unknown" badge on unknown files

### Parent Folder Boundaries ✓
- Folders can be marked as boundaries (stored in `settings.json`)
- Cross-boundary moves/deletes are blocked with `blocked_boundary` status
- Visual lock indicator in UI

### Duplicate Detection ✓ (Tiers 1–3)
- **Tier 1** (Exact): SHA256 hash match
- **Tier 2** (Likely): same filename + size
- **Tier 3** (Similar): same extension + Levenshtein name proximity
- Cross-path duplicate detection via `scanner/duplicate.py`

### Rule Engine (`planner/`) ✓
- Filter condition types: `extension`, `name_contains`, `name_pattern`, `path_contains`, `size_gt`, `size_lt`, `modified_after/before`, `created_after/before`, `modified_within_days`, `all_of`, `any_of`, `none_of`, `no_extension`, `duplicate`, `default`
- Destination templates: `{category}`, `{name}`, `{ext}`, `{year}`, `{month}`, `{day}`, `{parent}`, `{tree}`, `{depth}`, `{size_human}`
- First-matching-rule-wins priority ordering
- Conflict modes: `rename` (default), `skip`, `overwrite`

### Structure Analyzer (`scanner/structure.py`) ✓ (basic)
- Folder depth, file count, total size statistics
- Issue detection: deep nesting, large singular dirs, venv detection

### Web UI Pages ✓
1. **Scan** — Select folder(s), mode, include/exclude
2. **Results** — File tree, categories, duplicate groups
3. **Rules** — Rule builder with filter type/value editor
4. **Preview** — Action plan review with filter bar, select all/none, bulk actions; **rule name + match reason shown per file**
5. **Execute** — Progress, live feed, dry-run, undo
6. **Cross-Path Scan** — Multi-folder selection, duplicate groups by tier
7. **Structure** — Folder tree with issue markers
8. **Unknown** — Unknown file list with **Keep/Delete** approve/reject buttons
9. **Settings** — Output dir, conflict mode, protected folders, theme colours

### API Endpoints ✓
- `POST /api/scan` — single folder scan
- `POST /api/scan/multi` — cross-path scan
- `GET /api/manifest/{id}` — load manifest
- `GET /api/scans` — list scans
- `POST /api/plan` — generate action plan (returns `rule_name`, `rule_match_reason`)
- `POST /api/preview` — build preview
- `POST /api/execute` — execute plan (dry-run by default)
- `GET/PUT /api/rules` — load/save rules
- `GET/PUT /api/settings` — load/save settings
- `GET/POST /api/settings/parent-folders` — boundary management

### Output Modes ✓
- **Separate output directory** (default): files copied/moved to new base path
- **Dry-run by default**: execution never auto-modifies files without explicit opt-in

### Theme / UI
- CSS custom properties for colours
- Dark theme default
- Responsive single-page layout

---

## Planned (Phase v2 / v3+)

### Boundary Behavior Matrix UI
- Visual crossing-warning cards in Preview when an action would cross a boundary
- "Blocked Actions" section on Execute page

### Tier 4 — Semantic Duplicate Detection (AI)
- Perceptual hash (pHash) for image similarity
- Embedding similarity for text/code files (local LLM or TF-IDF fallback)
- Requires `ai/` module

### AI Layer (`ai/`) — Phase v2
- **Rule Learner**: observes approved actions → suggests new rules
- **Structure Analyzer**: identifies deep chains, redundant nesting, inconsistent naming
- **Duplicate Summarizer**: groups duplicates by origin, estimates space savings
- **Auto-Organizer**: "organize my Downloads by month and type" → generates rules
- **Image Comparator**: pHash + CNN feature similarity, visual diff map
- **File Semantic Comparer**: embedding/TF-IDF similarity for text and code
- AI provider UI: API key input, OAuth flows for OpenAI/Anthropic/Google, local Ollama/LM Studio support

### Output Mode 3 — Ask Per Folder (Hybrid)
- User selects specific parent folders each with own output configuration
- Prompt: "What do you want to do with Prospero/Mplug?"

### Enhanced Structure Analyzer
- `similar_subtrees` detection: two subtrees with >50% file overlap
- `empty_dir`, `hidden_heavy` issue types
- Recommendations panel with estimated impact

### Enhanced UI Pages
- **Page 2b: Structure Analysis** — visual tree map, severity highlights, drill-down, "Apply AI Suggestions"
- **Page 2c: Cross-Path Scan** — matrix view of folder overlaps, shared subpath browser
- **Page 2d: Duplicate Browser (Enhanced)** — group view with tier filter, bulk actions, "Keep Earliest/Latest/Tree:X" shortcuts

### Settings Schema — Full Implementation
- `scan.large_file_threshold_mb`
- `scan.hash_cache_enabled`, `scan.hash_cache_dir`
- `scan.follow_symlinks`
- `scan.exclude_known_system`
- `scan.unknown_file_policy`
- `structure.max_depth_warning`, `structure.large_dir_warning`
- `structure.detect_similar_subtrees`, `structure.similarity_threshold`
- Full `categories` subfolder mapping
- `ai.*` settings block

### Organizational Memory
- Learns user preferences over time from approved actions
- Stores persistent rule suggestions

### Plugin System
- Custom analyzers, custom destinations, third-party integrations

### Streaming JSON for Large Scans
- 663K files at 4KB avg = ~2.6GB manifest — streaming parse for very large scans

### Cross-Platform Path Handling
- Windows `\` path normalization before filesystem operations

### Collaborative Rules Sharing
- Export/import rules as shareable JSON bundles

---

## Overview

A local-first, AI-ready file intelligence platform. Not just a deduper — a tool that understands your file ecosystem, finds value in chaos, and helps you organize without destroying what matters.

**Core philosophy:** User is always in control. AI suggests, human decides. Local only. Open source.

---

## Drive Profile Used for Spec (Sigge's Halmstad Högskola Drive)
- **663,175 files** across a deeply nested research/ML workspace
- Top file types: `.jpg` (269K), `.txt` (244K), `.py` (20K), `.wav` (19K), `.pyc` (15K), `.pdf` (3.8K), `.md` (2.5K)
- Key patterns: Cloned repos with `.venv`, `__pycache__`, COCO annotation sets, ML model weights, audio datasets, research course materials
- Use case: Cross-repo duplicate detection, dataset cleanup, structure analysis

---

## Architecture

```
file_organizer/
├── organizer.py          # Phase 1 scan engine (done)
├── executor.py         # Phase 2 execution engine (done)
├── planner.py          # Phase 3 rule engine
├── app.py              # FastAPI web app
├── settings.json       # User settings
├── web_ui/             # Web frontend
│
├── scanner/            # Phase 3: Cross-path scan engine
│   ├── __init__.py
│   ├── manifest.py    # Extended manifest builder (includes subpath mapping)
│   ├── duplicate.py   # Cross-path duplicate detection
│   └── structure.py   # Folder structure analyzer
│
├── planner/            # Phase 3: Rule-based planner
│   ├── __init__.py
│   ├── engine.py      # Main planner logic
│   ├── templates.py   # Destination template system
│   └── rules.py       # Rule definitions + persistence
│
├── ai/                 # Phase v2: AI layer (stubbed in Phase 3)
│   ├── __init__.py
│   ├── interface.py   # AI module interface / protocol
│   ├── rule_learner.py
│   ├── structure_analyzer.py
│   ├── duplicate_summarizer.py
│   ├── auto_organizer.py
│   ├── image_comparator.py
│   └── file_semantic.py
│
├── ui/                 # Phase 3 UI components
│   ├── structure_view.py
│   ├── cross_path_scan.py
│   └── duplicate_browser.py
│
├── settings.json       # Full settings
└── data/               # Sample data
    ├── drive_index.json
    └── drive_files.json
```

---

## File Type Classification

### Classification Rules

Every file is classified into exactly one category:

| Category | Rule |
|----------|------|
| Known | Has a recognized extension AND matches a known type |
| Unknown | No extension, OR extension not recognized |
| System | Extension indicates system artifact (`.pyc`, `.DS_Store`, `.lock`, `.tmp`) |

**Known files:** Subject to normal rules and auto-actions.

**Unknown files:** Never auto-moved, auto-renamed, or auto-deleted. Always surfaced for explicit user decision.

Examples of "unknown" and what the system might suggest:

| File pattern | Likely type | System suggestion |
|---|---|---|
| `94884092518704` (no ext, large, in `archive/data/`) | Dataset shard / ML artifact | "Likely downloaded cache — confirm before any action" |
| `config` (no ext, no size, in repo root) | Git submodule marker or config | "Dotfile or system config — keep untouched" |
| `FEDCBA9876543210` (hex, no ext, small) | Session token, lock file, or crash dump | "System artifact — verify before deletion" |
| `somefile.tar` (has name, no extension but known container name) | Archive with missing extension | "Archive may be missing extension — open to inspect before action" |

### Unknown File Behavior

```
UNKNOWN_FILE_RULE:
  - Never include in auto-action plans
  - Always list in "Review Required" section of preview
  - Visual badge: "⚠ Unknown" in UI
  - Destructive actions blocked by default
  - User must explicitly approve each unknown file action
```

### Folder Deletion Rules

```
FOLDER_DELETION_GUARD:
  before_delete_folder(path):
    files = list_all_files(path, recursive=True)
    unknown_files = [f for f in files if f.category == UNKNOWN]
    known_deletable = [f for f in files if f.category == KNOWN and f.marked_for_deletion]
    
    if known_deletable == all files in folder AND unknown_files == []:
      → DELETE folder (safe, all contents are known and marked)
    
    elif unknown_files > 0 AND known_deletable == all known files:
      → BLOCK automatic deletion
      → Surface to user: "This folder contains X unknown files. Cannot delete automatically."
    
    else:
      → BLOCK automatic deletion
      → Surface: "This folder has mixed contents. Review manually."
```

---

## Parent Folder Boundaries

### Concept
Any folder can be marked as a **parent folder boundary** — a hard operational stop. No action (move, delete, rename) can cross this boundary without explicit user approval.

### Use Case
```
Filmmaking/
├── Projects/
│   ├── Project_A/    ← marked as parent boundary
│   └── Project_B/    ← marked as parent boundary
```

### Marking a Parent Folder
- User right-clicks any folder in scan results → "Mark as Parent Boundary"
- Stored in settings as an array of absolute paths
- Persists across scans
- Visual indicator in UI: 🔒 icon

### Boundary Behavior Matrix

| Action | Boundary: inside | Boundary: ancestor of target |
|--------|-----------------|------------------------------|
| Move file into boundary | ⚠️ Blocked (requires explicit approval) | ✅ Allowed |
| Move file out of boundary | ⚠️ Blocked | ✅ Allowed |
| Delete folder inside boundary | ⚠️ Blocked | ✅ Allowed |
| Restructure ancestor of boundary | ✅ Allowed | N/A |
| Analyze subtree under boundary | ✅ Allowed | N/A |

### Conflict Detection
```
PARENT_BOUNDARY_CHECK:
  before_execute_action(action):
    if action crosses parent_boundary:
      → BLOCK action
      → Add to blocked_actions list
      → Surface: "This action would affect parent boundary at /path/Boundary"

PARENT_BOUNDARY_CROSS_CONFLICT:
  before_execution_plan_submit(plan):
    conflicts = [a for a in plan if a.touches_parent_boundary]
    if conflicts:
      → ABORT submission
      → Surface all conflicts to user
      → Require user to: [Remove conflicting actions] or [Unmark boundary] or [Cancel]
```

### UI Presentation
- Locked folders shown with 🔒 in scan results
- Crossing a boundary → orange warning card in preview
- Execute page: "Blocked Actions" section (0 items = clean to run)

---

## Duplicate Detection Modes

### Tier 1 — Exact (SHA256)
- Identical files by hash
- Already implemented in Phase 1.5

### Tier 2 — Likely (size + name)
- Same filename + same size
- Different or null hash
- Already implemented in Phase 1

### Tier 3 — Similar (filename + size proximity)
- Same extension, similar filename (Levenshtein distance threshold)
- Same rough size range
- User-configurable sensitivity

### Tier 4 — Semantic (AI)
- Files with different names but similar/related content
- Enabled via AI layer (Phase v2)
- Stub in Phase 3, implemented in v2

---

## Cross-Path Scan Module (`scanner/`)

### Purpose
Scan multiple specific subtrees and detect cross-duplicates between them.

### Usage
```python
from scanner.manifest import build_cross_manifest
from scanner.duplicate import find_cross_duplicates

# Scan two specific subtrees
paths = [
    "/path/to/AliceMind/StructBERT",
    "/path/to/mPLUG/StructBERT",
]
manifest = build_cross_manifest(paths, mode="deep")
duplicates = find_cross_duplicates(manifest)
```

### Manifest Schema (Extended)
```json
{
  "scan_id": "uuid",
  "paths_scanned": ["/path/A", "/path/B"],
  "scan_mode": "deep",
  "files": [
    {
      "path": "/path/to/file.jpg",
      "relative_path": "StructBERT/config/file.jpg",
      "parent_tree": "AliceMind",
      "size": 4096,
      "modified": "ISO8601",
      "extension": "jpg",
      "hash": "sha256:...",
      "prefix_hash": "xxhash:...",
      "is_symlink": false,
      "category": "Images"
    }
  ],
  "duplicate_groups": [
    {
      "group_id": "uuid",
      "tier": "exact|likely|similar|semantic",
      "files": ["path1", "path2"],
      "shared_subpath": "StructBERT/config",
      "trees": ["AliceMind", "mPLUG"]
    }
  ]
}
```

### Cross-Duplicate Detection Logic
1. Group all files by their relative subpath (path relative to scan root)
2. Files with identical relative paths across different scan roots → Tier 1 duplicate group
3. Files with same basename and size but different subpath → Tier 2
4. Apply Tier 3 / Tier 4 as configured

---

## Structure Analyzer (`scanner/structure.py`)

### Purpose
Profile a directory tree and report structural issues.

### Structure Report Schema
```json
{
  "scan_root": "/path/to/Halmstad Högskola",
  "stats": {
    "total_files": 663175,
    "total_dirs": 12400,
    "max_depth": 12,
    "avg_depth": 6.2,
    "total_size_bytes": 0
  },
  "issues": [
    {
      "type": "deep_nesting",
      "severity": "warning",
      "path": "/Prospero/Models & Datasets/Mplug/Cloned Resp/...",
      "depth": 12,
      "message": "12 levels deep — consider flattening"
    },
    {
      "type": "single_child_dir",
      "severity": "info",
      "path": "/Courses/7_Principles.../Python Projects/.venv/lib/python3.11/site-packages/...",
      "message": "Single subfolder chain 8 deep with no branching"
    },
    {
      "type": "large_singular_file_dir",
      "severity": "info",
      "path": "/Models & Datasets/Mplug/archive/data",
      "file_count": 1000,
      "message": "1000 files in single directory, no subfolders"
    },
    {
      "type": "similar_subtrees",
      "severity": "info",
      "path_a": "/Models & Datasets/Mplug/Cloned Resp/AliceMind",
      "path_b": "/Models & Datasets/Mplug/Cloned Resp/mPLUG",
      "similarity": 0.73,
      "message": "73% file overlap between AliceMind and mPLUG — shared dependencies"
    },
    {
      "type": "venv_detected",
      "severity": "info",
      "paths": ["/Prospero/.venv", "/Courses/.../.venv"],
      "count": 8,
      "message": "8 Python virtual environments detected — .venv folders are isolated"
    }
  ],
  "recommendations": [
    {
      "action": "consider_git_submodule",
      "reason": "AliceMind and mPLUG share large dependency trees",
      "savings_estimate": "~2GB if deduplicated via submodules"
    }
  ]
}
```

### Structural Issue Types
- `deep_nesting`: depth > threshold (configurable, default 8)
- `single_child_chain`: directory with only one subdirectory, repeated
- `large_singular_dir`: directory with >500 files, no subfolders
- `similar_subtrees`: two subtrees with >50% file overlap (by relative path)
- `venv_detected`: Python virtual environments
- `empty_dir`: empty directory
- `hidden_heavy`: directory with >50 hidden files

---

## Rule Engine (`planner/`)

### Rule Schema
```json
{
  "id": "uuid",
  "name": "ML Config Files → Structured",
  "enabled": true,
  "priority": 1,
  "filter": {
    "type": "all_of",
    "conditions": [
      {"type": "extension", "values": ["yaml", "yml", "json", "toml"]},
      {"type": "path_contains", "value": "config"}
    ]
  },
  "destination": {
    "type": "template",
    "template": "{category}/ML/Configs/{name}.{ext}",
    "conflict_mode": "rename"
  },
  "tags": ["ml", "config"]
}
```

### Filter Condition Types
- `extension`: file extension in list
- `name_contains`: substring match (case-insensitive)
- `name_pattern`: glob pattern (fnmatch)
- `path_contains`: path segment substring match
- `path_starts_with`: path starts with given prefix
- `size_gt` / `size_lt`: file size comparison
- `modified_before` / `modified_after`: date comparison
- `has_exif` / `has_dominant_color`: metadata conditions
- `all_of` / `any_of` / `none_of`: logical combinations

### Destination Template Variables
- `{category}` — Images / Documents / Video / Audio / Code / Archives / Other
- `{subcategory}` — user-defined subcategory
- `{name}` — filename without extension
- `{ext}` — extension (no dot)
- `{year}` / `{month}` / `{day}` — from file modified date
- `{parent}` — immediate parent directory name
- `{tree}` — root scan tree name (when cross-scanning)
- `{depth}` — nesting depth of file
- `{size_human}` — human-readable size (e.g. "4.2MB")

### Rule Priority
- Rules are ordered by user (drag-to-reorder in UI)
- First matching rule wins
- Unmatched files → `skipped` action (user reviews)

---

## AI Layer (`ai/`) — Phase v2

### Interface Protocol
```python
class AICategorizer(Protocol):
    async def categorize_file(self, file_path: str, content_hint: str) -> str:
        """Return category suggestion"""
    async def suggest_rules(self, manifest: Manifest) -> list[Rule]:
        """Return suggested rules based on observed patterns"""
    async def summarize_duplicates(self, groups: list[DuplicateGroup]) -> str:
        """Return human-readable summary of duplicate groups"""
    async def compare_images(self, path_a: str, path_b: str) -> float:
        """Return similarity score 0-1 between two images"""
    async def compare_files_semantic(self, path_a: str, path_b: str) -> float:
        """Return semantic similarity score 0-1"""
    async def analyze_structure(self, structure_report: StructureReport) -> StructureAdvice:
        """Return advice on structure improvements"""
    async def suggest_organization(self, manifest: Manifest) -> OrganizationPlan:
        """Return AI-generated organization suggestion"""
```

### Phase v2 Modules

#### Rule Learner
- Observes user behavior over time (approved actions)
- Suggests new rules: "You moved 12 files containing 'invoice' to Invoices — create a rule?"
- Learns from repeated patterns

#### Structure Analyzer
- Identifies deep chains, redundant nesting, inconsistent naming
- Suggests flattening or restructuring
- Identifies "island" directories (files that should be grouped but aren't)

#### Duplicate Summarizer
- Groups duplicates by origin: "These 8 copies of StructBERT/config are from different cloned repos"
- Suggests canonical location
- Estimates space savings

#### Auto-Organizer
- Given a folder and a goal, proposes an organization plan
- "Organize my Downloads by month and type" → generates rules
- Human reviews before execution

#### Image Comparator
- perceptual hash comparison (pHash / aHash)
- perceptual hash + CNN feature similarity
- Returns similarity score + visual diff map

#### File Semantic Comparer
- For text files: embedding similarity (local small LLM or TF-IDF fallback)
- For documents: structure + content similarity
- For code: AST-level similarity

### AI Configuration (settings.json)
```json
{
  "ai": {
    "enabled": false,
    "provider": "openai",
    "api_key_env": "OPENAI_API_KEY",
    "model": "gpt-4o-mini",
    "image_model": "ResNet50",
    "semantic_threshold": 0.85,
    "rule_learner_enabled": true
  }
}
```

### Provider Support (v2)
Supported providers with API key or OAuth:

| Provider | Auth | Models |
|---------|------|--------|
| OpenAI | API key + OAuth | GPT-4o, GPT-4o-mini, o3, o4-mini |
| Anthropic | API key + OAuth | Claude 3.5 Sonnet, 3.7, Opus |
| Google AI Studio | API key + OAuth | Gemini 2.0 Flash, 2.5 Pro, 3.0 |
| Groq | API key | Llama 4, Mistral, Qwen |
| Ollama | Local (no key) | Any local model |
| LM Studio | Local (no key) | Any local model |
| Local model (raw) | None | HuggingFace, GGUF, etc. |

### AI Provider UI (v2)
- Settings page: "Connect AI" section
- User pastes API key OR clicks "Connect with OAuth" (opens provider OAuth flow)
- Dropdown to select provider
- Model auto-detects available models for selected provider
- Connection test: "Verifying..." → ✅ Connected or ❌ Invalid
- All credentials stored locally, never transmitted except to the provider
- No telemetry, no third-party logging

### Design Principle
Inspired by OpenClaw's approach but simplified:
- OpenClaw is powerful but complex to configure
- File Organizer: one field for API key, one dropdown for provider, one for model — done
- OAuth where supported (OpenAI, Anthropic, Google) for keyless flow
- Fall back to local models if no API key provided
- "AI Features require an API key to enable" shown in UI when not configured

---

## Output Modes

### Mode 1 — In-Place Reorganization
- Files moved within the same scanned tree
- Folder structure preserved, files reorganized within
- Best for: cleaning up existing structure

### Mode 2 — Separate Output Directory
- All organized files copied/moved to new base path
- Original untouched
- Best for: testing, having a clean copy

### Mode 3 — Ask Per Folder (Hybrid)
- User selects specific parent folders
- Each selected folder gets its own output configuration
- Tool asks: "What do you want to do with Prospero/Mplug?"
  - Mirror structure (organize within)
  - Flatten into category folders
  - Output to external drive

### Mode 4 — Audit Only
- No moves, only reports
- Full analysis, duplicate report, structure report
- Best for: understanding before committing

---

## UI Pages

### Existing Pages (from Phase 3 current)
1. **Scan** — Select folder(s), mode, include/exclude
2. **Results** — File tree, categories, duplicate groups
3. **Rules** — Rule builder with live preview
4. **Preview** — Action plan review with bulk select
5. **Execute** — Progress, live feed, undo

### New Pages (Phase 3 extended)

#### Page 2b: Structure Analysis
- Visual tree map of scanned folder
- Issues highlighted by severity (red/yellow/green)
- Clickable nodes → drill into specific issues
- Recommendations panel with estimated impact
- "Apply AI Suggestions" button (Phase v2)

#### Page 2c: Cross-Path Scan
- Multi-select folders to compare
- Matrix view: which folders share files
- Shared subpath browser
- "Compare" button → generates cross-duplicate manifest
- Per-group action: keep from which tree, trash others

#### Page 2d: Duplicate Browser (Enhanced)
- Group view with tier filter (Exact / Likely / Similar / Semantic)
- Per-group: see all locations, sizes, modified dates
- Bulk select by tier
- "Keep Earliest" / "Keep Latest" / "Keep in Tree: X" shortcuts
- AI summarizer button (Phase v2)

#### Page 3a: AI Panel (Phase v2)
- Rule learner suggestions
- Structure improvement recommendations
- Auto-organizer preview
- Toggle AI features on/off per scan

---

## Settings Schema

```json
{
  "base_output_dir": "/path/to/Organized",
  "default_output_mode": "separate_output",
  "conflict_mode": "rename",
  "trash_dir": "~/.file-organizer-trash",
  "scan": {
    "large_file_threshold_mb": 100,
    "hash_cache_enabled": true,
    "hash_cache_dir": "~/.file-organizer-cache",
    "follow_symlinks": false,
    "include_hidden": false,
    "exclude_dirs": [".git", "__pycache__", ".venv", "node_modules", ".DS_Store"]
  },
  "structure": {
    "max_depth_warning": 8,
    "large_dir_warning": 500,
    "detect_similar_subtrees": true,
    "similarity_threshold": 0.5
  },
  "categories": {
    "Images": {"enabled": true, "subfolders": ["Photos", "Screenshots", "ML", "Raw", "Other"]},
    "Documents": {"enabled": true, "subfolders": ["PDFs", "Text", "Spreadsheets", "ML", "Other"]},
    "Video": {"enabled": true, "subfolders": ["Movies", "TV", "Clips", "ML", "Other"]},
    "Audio": {"enabled": true, "subfolders": ["Music", "Podcasts", "ML", "Other"]},
    "Code": {"enabled": true, "subfolders": ["Python", "Scripts", "Configs", "Other"]},
    "Archives": {"enabled": true, "subfolders": ["Zip", "Tar", "Other"]},
    "Other": {"enabled": true, "subfolders": []}
  },
  "rules": [],
  "parent_folders": [],  # absolute paths marked as parent boundaries
  "scan": {
    "exclude_dirs": [".git", "__pycache__", ".venv", "node_modules", ".DS_Store", "node_modules", ".Trash", "$RECYCLE.BIN"],
    "exclude_known_system": true,  # auto-exclude .pyc, .DS_Store, etc.
    "unknown_file_policy": "review"  # always surface unknown files to user
  },
  "theme": {
    "primary_color": "#6366f1",
    "bg_color": "#0f172a",
    "surface_color": "#1e293b",
    "text_color": "#f1f5f9",
    "accent_color": "#22d3ee",
    "muted_color": "#94a3b8",
    "success_color": "#22c55e",
    "warning_color": "#f59e0b",
    "error_color": "#ef4444"
  },
  "ai": {
    "enabled": false,
    "provider": "local",
    "model": "sentence-transformers/all-MiniLM-L6-v2",
    "image_model": "ResNet50",
    "semantic_threshold": 0.85,
    "rule_learner_enabled": true
  }
}
```

---

## Implementation Phases

### Phase 3 (Current) — Structural Foundation
- Cross-path scan module with manifest
- Cross-path duplicate detection (Tier 1 + 2)
- Structure analyzer with issue detection
- Multi-folder selection and comparison UI
- Output modes: in-place, separate output, ask-per-folder
- Enhanced duplicate browser with tier filtering
- Structure analysis page

### Phase v2 — AI Layer
- AI interface protocol + stub implementations
- Rule learner from user action history
- Structure analyzer integration
- Duplicate summarizer
- Image comparator (pHash)
- File semantic comparer (TF-IDF fallback)
- Auto-organizer suggestion engine

### Phase v3+ — Advanced
- Local LLM integration for deep semantic understanding
- Visual diff map for image comparison
- Organizational memory (learns user preferences over time)
- Collaborative rules sharing
- Plugin system for custom analyzers

---

## Technical Notes

### Performance
- 663K files at 4KB avg = ~2.6GB manifest (JSON)
- Use streaming JSON for large scans
- Hash cache SQLite — must handle concurrent reads
- Structure analysis is O(n) on directory count, not file count

### Git-aware Scanning
- `.git` directories: scan only to detect cloned repos
- Never move/delete `.git` folders
- Flag `.venv`, `node_modules` separately

### Cross-Platform
- Path separators normalized internally to `/`
- On Windows: convert to `\` before filesystem operations
- Tested on macOS (Intel + Apple Silicon), Linux, Windows (future)

---

## Open Questions (User to Answer)
1. Should `.venv`, `__pycache__`, `.git` be included in scans by default, or always excluded?
2. For your drive specifically — should `archive/data/` files (numbered IDs, no extension) be treated as ML training artifacts or flagged as unusual?
3. What output mode do you default to for your drive — separate output or in-place?
