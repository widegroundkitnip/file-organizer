# Sprint 0 Decision — Dual-Scanner Unification
**Project:** file-organizer
**Date:** 2026-03-25
**Status:** DECISION LOCKED — do not revisit

---

## Existing Decisions (LOCKED)

1. `scanner/manifest.py` (ManifestScanner/ExtendedManifestBuilder) = **canonical scanner**
2. `organizer.py` = **deprecated from pipeline**, kept as CLI reference only
3. `/api/scan` = rewrite to call ManifestScanner directly
4. Manifest format = unified to scanner/manifest.py output
5. Sprint 7a = migration implementation (successor task)

---

## 1. Scanner Canonicalization Plan

### Current State

**`/api/scan` (app.py ~lines 150-215):**
- Runs `organizer.py` via `subprocess.run()` as a child process
- Writes manifest to `scans/scan_<timestamp>.json`
- Then reads that file back to extract `total_files`
- No in-process scanner — subprocess is the scan engine

**`/api/scan/multi` (app.py ~lines 335-360):**
- Calls `build_cross_manifest()` from `scanner/manifest.py` **directly in-process**
- Returns manifest as JSON response (no disk artifact)
- Uses `CrossPathDuplicateFinder` and `StructureAnalyzer` on the in-memory result

**`app.py` already imports scanner directly:**
```python
from scanner import build_cross_manifest, CrossPathDuplicateFinder, StructureAnalyzer
```

### What Must Change

`/api/scan` must be rewritten to mirror `/api/scan/multi`:
- Replace `subprocess.run([sys.executable, "organizer.py", ...])` with direct `ManifestScanner` instantiation or `build_cross_manifest()`
- Return in-memory manifest directly (no disk write/read cycle)
- Progress/cancellation already wired in `ManifestScanner` via `cancel_event` and `progress_callback`

**Key difference — manifest schema divergence:**

