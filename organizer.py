#!/usr/bin/env python3
"""
File Organizer & Deduper CLI — Phase 1: Scan Engine
Phase 1.5 improvements:
- Two-stage hashing (size → 4KB prefix hash → full hash)
- Persistent hash cache (SQLite)
- Symlink detection and flagging
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
import xxhash
from rich.console import Console
from rich.live import Live
from rich.text import Text

app = typer.Typer(help="File Organizer & Deduper — scan engine")
console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALWAYS_EXCLUDED = {
    ".git", ".svn", ".DS_Store", "__pycache__", ".Trash",
    "$RECYCLE.BIN", "System Volume Information", "pagefile.sys", "Thumbs.db",
}

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

LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB
CHUNK_SIZE = 1024 * 1024                   # 1 MB
PREFIX_SIZE = 4 * 1024                     # 4 KB for prefix hash


# ---------------------------------------------------------------------------
# Hash Cache (SQLite-backed)
# ---------------------------------------------------------------------------

class HashCache:
    """Persistent hash cache keyed by (absolute_path, size, mtime)."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        """Per-thread connection."""
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_hashes (
                    path  TEXT    NOT NULL,
                    size  INTEGER NOT NULL,
                    mtime REAL    NOT NULL,
                    hash  TEXT    NOT NULL,
                    PRIMARY KEY (path, size, mtime)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_path ON file_hashes(path)")
            conn.execute("PRAGMA journal_mode=WAL")  # concurrent write support
            conn.commit()
            self._local.conn = conn
        return self._local.conn

    def get(self, path: str, size: int, mtime: float) -> Optional[str]:
        """Return cached hash if (path, size, mtime) matches, else None."""
        cur = self._conn().execute(
            "SELECT hash FROM file_hashes WHERE path=? AND size=? AND mtime=?",
            (path, size, mtime),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def put(self, path: str, size: int, mtime: float, hash_val: str) -> None:
        """Insert or replace cached hash entry."""
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash) VALUES (?,?,?,?)",
            (path, size, mtime, hash_val),
        )
        conn.commit()

    def close(self) -> None:
        if hasattr(self._local, "conn"):
            self._local.conn.close()


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def sha256_file(path: str) -> Optional[str]:
    """Return 'sha256:<hexdigest>' or None on error."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"
    except (OSError, PermissionError):
        return None


