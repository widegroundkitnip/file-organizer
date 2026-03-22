# file-organizer

A fast, memory-efficient file scan, deduplication, and execution tool.
- **Phase 1:** Scan Engine (`organizer.py`)
- **Phase 2:** Execution Engine (`executor.py`)
- **Phase 3:** Web UI + Rule Engine (`app.py`, `planner.py`)

## Phase 3 — Web UI

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 3001 --reload
# Open http://localhost:3001
```

**Workflow:** Scan → Results → Rules → Preview → Execute

---

## Install

```bash
pip install -r requirements.txt
```

## Usage

### Fast scan (filename + size, no hashing)

```bash
python organizer.py scan --path /some/dir --mode fast
```

### Deep scan (SHA256 hashing, ThreadPoolExecutor)

```bash
python organizer.py scan --path /some/dir --mode deep
```

### Deep scan, include hidden folders

```bash
python organizer.py scan --path /some/dir --mode deep --include-hidden
```

### Save output to a specific directory

```bash
python organizer.py scan --path /some/dir --mode fast --output-dir /tmp/scans/
```

## Output

Produces `scan_YYYY-MM-DD_HHMMSS.json` in the output directory (default: cwd).

### Schema

```json
{
  "scan_meta": {
    "path": "/some/dir",
    "mode": "fast",
    "timestamp": "2026-03-22T12:00:00+00:00",
    "total_files": 1234,
    "total_size_bytes": 56789012
  },
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
    {
      "group_id": 0,
      "tier": "definite",
      "files": ["/some/dir/a.jpg", "/some/dir/b.jpg"],
      "hash": "sha256:abc123..."
    }
  ],
  "empty_folders": ["/some/dir/empty/"],
  "hidden_folders": ["/some/dir/.hidden/"],
  "category_preview": {
    "Images": 450,
    "Documents": 120,
    "Other": 60
  }
}
```

## Duplicate Tiers

| Tier | Meaning |
|------|---------|
| `definite` | Exact SHA256 match (deep mode only) |
| `likely` | Same filename + size (fast or deep mode) |

## Notes (Phase 1)

- **No files are ever moved or deleted** by the scan engine — scan only.
- Hidden folders (`.name`) skipped by default; use `--include-hidden` to override.
- Always excluded: `.git`, `.svn`, `__pycache__`, `.Trash`, `$RECYCLE.BIN`, etc.
- Files >100 MB are skipped for hashing in deep mode (size+name proxy used instead).
- Deep mode uses 8–16 worker threads depending on CPU count.

---

## Phase 2 — Execution Engine (`executor.py`)

Takes an action plan JSON and executes it safely.

### Action Plan Schema

```json
[
  {"action": "move", "src": "/absolute/path/file.jpg", "dst": "/absolute/destination/file.jpg"},
  {"action": "delete", "path": "/absolute/path/duplicate.jpg"},
  {"action": "skip", "path": "/absolute/path/keep-as-is.jpg"}
]
```

### Usage

```bash
# Dry run (simulate, no changes)
python executor.py execute --plan plan.json --output-dir /tmp/fo-output/ --dry-run

# Real execution
python executor.py execute --plan plan.json --output-dir /tmp/fo-output/
```

### Safety Guarantees

| Feature | Behaviour |
|---------|-----------|
| **Dry-run** | Logs every action that would happen; touches nothing |
| **Conflict detection** | If `dst` already exists, action is logged as `conflict` and skipped |
| **No hard delete** | `delete` actions move files to `<output_dir>/trash/YYYY-MM-DD_HHMMSS/` |
| **Undo log** | Written to `<output_dir>/undo_YYYY-MM-DD_HHMMSS.json` after every real run |
| **Atomic-ish** | Stops on first error; writes partial undo log before exit |
| **Path validation** | All paths must be absolute; validated before execution starts |

### Output Files

- `<output_dir>/undo_YYYY-MM-DD_HHMMSS.json` — full record of every action taken
- `<output_dir>/trash/YYYY-MM-DD_HHMMSS/<filename>` — "deleted" files (recoverable)
