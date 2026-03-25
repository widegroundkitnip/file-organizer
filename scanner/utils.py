import os
from pathlib import Path
from typing import Set

# Directories always excluded from scanning (migrated from organizer.py)
ALWAYS_EXCLUDED: Set[str] = {
    ".git", ".svn", ".DS_Store", "__pycache__", ".Trash",
    "$RECYCLE.BIN", "System Volume Information", "pagefile.sys", "Thumbs.db",
}

SYSTEM_EXTENSIONS: Set[str] = {
    ".pyc", ".pyo", ".DS_Store", ".localized",
    ".lock", ".tmp", ".temp", ".swp", ".swo",
    ".cache", ".bak", ".backup",
}
UNKNOWN_EXTENSIONS: Set[str] = {".log"}

def classify_file(name: str, ext: str) -> str:
    """Return 'system', 'unknown', or 'known'"""
    if ext.lower() in SYSTEM_EXTENSIONS:
        return "system"
    if ext.lower() in UNKNOWN_EXTENSIONS or not ext:
        return "unknown"
    return "known"

def is_venv_dir(name: str) -> bool:
    return name == ".venv" or name.startswith("venv") or name == "env"

def is_git_dir(name: str) -> bool:
    return name == ".git"

def is_pycache(name: str) -> bool:
    return name == "__pycache__" or name.endswith(".pyc")

def normalize_path(path: str) -> str:
    """Normalize path separators to forward slash, strip null bytes (defensive)."""
    return path.replace(os.sep, "/").replace("\x00", "")

def get_relative_path(src_path: str, scan_root: str) -> str:
    """Get path relative to scan root."""
    src = normalize_path(src_path)
    root = normalize_path(scan_root.rstrip("/"))
    if src.startswith(root + "/"):
        return src[len(root)+1:]
    return src

def is_hidden(name: str, path: str) -> bool:
    """Check if file/dir is hidden (dot-prefixed or macOS specific)."""
    if name.startswith("."):
        return True
    # macOS
    try:
        import stat
        st = os.stat(path)
        return bool(st.st_flags & 0x8000)  # UF_HIDDEN on macOS
    except:
        return False


# ---------------------------------------------------------------------------
# Empty / hidden folder detection (migrated from organizer.py)
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
