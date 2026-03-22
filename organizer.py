#!/usr/bin/env python3
"""
File Organizer & Deduper CLI — Phase 1: Scan Engine
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.spinner import Spinner
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


# ---------------------------------------------------------------------------
# Hashing
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


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------

def walk_files(
    root: str,
    include_hidden: bool,
    counter: list[int],
    lock: threading.Lock,
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

            if entry.is_dir(follow_symlinks=False):
                # Hidden dir check
                if name.startswith(".") and not include_hidden:
                    continue
                dirs_to_visit.append(entry.path)
            elif entry.is_file(follow_symlinks=False):
                # Hidden file: only skip if parent is hidden (handled by dir skip above)
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
                    "hash": None,  # filled in later for deep mode
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
    # Key: (name_lower, size_bytes)
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
        # Skip if already captured as definite
        if all(p in seen_paths for p in paths_in_group):
            continue
        # Filter out those already in a definite group
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
    """Return list of effectively-empty directory paths.

    A directory is effectively empty if it contains no files AND all of its
    subdirectories (recursively) are also effectively empty.  Walking bottom-up
    (topdown=False) means a parent is processed only after all its children, so
    we can look up child status in the already-built empty_set.
    """
    empty_set: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        # Filter out always-excluded and (optionally) hidden dirs from consideration.
        # NOTE: in topdown=False mode dirnames[:] does NOT prune traversal, but we
        # use it purely as the list of relevant children to check below.
        relevant_subdirs = [
            os.path.join(dirpath, d)
            for d in dirnames
            if d not in ALWAYS_EXCLUDED and (include_hidden or not d.startswith("."))
        ]

        has_files = bool(filenames)
        all_subdirs_empty = all(p in empty_set for p in relevant_subdirs)

        if not has_files and all_subdirs_empty:
            empty_set.add(dirpath)

    # Exclude root itself
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

    timestamp_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    out_file = os.path.join(out_dir, f"scan_{timestamp_str}.json")

    counter = [0]
    lock = threading.Lock()

    # --- Walk phase ---
    console.print(f"[bold cyan]Scanning:[/bold cyan] {root}  [dim](mode={mode})[/dim]")

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

        files = walk_files(root, include_hidden, counter, lock)

        stop_event.set()
        ticker.join()
        live.update(Text(f"✓ Walk complete: {len(files)} files", style="green"))

    total_size = sum(f["size_bytes"] for f in files)

    # --- Hash phase (deep mode only) ---
    if mode == "deep" and files:
        console.print(f"[bold cyan]Hashing:[/bold cyan] {len(files)} files with ThreadPoolExecutor")
        hashed_count = [0]

        def _hash_file(f: dict) -> dict:
            if f["size_bytes"] <= LARGE_FILE_THRESHOLD:
                f["hash"] = sha256_file(f["path"])
            else:
                # size+name proxy — leave hash null
                f["hash"] = None
            with lock:
                hashed_count[0] += 1
            return f

        workers = min(16, max(8, os.cpu_count() or 8))
        with Live(console=console, refresh_per_second=10) as live:
            stop_event2 = threading.Event()

            def _render2():
                return Text(
                    f"⠋ Hashing... {hashed_count[0]}/{len(files)} files",
                    style="cyan",
                )

            def _ticker2():
                while not stop_event2.is_set():
                    live.update(_render2())
                    stop_event2.wait(0.1)

            ticker2 = threading.Thread(target=_ticker2, daemon=True)
            ticker2.start()

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_hash_file, f): f for f in files}
                files = [fut.result() for fut in as_completed(futures)]

            stop_event2.set()
            ticker2.join()
            live.update(Text(f"✓ Hashing complete: {hashed_count[0]} files", style="green"))

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
    console.print(f"  Total size   : {total_size / 1024 / 1024:.1f} MB")
    console.print(f"  Duplicates   : {len(duplicate_groups)} group(s)")
    console.print(f"  Empty folders: {len(empty_folders)}")
    console.print(f"  Output       : {out_file}")
    console.print()
    console.print("[bold]Category preview:[/bold]")
    for cat, cnt in sorted(category_preview.items(), key=lambda x: -x[1]):
        console.print(f"  {cat:<12} {cnt:>6,}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
