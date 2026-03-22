# File Organizer & Deduper

A fast, local-first file intelligence platform. Scan, understand, deduplicate, organize, and (with v2) get AI-powered suggestions on your file ecosystem.

**Status:** Phase 3 development | [SPEC.md](SPEC.md) for full architecture

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 3001 --reload
# → http://localhost:3001
```

## Phases

| Phase | Status | What |
|-------|--------|------|
| Phase 1 — Scan Engine | ✅ Done | Directory walking, hashing, duplicate detection, manifest builder |
| Phase 2 — Execution Engine | ✅ Done | Safe move/delete, undo log, conflict detection, dry-run |
| Phase 3 — Web UI + Rule Engine | 🔨 In Progress | Cross-path scanning, structure analysis, rule builder, multi-output modes |
| Phase v2 — AI Layer | 🔜 Planned | Rule learning, structure analysis, duplicate summarizer, auto-organizer |

---

## Phase 1 — Scan Engine

```bash
python organizer.py scan --path /some/dir --mode fast
python organizer.py scan --path /some/dir --mode deep
python organizer.py scan --path /some/dir --mode deep --include-hidden
python organizer.py scan --path /some/dir --mode fast --output-dir /tmp/scans/
```

### Output Schema

```json
{
  "scan_meta": {"path": "/some/dir", "mode": "fast", "total_files": 1234},
  "files": [
    {
      "path": "/some/dir/photo.jpg",
      "name": "photo.jpg",
      "ext": "jpg",
      "size_bytes": 204800,
      "modified_ts": "2025-01-15T10:30:00+00:00",
      "hash": "sha256:abc123..."
    }
  ],
  "duplicate_groups": [
    {"group_id": 0, "tier": "definite", "files": ["...a.jpg", "...b.jpg"], "hash": "sha256:abc123..."}
  ],
  "empty_folders": ["/some/dir/empty/"],
  "hidden_folders": ["/some/dir/.hidden/"],
  "category_preview": {"Images": 450, "Documents": 120, "Other": 60}
}
```

### Duplicate Tiers

| Tier | Meaning |
|------|---------|
| `definite` | Exact SHA256 match |
| `likely` | Same filename + size |

**Notes:**
- Files >100 MB are skipped for hashing (size+name proxy)
- Hidden folders excluded by default
- Always excluded: `.git`, `.svn`, `__pycache__`, `.Trash`, `$RECYCLE.BIN`, etc.
- Phase 1 never moves or deletes files

---

## Phase 2 — Execution Engine

```bash
python executor.py execute --plan plan.json --output-dir /tmp/fo-output/ --dry-run
python executor.py execute --plan plan.json --output-dir /tmp/fo-output/
```

### Action Plan Schema

```json
[
  {"action": "move", "src": "/path/a.jpg", "dst": "/organized/Images/a.jpg"},
  {"action": "delete", "path": "/path/duplicate.jpg"},
  {"action": "skip", "path": "/path/keep-as-is.jpg"}
]
```

### Safety

| Feature | Behavior |
|---------|----------|
| Dry-run | Logs every action, touches nothing |
| Conflict detection | Skips existing destinations (no overwrite) |
| No hard delete | Moves to `<output_dir>/trash/YYYY-MM-DD_HHMMSS/` |
| Undo log | Full record of every action taken |
| Atomic-ish | Stops on first error, partial undo preserved |

---

## Phase 3 — Web UI (current development)

Open `app.py` via uvicorn (see Quick Start). Full workflow: **Scan → Results → Rules → Preview → Execute**

### Features in development
- Multi-folder selection and cross-path scanning
- Structure analyzer (deep nesting, similar subtrees, venv detection)
- Rule builder with live preview
- Output modes: in-place, separate output, ask-per-folder
- Duplicate browser with tier filtering

### Phase 3 Architecture

```
scanner/       — Cross-path scan + duplicate detection
planner/       — Rule engine + destination templates
ai/            — AI layer (stubbed, v2)
```

See [SPEC.md](SPEC.md) for full architecture.

---

## Phase v2 — AI Layer (planned)

Inspired by OpenClaw's flexibility, but simplified for file organization:

### AI Providers

| Provider | Auth | Models |
|---------|------|--------|
| OpenAI | API key + OAuth | GPT-4o, 4o-mini, o3, o4-mini |
| Anthropic | API key + OAuth | Claude 3.5 Sonnet, 3.7, Opus |
| Google AI Studio | API key + OAuth | Gemini 2.0 Flash, 2.5 Pro, 3.0 |
| Groq | API key | Llama 4, Mistral, Qwen |
| Ollama | Local (no key) | Any local model |
| LM Studio | Local (no key) | Any local model |

### AI Features (v2)
- **Rule learner**: observes your actions, suggests new organization rules
- **Structure analyzer**: detects deep nesting, redundant folders, suggests flattening
- **Duplicate summarizer**: groups duplicates by origin, estimates space savings
- **Auto-organizer**: AI suggests where files should go based on content
- **Image comparator**: perceptual hash + visual diff
- **File semantic comparer**: embedding similarity for text/code

### AI Setup (v2)
```
Settings → Connect AI → Select provider → Paste API key or OAuth → Choose model → ✅ Connected
```
All credentials stored locally. No telemetry.

---

## File Structure

```
file-organizer/
├── organizer.py          # Phase 1 scan engine
├── executor.py           # Phase 2 execution engine
├── planner.py           # Phase 3 rule planner
├── app.py               # FastAPI web app
├── settings.json        # User settings
├── requirements.txt
├── SPEC.md             # Full architecture + v2 AI spec
├── README.md
├── scanner/            # Phase 3: cross-path scanning
├── planner/             # Phase 3: rule engine
├── ai/                 # Phase v2: AI layer
└── data/               # Sample data (not on GitHub — 69MB)
```
