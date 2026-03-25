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