| Field | organizer.py | scanner/manifest.py |
|-------|-------------|---------------------|
| `scan_meta.mode` | `"fast"\|"deep"` | `"fast"\|"deep"` |
| `scan_meta.scan_id` | datetime str | datetime str |
| `files[].hash` | `"sha256:..."` or null | raw hex (no prefix) or null |
| `files[].prefix_hash` | not present | xxhash hex |
| `files[].classification` | not present | `"known"\|"unknown"\|"system"` |
| `files[].category` | via `EXTENSION_MAP` | via `_category_from_ext()` |
| `files[].depth` | not present | present |
| `files[].parent_tree` | not present | present |
| `duplicate_groups` | present (organizer's own) | not in base manifest; via `CrossPathDuplicateFinder` |
| `stats` | not present | present (by_category, by_parent_tree, etc.) |
| `empty_folders` | present | not in base manifest |
| `hidden_folders` | present | not in base manifest |

The `ScannedFile` dataclass fields differ from organizer.py's file dict. Sprint 7a must unify the schema.

### Manifest Unification Decision

`scanner/manifest.py` output = **canonical manifest format**. All consumers (planner, UI) consume this schema after Sprint 7a.

The fields unique to organizer.py's output (`empty_folders`, `hidden_folders`) must be either:
- Added to `ExtendedManifestBuilder._build_manifest()` output, OR
- Computed separately in `/api/scan` response via helper functions from organizer.py

**Decision:** Add `empty_folders` and `hidden_folders` computation to `ExtendedManifestBuilder` or as a post-scan step in `/api/scan`. Do NOT keep organizer.py in the call chain.

---

## 2. organizer.py Deprecation Path

### What to KEEP
- `HashCache` class (SQLite-backed persistent hash cache) — useful utility, should migrate to `scanner/utils.py` or `scanner/cache.py`
- `two_stage_hash()` logic (size grouping → prefix hash → full hash pipeline) — the staged approach is sound; scanner/manifest.py should adopt it for deep mode
- `find_duplicates()` — Tier 1 (hash) and Tier 2 (name+size) logic; scanner/duplicate.py covers this but the organizer.py version has slightly different grouping logic worth reviewing
- `find_empty_folders()` and `find_hidden_folders()` — needed for API response fields
- `EXTENSION_MAP` and category classification — scanner/manifest.py has its own mapping; consolidate into one source
- CLI interface (`@app.command()`) — kept as reference only; not called by app.py after migration

### What to REMOVE from pipeline
- The `scan` command's subprocess invocation in `app.py`
- Any code path where organizer.py is run as a library (it's designed as a CLI, not a module)
- The disk-write-then-read cycle in `/api/scan`

### Backward Compatibility Notes
- organizer.py CLI continues to work for manual/local runs
- Existing scan JSON files in `scans/` directory are in organizer.py format — `load_manifest()` in planner must handle both formats during transition (add a format version field on new scans to distinguish)
- rules.json and settings.json are unaffected

### Migration of Unique Logic
organizer.py has `ALWAYS_EXCLUDED` set of directory names that scanner/manifest.py does not have. This should be added to `scanner/utils.py`.

---

## 3. API Migration

### `/api/scan` — Current Contract
```
POST body:  { path: str, mode: str, include_hidden: bool }
Response:   { status: "ok", manifest_path: str, manifest_id: str, total_files: int }
Side effect: writes scans/scan_<timestamp>.json to disk
```

### `/api/scan` — New Contract
```
POST body:  { path: str, mode: str, include_hidden: bool, exclude_dirs?: list[str] }
Response:   {
  status: "ok",
  manifest_id: str,          # e.g. scan_2026-03-25_120000
  total_files: int,
  manifest: { ... },         # full manifest inline (like /api/scan/multi)
  duplicates: [...],          # tier1+tier2+tier3 from CrossPathDuplicateFinder
  structure: { ... },        # from StructureAnalyzer
  unknown_files: [...],       # up to 100 unknown/system files
  unknown_count: int,
  is_empty: bool
}
Side effect: no disk artifact (in-memory only)
```

### `/api/scan/multi` — already correct pattern
No changes needed. Already uses `build_cross_manifest()` + `CrossPathDuplicateFinder` + `StructureAnalyzer` in-process.

### Other endpoints needing review
- `GET /api/manifest/{id}` — still reads from `scans/*.json` files on disk; after migration, manifests may be in-memory only. Need to either store manifests in a session store (Redis/dict) or write to disk with unified schema
- `GET /api/scans` — same; lists scans/*.json on disk. After migration, may need to track scans in a registry
- `POST /api/preview` — calls `load_manifest()` which reads disk JSON; must handle both old and new schema
- `POST /api/execute` — no changes needed (consumes action plan, not scanner output)

### New call contract for `/api/scan`
```python
# NEW: direct in-process scan (no subprocess)
from scanner import build_cross_manifest, CrossPathDuplicateFinder, StructureAnalyzer

manifest = build_cross_manifest(
    paths=[req.path],
    mode=req.mode,
    include_hidden=req.include_hidden,
    exclude_dirs=req.exclude_dirs or [],
)
finder = CrossPathDuplicateFinder(manifest["files"])
duplicates = finder.find()
analyzer = StructureAnalyzer(manifest, [req.path])
structure = analyzer.analyze()
unknown_files = [f for f in manifest["files"] if f.get("classification") in ("unknown", "system")]
```

---

## 4. Bug Inventory (Critical → Sprint 7a must fix)

### BUG-001 — CRITICAL
**All rules disabled by default — new users get zero automation**
- File: `rules.json`, `planner/rules.py`
- All 28 rules have `enabled: false` in rules.json. RuleManager.load() never falls back to in-code defaults once rules.json exists.
- **Fix:** On first load (rules.json not exists), write defaults with `enabled: true`. When loading, if rules.json exists but ALL rules are disabled, log warning.

### BUG-002 — CRITICAL
**Duplicate/conflicting rules in rules.json**
- File: `rules.json`
- Screenshots rule at priority 5 AND 10. Images at 10 AND 30. Camera photos at 6 and 31. Conflicting behavior.
- **Fix:** Deduplicate on load: if two rules have same name+filter, keep higher-priority. Or add schema version with migration.

### BUG-004 — MODERATE
**Tier 1 groups all empty/sparse files as duplicates**
- File: `scanner/duplicate.py`, `_find_exact()`
- Empty files (0 bytes) all hash identically → all grouped as Tier 1 exact duplicates across unrelated file types.
- **Fix:** Skip grouping if `size == 0` or if hash equals empty-file hash (`e3b0c44298fc1c14...`).

### BUG-003 — MODERATE
**No scope_mode UI control — project_safe_mode inaccessible**
- Files: `web_ui/index.html`, `web_ui/js/app.js`
- Backend accepts `scope_mode` param but UI has no control for it.
- **Fix:** Add scope_mode selector in preview/setup area. Surface profile's `default_scope_mode`.

---

## 5. Sprint 7a Checklist

```
SPRINT 7A — Dual-Scanner Unification + Critical Bug Fixes
=========================================================
All tasks below are REQUIRED. Do not skip items.

TASK 7a-01 — Rewrite /api/scan to use ManifestScanner directly
  [ ] Remove subprocess.run([sys.executable, "organizer.py", ...]) call
  [ ] Import build_cross_manifest, CrossPathDuplicateFinder, StructureAnalyzer
  [ ] Call build_cross_manifest(paths=[req.path], mode=req.mode, include_hidden=req.include_hidden)
  [ ] Run CrossPathDuplicateFinder on manifest["files"]
  [ ] Run StructureAnalyzer on manifest and paths
  [ ] Compute unknown_files (classification in unknown/system)
  [ ] Return inline manifest in response (no disk write)
  [ ] Remove the disk-read-back logic for total_files count
  [ ] Test: scan a folder via API, verify manifest returned inline

TASK 7a-02 — Deprecate organizer.py from scan pipeline
  [ ] Add "# DEPRECATED: do not call from app.py" comment at top of organizer.py
  [ ] Verify no remaining imports of organizer.py in app.py
  [ ] Remove organizer.py from any import chains in scanner/, planner/, executor/
  [ ] Document in organizer.py docstring that it is reference-only

TASK 7a-03 — Consolidate duplicate detection logic
  [ ] Audit organizer.py find_duplicates() vs scanner/duplicate.py CrossPathDuplicateFinder
  [ ] Confirm scanner/duplicate.py covers all Tier 1/2/3 logic from organizer.py
  [ ] Add empty-file skip (size==0) to CrossPathDuplicateFinder._find_exact()
  [ ] Migrate ALWAYS_EXCLUDED from organizer.py to scanner/utils.py
  [ ] Verify EXTENSION_MAP coverage is equivalent in both

TASK 7a-04 — Unified manifest schema
  [ ] Add empty_folders computation to post-scan (reuse find_empty_folders from organizer.py)
  [ ] Add hidden_folders computation to post-scan
  [ ] Verify ScannedFile fields: hash format (raw hex vs sha256: prefix — pick one and document)
  [ ] Add schema_version field to manifest output
  [ ] load_manifest() in planner must handle both old (organizer.py) and new schema
  [ ] Test: scan with new schema, feed to planner, verify plan generates

TASK 7a-05 — /api/manifest/{id} and /api/scans compatibility
  [ ] Decide: store manifests in memory registry (dict keyed by manifest_id) or continue writing to scans/
  [ ] If registry: implement in-process manifest storage for /api/scan responses
  [ ] If disk: write unified manifest to scans/ with new schema
  [ ] Verify /api/manifest/{id} returns correct unified schema
  [ ] Verify /api/scans listing works with new scan format

TASK 7a-06 — BUG-001 Fix: Rules enabled by default
  [ ] In planner/rules.py RuleManager: on first load (rules.json doesn't exist), write defaults with enabled=True
  [ ] Add check: if rules.json exists AND all rules have enabled=False, log WARNING
  [ ] Provide migration path: if all disabled, offer to reset to defaults
  [ ] Test: delete rules.json, restart app, verify rules loaded with enabled=True

TASK 7a-07 — BUG-002 Fix: Deduplicate rules.json
  [ ] Add rule deduplication on load: if two rules have same name AND same filter type, keep the one with higher priority (lower number)
  [ ] Normalize case conflicts (e.g., "photos" vs "Photos" in same rule type)
  [ ] Clean rules.json: remove duplicate Screenshots (prio 5 and 10), duplicate Images (prio 10 and 30), conflicting Camera photos rules
  [ ] Test: load rules.json, verify no duplicate names

TASK 7a-08 — BUG-004 Fix: Empty file Tier 1 exclusion
  [ ] In scanner/duplicate.py CrossPathDuplicateFinder._find_exact(): skip files with size == 0
  [ ] Add explicit check: skip if hash equals empty-file SHA256 (e3b0c44298fc1c14...)
  [ ] Test: scan folder with empty files, verify they don't appear in Tier 1 duplicate groups

TASK 7a-09 — Verify web UI end-to-end
  [ ] Start app, open UI, click Scan, select folder
  [ ] Verify scan completes and results render
  [ ] Navigate to preview, verify file list and categories
  [ ] Navigate to rules, verify rules are enabled and visible
  [ ] Test a dry-run execute, verify no real file changes

TASK 7a-10 — Run existing test suite
  [ ] Run all existing tests (test_scanner.py and any other test files)
  [ ] Fix any breakage from scanner swap
  [ ] All tests must pass before declaring Sprint 7a complete

ACCEPTANCE CRITERIA (all must be true before Sprint 7a is done):
  [ ] app.py /api/scan uses scanner/manifest.py exclusively — zero subprocess calls to organizer.py
  [ ] organizer.py not imported anywhere in app.py, scanner/, planner/
  [ ] All Tier 1/2/3 duplicate detection runs through scanner/duplicate.py
  [ ] New scans use unified manifest schema with schema_version field
  [ ] load_manifest() handles both old organizer.py format and new unified format
  [ ] BUG-001: rules load as enabled=True on fresh install
  [ ] BUG-002: rules.json deduplicated, no conflicting priorities
  [ ] BUG-004: empty files excluded from Tier 1 duplicate groups
  [ ] Web UI scan → preview → execute flow works end-to-end
  [ ] All existing tests pass
```

---

## Blocker Status

**Sprint 7a is UNBLOCKED by this decision.** All preceding sprints (7b, 7c, 7d, 8, 9, 10, 11) are blocked by Sprint 7a and this decision removes that block.

---

*Decision produced: 2026-03-25*
*Decision locked: 2026-03-25*
*Next action: Spawn Sprint 7a (pending human approval)*
