# File Organizer & Deduper — Phase 3 Specification
**Phase:** 3 (Web UI Prototype → Desktop V1)
**Stack:** Python FastAPI backend + Vanilla JS/CSS web UI
**Goal:** Polished, local-first desktop app feel. Open source. No internet required.

---

## Architecture

```
file-organizer/
├── organizer.py          # Phase 1 scan engine (unchanged)
├── executor.py           # Phase 2 execution engine (unchanged)
├── planner.py            # NEW: Phase 3 rule engine — generates action plans
├── app.py                # NEW: FastAPI app — serves UI + API
├── settings.json         # NEW: User settings (categories, rules, preferences)
└── web_ui/              # NEW: Static web assets
    ├── index.html
    ├── css/
    │   └── style.css
    └── js/
        └── app.js
```

**Stack decisions:**
- FastAPI backend: wraps organizer.py + executor.py as subprocess calls
- planner.py: pure Python module — reads manifest JSON + rules JSON → emits action plan JSON
- Web UI: Vanilla JS + CSS (no framework, no build step) — keeps it simple and portable
- Future desktop: same codebase wrapped with Flet or PyInstaller — no rewrite
- Local-only: no external APIs, no internet, no telemetry

**Port:** 3001 (next free safe port after Mission Control on 3000)

---

## Planner Module (`planner.py`)

### Role
Takes a Phase 1 manifest JSON + a rules configuration → produces an action plan JSON for Phase 2 executor.

### Data Model

**Rule:**
```json
{
  "name": "PDFs to Documents",
  "category": "Documents",
  "filter": {
    "type": "extension",
    "values": ["pdf"]
  },
  "subfolder": "PDFs",
  "destination_template": "{category}/{subfolder}/{name}.{ext}",
  "conflict_mode": "rename"
}
```

**Filter types:**
- `extension`: match by file extension (values: list of extensions)
- `name_contains`: match if filename contains substring
- `name_pattern`: match by glob pattern (e.g. `invoice_*`)
- `size_gt`: match files larger than N bytes
- `size_lt`: match files smaller than N bytes
- `has_metadata`: match by file metadata (e.g. has EXIF)

**Destination template variables:**
- `{category}` — Images, Documents, Videos, Audio, Code, Archives, Other
- `{subfolder}` — user-defined subfolder within category
- `{name}` — original filename without extension
- `{ext}` — original extension
- `{year}` — file modified year (YYYY)
- `{month}` — file modified month (MM)
- `{date}` — file modified date (YYYY-MM-DD)

**Conflict modes:**
- `skip`: do nothing if destination exists
- `rename`: append `_1`, `_2` etc. to filename (default)
- `overwrite`: replace destination file (with confirmation in UI)

**Action plan item:**
```json
{
  "action": "move",
  "src": "/path/to/file.jpg",
  "dst": "/organized/Images/Photos/file.jpg",
  "rule_matched": "Photos to Images",
  "status": "pending",
  "conflict_mode": "rename"
}
```

### Planner Logic
1. Load manifest JSON
2. For each file in manifest, evaluate rules in priority order (user-defined order)
3. First matching rule determines destination
4. If no rule matches → `action: "skip"`
5. Check for duplicate groups → apply duplicate resolution rule (keep first, move rest, or ask user)
6. Return action plan JSON

### Rule Priority
- Rules are user-ordered in settings.json
- First matching rule wins (no cascading)
- Catch-all default: move to category root

---

## API Endpoints (`app.py`)

### `POST /api/scan`
Run Phase 1 organizer scan.

**Request:**
```json
{"path": "/home/sigge/Downloads", "mode": "fast", "include_hidden": false}
```

**Response:**
```json
{"status": "ok", "manifest_path": "/tmp/scan_2024-01-15.json", "total_files": 1234}
```

### `GET /api/manifest/<scan_id>`
Return manifest JSON for a completed scan.

### `GET /api/rules`
Return current rules from settings.json.

### `PUT /api/rules`
Save updated rules to settings.json.

**Request:** `{ "rules": [...] }`

### `POST /api/preview`
Generate action plan from current manifest + rules (dry run — no file changes).

**Request:**
```json
{"manifest_path": "/tmp/scan_xxx.json", "rules": [...]}
```

**Response:**
```json
{
  "actions": [
    {"action": "move", "src": "...", "dst": "...", "rule_matched": "...", "status": "pending"},
    {"action": "skip", "path": "...", "status": "skipped_no_rule"}
  ],
  "stats": {"total": 100, "to_move": 45, "to_delete": 3, "to_skip": 52}
}
```

### `POST /api/execute`
Execute a confirmed action plan via executor.py.

**Request:**
```json
{"action_plan": [...], "output_dir": "/tmp/fo-output/"}
```

**Response:**
```json
{"status": "ok", "undo_log": "/tmp/fo-output/undo_2024-01-15.json", "completed": 48, "failed": 0}
```

### `GET /api/settings`
Return current settings.json contents.

### `PUT /api/settings`
Save updated settings.

---

## Settings (`settings.json`)

