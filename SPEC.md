# File Organizer & Deduper — Product Specification
**Version 3.0** | **2026-03-22**
**Phase 3 + v2 Vision**

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
    "provider": "local",
    "model": "sentence-transformers/all-MiniLM-L6-v2",
    "image_model": "ResNet50",
    "semantic_threshold": 0.85,
    "rule_learner_enabled": true
  }
}
```

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