def xxh3_prefix(path: str) -> Optional[str]:
    """Return xxh3_64 hash of the first PREFIX_SIZE bytes."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(PREFIX_SIZE)
        return xxhash.xxh3_64(data).hexdigest()
    except (OSError, PermissionError):
        return None


# ---------------------------------------------------------------------------
# Two-stage hashing
# ---------------------------------------------------------------------------

def two_stage_hash(
    files: list[dict],
    lock: threading.Lock,
    hashed_count: list[int],
    cache: Optional[HashCache],
) -> list[dict]:
    """
    Three-stage deduplication to minimise expensive full-file reads:
      Stage 1 — group by size; drop singletons
      Stage 2 — prefix hash (4 KB); drop singletons
      Stage 3 — full SHA256 only for remaining candidates

    Returns files list with 'hash' field populated where computed.
    Stats are printed at the end.
    """
    # --- Stage 1: group by size ---
    size_groups: dict[int, list[dict]] = defaultdict(list)
    for f in files:
        size_groups[f["size_bytes"]].append(f)

    candidates_after_size = [f for grp in size_groups.values() if len(grp) > 1 for f in grp]
    skipped_size = len(files) - len(candidates_after_size)

    # --- Stage 2: prefix hash ---
    prefix_groups: dict[str, list[dict]] = defaultdict(list)

    def _compute_prefix(f: dict) -> Optional[str]:
        path = f["path"]
        size = f["size_bytes"]
        mtime = f.get("_mtime_raw", 0.0)
        # Check cache first
        if cache:
            cached = cache.get(path, size, mtime)
            if cached:
                with lock:
                    hashed_count[0] += 1
                return cached
        return None

    for f in candidates_after_size:
        cached_hash = _compute_prefix(f)
        if cached_hash:
            # If we have a cached full hash, use it directly as prefix key too
            prefix_groups[cached_hash].append(f)
            f["hash"] = cached_hash
        else:
            ph = xxh3_prefix(f["path"])
            if ph:
                prefix_groups[f"size:{f['size_bytes']}:prefix:{ph}"].append(f)

    candidates_after_prefix = [
        f for grp in prefix_groups.values()
        if len(grp) > 1
        for f in grp
        if f.get("hash") is None  # not already resolved via cache
    ]
    # Also include those already resolved via cache (they stay with their hash)
    already_resolved = [f for f in candidates_after_size if f.get("hash") is not None]

    skipped_prefix = len(candidates_after_size) - len(candidates_after_prefix) - len(already_resolved)

    # --- Stage 3: full SHA256 on remaining candidates ---
    full_hash_count = 0

    def _full_hash(f: dict) -> dict:
        nonlocal full_hash_count
        path = f["path"]
        size = f["size_bytes"]
        mtime = f.get("_mtime_raw", 0.0)

        h = sha256_file(path)
        f["hash"] = h
        if h and cache:
            cache.put(path, size, mtime, h)
        with lock:
            hashed_count[0] += 1
            full_hash_count += 1
        return f

    workers = min(16, max(8, os.cpu_count() or 8))
    if candidates_after_prefix:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_full_hash, f): f for f in candidates_after_prefix}
            for fut in as_completed(futures):
                fut.result()

    console.print(
        f"  [dim]Two-stage hashing stats:[/dim]\n"
        f"    Total files      : {len(files):,}\n"
        f"    Skipped (unique size)  : {skipped_size:,}\n"
        f"    Cache hits       : {len(already_resolved):,}\n"
        f"    Skipped (unique prefix): {skipped_prefix:,}\n"
        f"    Full hashes computed   : {full_hash_count:,}"
    )

    return files


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------

def walk_files(
    root: str,
    include_hidden: bool,
    counter: list[int],
    lock: threading.Lock,
    follow_symlinks: bool = False,
) -> list[dict]:
    """Recursively walk root with os.scandir; return list of file-entry dicts."""
    results: list[dict] = []
    dirs_to_visit = [root]

    while dirs_to_visit:
        current = dirs_to_visit.pop()
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except (PermissionError, OSError):
            continue

        for entry in entries:
            name = entry.name

            # Always-excluded names
            if name in ALWAYS_EXCLUDED:
                continue

            # Check if it's a symlink
            is_sym = entry.is_symlink()

            if is_sym:
                # Symlink: record it, optionally resolve
                try:
                    target = os.readlink(entry.path)
                    target_abs = os.path.realpath(entry.path)
                except OSError:
                    target = None
                    target_abs = None

                if follow_symlinks and target_abs and os.path.isfile(target_abs):
                    # Treat as regular file but flag it
                    try:
                        stat = os.stat(entry.path)  # stat through symlink
                    except OSError:
                        continue
                    ext = Path(name).suffix.lstrip(".").lower()
                    modified_ts = datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat()
                    results.append({
                        "path": entry.path,
                        "name": name,
                        "ext": ext,
                        "size_bytes": stat.st_size,
                        "modified_ts": modified_ts,
                        "_mtime_raw": stat.st_mtime,
                        "hash": None,
                        "is_symlink": True,
                        "symlink_target": target_abs,
                    })
                    with lock:
                        counter[0] += 1
                elif os.path.isdir(entry.path) if follow_symlinks else False:
                    # Symlink to dir: optionally follow
                    if not name.startswith(".") or include_hidden:
                        dirs_to_visit.append(entry.path)
                else:
                    # Record symlink without following
                    results.append({
                        "path": entry.path,
                        "name": name,
                        "ext": Path(name).suffix.lstrip(".").lower(),
                        "size_bytes": 0,
                        "modified_ts": None,
                        "_mtime_raw": 0.0,
                        "hash": None,
                        "is_symlink": True,
                        "symlink_target": target,
                    })
                    with lock:
                        counter[0] += 1
                continue

            if entry.is_dir(follow_symlinks=False):
                # Hidden dir check
                if name.startswith(".") and not include_hidden:
                    continue
                dirs_to_visit.append(entry.path)
            elif entry.is_file(follow_symlinks=False):
                try:
                    stat = entry.stat(follow_symlinks=False)
                except OSError:
                    continue

                ext = Path(name).suffix.lstrip(".").lower()
                modified_ts = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()

                results.append({
                    "path": entry.path,
                    "name": name,
                    "ext": ext,
                    "size_bytes": stat.st_size,
                    "modified_ts": modified_ts,
                    "_mtime_raw": stat.st_mtime,
                    "hash": None,
                    "is_symlink": False,
                    "symlink_target": None,
                })

                with lock:
                    counter[0] += 1

    return results


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def find_duplicates(files: list[dict]) -> list[dict]:
    """Build duplicate_groups from file list."""
    groups: list[dict] = []
    group_id = 0

    # --- Definite: exact SHA256 match (deep mode) ---
    hash_map: dict[str, list[str]] = defaultdict(list)
    for f in files:
        if f["hash"] is not None:
            hash_map[f["hash"]].append(f["path"])

    for h, paths in hash_map.items():
        if len(paths) > 1:
            groups.append({
                "group_id": group_id,
                "tier": "definite",
                "files": paths,
                "hash": h,
            })
            group_id += 1

    # --- Likely: same name+size, different (or null) hash ---
    name_size_map: dict[tuple, list[dict]] = defaultdict(list)
    for f in files:
        key = (f["name"].lower(), f["size_bytes"])
        name_size_map[key].append(f)

    seen_paths: set[str] = set()
    for grp in groups:
        seen_paths.update(grp["files"])

    for key, entries in name_size_map.items():
        if len(entries) < 2:
            continue
        paths_in_group = [e["path"] for e in entries]
        if all(p in seen_paths for p in paths_in_group):
            continue
        novel = [p for p in paths_in_group if p not in seen_paths]
        if len(novel) < 2:
            continue
        groups.append({
            "group_id": group_id,
            "tier": "likely",
            "files": paths_in_group,
            "hash": None,
        })
        group_id += 1

    return groups


# ---------------------------------------------------------------------------
# Empty-folder detection
# ---------------------------------------------------------------------------

def find_empty_folders(root: str, include_hidden: bool) -> list[str]:
    """Return list of effectively-empty directory paths."""
    empty_set: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        relevant_subdirs = [
            os.path.join(dirpath, d)
            for d in dirnames
            if d not in ALWAYS_EXCLUDED and (include_hidden or not d.startswith("."))
        ]

        has_files = bool(filenames)
        all_subdirs_empty = all(p in empty_set for p in relevant_subdirs)

        if not has_files and all_subdirs_empty:
            empty_set.add(dirpath)

    empty_set.discard(root)
    return sorted(empty_set)


def find_hidden_folders(root: str) -> list[str]:
    """Return list of hidden folder paths (starting with .)."""
    hidden: list[str] = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ALWAYS_EXCLUDED]
        for d in dirnames:
            if d.startswith("."):
                hidden.append(os.path.join(dirpath, d))
    return hidden


# ---------------------------------------------------------------------------
# Category preview
# ---------------------------------------------------------------------------

def build_category_preview(files: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for f in files:
        cat = EXTENSION_MAP.get(f["ext"], "Other")
        counts[cat] += 1
    return dict(counts)


# ---------------------------------------------------------------------------
# Scan command
# ---------------------------------------------------------------------------

@app.command()
def scan(
    path: str = typer.Option(..., "--path", help="Directory to scan"),
    mode: str = typer.Option("fast", "--mode", help="Scan mode: fast | deep"),
    include_hidden: bool = typer.Option(False, "--include-hidden", help="Include hidden folders"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", help="Directory to save JSON output (default: cwd)"),
    cache_dir: Optional[str] = typer.Option(None, "--cache-dir", help="Directory for hash cache DB (default: output_dir)"),
    follow_symlinks: bool = typer.Option(False, "--follow-symlinks", help="Follow symlinks (default: False, symlinks are always detected and flagged)"),
):
    """Scan a directory and produce a manifest JSON."""

    if mode not in ("fast", "deep"):
        console.print(f"[red]Invalid mode '{mode}'. Use 'fast' or 'deep'.[/red]")
        raise typer.Exit(1)

    root = os.path.abspath(path)
    if not os.path.isdir(root):
        console.print(f"[red]Path '{root}' is not a directory.[/red]")
        raise typer.Exit(1)

    out_dir = os.path.abspath(output_dir) if output_dir else os.getcwd()
    os.makedirs(out_dir, exist_ok=True)

    cache_db_dir = os.path.abspath(cache_dir) if cache_dir else out_dir
    os.makedirs(cache_db_dir, exist_ok=True)
    cache_db_path = os.path.join(cache_db_dir, "hash_cache.db")

    timestamp_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    out_file = os.path.join(out_dir, f"scan_{timestamp_str}.json")

    counter = [0]
    lock = threading.Lock()

    # --- Walk phase ---
    console.print(f"[bold cyan]Scanning:[/bold cyan] {root}  [dim](mode={mode}, follow_symlinks={follow_symlinks})[/dim]")

    files: list[dict] = []
    with Live(console=console, refresh_per_second=10) as live:
        def _render():
            return Text(f"⠋ Walking... {counter[0]} files found", style="cyan")

        import threading as _threading
        stop_event = _threading.Event()

        def _ticker():
            while not stop_event.is_set():
                live.update(_render())
                stop_event.wait(0.1)

        ticker = _threading.Thread(target=_ticker, daemon=True)
        ticker.start()

        files = walk_files(root, include_hidden, counter, lock, follow_symlinks=follow_symlinks)

        stop_event.set()
        ticker.join()
        live.update(Text(f"✓ Walk complete: {len(files)} files/symlinks", style="green"))

    symlink_count = sum(1 for f in files if f.get("is_symlink"))
    regular_files = [f for f in files if not f.get("is_symlink")]
    total_size = sum(f["size_bytes"] for f in files)

    if symlink_count:
        console.print(f"  [dim]Symlinks detected: {symlink_count}[/dim]")

    # --- Hash phase (deep mode only) ---
    if mode == "deep" and files:
        console.print(f"[bold cyan]Hashing:[/bold cyan] {len(regular_files)} regular files (two-stage)")

        # Open hash cache
        cache = HashCache(cache_db_path)
        console.print(f"  [dim]Hash cache: {cache_db_path}[/dim]")

        hashed_count = [0]

        with Live(console=console, refresh_per_second=10) as live:
            stop_event2 = threading.Event()

            def _render2():
                return Text(
                    f"⠋ Hashing... {hashed_count[0]}/{len(regular_files)} processed",
                    style="cyan",
                )

            def _ticker2():
                while not stop_event2.is_set():
                    live.update(_render2())
                    stop_event2.wait(0.1)

            ticker2 = threading.Thread(target=_ticker2, daemon=True)
            ticker2.start()

            # Only hash regular files (not symlinks)
            regular_files = two_stage_hash(regular_files, lock, hashed_count, cache)

            stop_event2.set()
            ticker2.join()
            live.update(Text(f"✓ Hashing complete: {hashed_count[0]} processed", style="green"))

        cache.close()

        # Merge symlinks back
        sym_files = [f for f in files if f.get("is_symlink")]
        files = regular_files + sym_files

    # Strip internal _mtime_raw field from output
    for f in files:
        f.pop("_mtime_raw", None)

    # --- Analysis ---
    console.print("[bold cyan]Analysing...[/bold cyan]")
    duplicate_groups = find_duplicates(files)
    empty_folders = find_empty_folders(root, include_hidden)
    hidden_folders = find_hidden_folders(root)
    category_preview = build_category_preview(files)

    # --- Build manifest ---
    manifest = {
        "scan_meta": {
            "path": root,
            "mode": mode,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "total_files": len(files),
            "total_size_bytes": total_size,
            "symlink_count": symlink_count,
            "follow_symlinks": follow_symlinks,
        },
        "files": files,
        "duplicate_groups": duplicate_groups,
        "empty_folders": empty_folders,
        "hidden_folders": hidden_folders,
        "category_preview": category_preview,
    }

    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    # --- Summary ---
    console.print()
    console.print(f"[bold green]✓ Scan complete[/bold green]")
    console.print(f"  Files        : {len(files):,}")
    console.print(f"  Symlinks     : {symlink_count:,}")
    console.print(f"  Total size   : {total_size / 1024 / 1024:.1f} MB")
    console.print(f"  Duplicates   : {len(duplicate_groups)} group(s)")
    console.print(f"  Empty folders: {len(empty_folders)}")
    console.print(f"  Output       : {out_file}")
    if mode == "deep":
        console.print(f"  Hash cache   : {cache_db_path}")
    console.print()
    console.print("[bold]Category preview:[/bold]")
    for cat, cnt in sorted(category_preview.items(), key=lambda x: -x[1]):
        console.print(f"  {cat:<12} {cnt:>6,}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