```json
{
  "base_output_dir": "/home/sigge/Organized",
  "default_conflict_mode": "rename",
  "trash_dir": "/home/sigge/.file-organizer-trash",
  "categories": {
    "Images": {"enabled": true, "subfolders": ["Photos", "Screenshots", "Raw"]},
    "Documents": {"enabled": true, "subfolders": ["PDFs", "Text", "Spreadsheets"]},
    "Videos": {"enabled": true, "subfolders": ["Movies", "TV", "Clips"]},
    "Audio": {"enabled": true, "subfolders": ["Music", "Podcasts"]},
    "Code": {"enabled": false, "subfolders": []},
    "Archives": {"enabled": false, "subfolders": []}
  },
  "rules": [
    {
      "name": "Screenshots",
      "category": "Images",
      "filter": {"type": "name_contains", "value": "Screenshot"},
      "subfolder": "Screenshots",
      "destination_template": "{category}/{subfolder}/{name}.{ext}",
      "conflict_mode": "rename"
    },
    {
      "name": "PDF Invoices",
      "category": "Documents",
      "filter": {"type": "name_contains", "value": "invoice"},
      "subfolder": "Invoices",
      "destination_template": "{category}/{subfolder}/{year}/{name}.{ext}",
      "conflict_mode": "rename"
    }
  ],
  "theme": {
    "primary_color": "#6366f1",
    "bg_color": "#0f172a",
    "surface_color": "#1e293b",
    "text_color": "#f1f5f9",
    "accent_color": "#22d3ee"
  }
}
```

---

## Web UI Pages

### Page 1: Home / Scan
- Large folder picker (click to browse, or paste path)
- Scan mode toggle: Fast / Deep
- Checkboxes: Include hidden folders
- "Scan" button — starts scan, shows live progress (file count ticker)
- Recent scan history (last 5 scans, click to load)

### Page 2: Results Dashboard
- Summary cards: Total files, Total size, Categories breakdown, Duplicate groups found
- Category list: each category expandable to show files
- Duplicate groups: visually grouped, expandable — show file paths, sizes, modified dates
- "Build Rules" button → goes to Rules page
- "Preview Actions" button → generates plan and goes to Preview page

### Page 3: Rules Builder
- Left panel: file list (from manifest), click to select files
- Right panel: rule editor
  - Rule name (text input)
  - Filter type dropdown + value input
  - Category dropdown
  - Subfolder input (with autocomplete from settings categories)
  - Destination template (pre-filled, editable, shows live preview)
  - Conflict mode: skip / rename / overwrite
  - Preview: shows which files from manifest this rule would match
- Rule list (ordered): drag to reorder, toggle enable/disable, delete
- "Add Rule" button
- "Save Rules" button
- "Preview Plan" button → goes to Preview page

### Page 4: Action Plan Preview
- Full action plan list: each item shows src → dst
- Filter: All / Moves / Deletes / Skips / Conflicts
- Bulk actions: "Select All Moves", "Select All Deletes", "Deselect All"
- Each item: checkbox + icon + file name + arrow + destination
- Conflict items highlighted in orange, with conflict mode shown
- Warning banner if overwrite mode is selected
- "Execute" button (prominent, accent color)
- "Back to Rules" button

### Page 5: Execution & Complete
- Progress bar: completed / total actions
- Live action feed: shows last 5 executed actions in real time
- Cancel button (stops execution, preserves undo log)
- On complete: success message + summary
- "Undo Last Run" button (loads undo log, offers to reverse)
- "New Scan" button

---

## Visual Design

**Style:** Modern dark, polished, desktop-app feel. Inspired by Linear, Raycast, VS Code.

**Colors (CSS variables from settings.json theme):**
- Background: `#0f172a`
- Surface/cards: `#1e293b`
- Primary: `#6366f1` (indigo)
- Accent: `#22d3ee` (cyan)
- Text: `#f1f5f9`
- Muted text: `#94a3b8`
- Success: `#22c55e`
- Warning/conflict: `#f59e0b`
- Error: `#ef4444`

**Typography:** System font stack (San Francisco / Segoe UI / Ubuntu) — no external fonts needed.

**Layout:** Single-page app feel with sidebar navigation. Pages switch without full reload. Smooth transitions.

**Logo:** Placeholder SVG icon for now (can be replaced later).

**Animations:**
- Page transitions: fade + slide (150ms)
- Button hover: subtle scale + glow
- Progress bar: animated stripes
- Duplicate groups: subtle pulse on hover

---

## Acceptance Criteria

### Must work locally, no internet
- All assets served from FastAPI locally
- No CDN dependencies for JS/CSS
- No external API calls

### Scan → Rules → Preview → Execute flow works end-to-end
1. User picks folder → scan runs → manifest loaded
2. User configures rules → preview generated
3. User reviews action plan → executes
4. Files are moved → undo log created
5. User can undo if something went wrong

### Settings persist
- All settings saved to settings.json on disk
- Survives app restart
- Theme colors applied from settings

### Duplicate groups handled correctly
- Definite duplicates (same hash): clearly flagged
- Likely duplicates (same name+size, different hash): flagged separately
- User chooses which to keep/delete per group

### Error handling
- Invalid folder path → clear error message
- Permission denied → shown per file, execution continues
- Disk full → detected, stopped, undo log preserved
- Executor crash mid-run → partial undo log still valid

### Future AI hook
- Settings has an `ai_categorizer` section (disabled by default)
- If enabled, planner calls a local AI module to categorize files by content
- Interface defined, implementation deferred to Phase 4

---

## Deferred to Phase 4
- Actual AI content categorization (hook only, not implemented)
- Flet / PyInstaller desktop packaging
- Logo and full branding
- Advanced name pattern regex builder
- macOS / Windows specific paths and behaviors
