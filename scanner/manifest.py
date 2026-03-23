import json
import os
import hashlib
import xxhash
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Optional, Set
from .utils import classify_file, is_venv_dir, is_git_dir, is_pycache, get_relative_path, normalize_path

LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB
HASH_CACHE_SIZE = 8 * 1024  # xxhash chunk size for prefix hash (8KB)

@dataclass
class ScannedFile:
    path: str
    relative_path: str
    parent_tree: str
    name: str
    ext: str
    size_bytes: int
    modified_ts: str
    mtime: float = 0.0   # unix timestamp — for date-based filters
    ctime: float = 0.0   # unix timestamp — for date-based filters
    hash: Optional[str] = None
    prefix_hash: Optional[str] = None
    category: str = "other"
    classification: str = "known"  # known | unknown | system
    is_symlink: bool = False
    symlink_target: Optional[str] = None
    is_duplicate: bool = False
    depth: int = 0

@dataclass
class ScanMeta:
    scan_id: str
    paths_scanned: List[str]
    mode: str  # fast | deep
    timestamp: str
    total_files: int
    total_size_bytes: int
    scan_roots: List[str]

class ExtendedManifestBuilder:
    def __init__(self, paths: List[str], mode: str = "fast",
                 include_hidden: bool = False,
                 exclude_dirs: Optional[List[str]] = None,
                 hash_cache: Optional[dict] = None,
                 follow_symlinks: bool = False):
        self.paths = [normalize_path(p) for p in paths]
        self.mode = mode
        self.include_hidden = include_hidden
        # Default exclusions only apply when exclude_dirs is not explicitly provided (None).
        # Passing [] means "override with nothing"; passing ["git"] overrides .git exclusion.
        if exclude_dirs is None:
            self.exclude_dirs: Set[str] = {".git", "__pycache__", ".venv", "env", "node_modules", ".DS_Store", ".Trash", "$RECYCLE.BIN"}
        else:
            self.exclude_dirs = set(exclude_dirs)
        self.hash_cache = hash_cache or {}  # path -> hash
        self.follow_symlinks = follow_symlinks
        self.files: List[ScannedFile] = []
        self._file_count = 0
        self._total_size = 0
        self._lock = threading.Lock()

    def scan(self) -> dict:
        for path in self.paths:
            self._scan_single(path, parent_tree=self._get_tree_name(path))
        return self._build_manifest()

    def _get_tree_name(self, path: str) -> str:
        """Get a readable name for this scan root."""
        return os.path.basename(path.rstrip("/")) or path

    def _should_exclude_dir(self, name: str) -> bool:
        return name in self.exclude_dirs

    def _scan_single(self, root: str, parent_tree: str):
        root = normalize_path(root)
        for dirpath, dirnames, filenames in os.walk(root, followlinks=self.follow_symlinks):
            # Filter hidden dirs and excluded dirs in-place
            dirnames[:] = [
                d for d in dirnames
                if not (d.startswith(".") and not self.include_hidden)
                and not self._should_exclude_dir(d)
            ]
            rel_dir = get_relative_path(dirpath, root)
            depth = rel_dir.count("/") + (1 if rel_dir else 0)
            for name in filenames:
                if name.startswith(".") and not self.include_hidden:
                    continue
                full_path = normalize_path(os.path.join(dirpath, name))
                try:
                    st = os.stat(full_path)
                except OSError:
                    continue
                is_symlink = os.path.islink(full_path)
                name_clean = name if not name.startswith(".") else name
                _, ext = os.path.splitext(name_clean)
                ext = ext.lower()
                classification = classify_file(name_clean, ext)
                size = st.st_size
                modified = datetime.fromtimestamp(st.st_mtime).isoformat()
                f = ScannedFile(
                    path=full_path,
                    relative_path=normalize_path(os.path.join(rel_dir, name)),
                    parent_tree=parent_tree,
                    name=name,
                    ext=ext,
                    size_bytes=size,
                    modified_ts=modified,
                    mtime=st.st_mtime,
                    ctime=st.st_ctime,
                    category=self._category_from_ext(ext),
                    classification=classification,
                    is_symlink=is_symlink,
                    depth=depth,
                )
                if is_symlink:
                    try:
                        f.symlink_target = os.readlink(full_path)
                    except OSError:
                        pass
                if self.mode == "deep":
                    f.prefix_hash = self._prefix_hash(full_path)
                    if size <= LARGE_FILE_THRESHOLD:
                        cache_key = (full_path, size, st.st_mtime)
                        if cache_key in self.hash_cache:
                            f.hash = self.hash_cache[cache_key]
                        else:
                            f.hash = self._full_hash(full_path)
                            self.hash_cache[cache_key] = f.hash
                with self._lock:
                    self.files.append(f)
                    self._file_count += 1
                    self._total_size += size

    def _prefix_hash(self, path: str) -> str:
        """Fast xxhash of first 8KB."""
        h = xxhash.xxh64()
        try:
            with open(path, "rb") as f:
                chunk = f.read(HASH_CACHE_SIZE)
                h.update(chunk)
        except OSError:
            pass
        return h.hexdigest()

    def _full_hash(self, path: str) -> str:
        """SHA256 full file hash."""
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except OSError:
            pass
        return h.hexdigest()

    def _category_from_ext(self, ext: str) -> str:
        mapping = {
            "images": {"jpg","jpeg","png","gif","bmp","svg","webp","heic","tiff","raw","psd","ico","jfif","pnm"},
            "documents": {"pdf","doc","docx","txt","rtf","odt","xls","xlsx","ppt","pptx","csv","md","pages","numbers","keynote"},
            "video": {"mp4","mkv","mov","avi","wmv","flv","webm","m4v","mpeg","mpg","ts","mts"},
            "audio": {"mp3","wav","flac","aac","ogg","m4a","wma","opus","aiff"},
            "code": {"py","js","ts","java","c","cpp","h","hpp","cs","go","rs","rb","php","swift","kt","scala","r","sh","bash","zsh","ps1","sql","html","css","json","xml","yaml","yml","toml","ini","cfg","env"},
            "archives": {"zip","tar","gz","bz2","xz","rar","7z","tgz","bz","lz","lzma"},
        }
        for cat, exts in mapping.items():
            if ext.lstrip(".") in exts:
                return cat
        return "other"

    def _build_manifest(self) -> dict:
        return {
            "scan_meta": asdict(ScanMeta(
                scan_id=datetime.now().strftime("%Y%m%d%H%M%S"),
                paths_scanned=self.paths,
                mode=self.mode,
                timestamp=datetime.now().isoformat(),
                total_files=self._file_count,
                total_size_bytes=self._total_size,
                scan_roots=[self._get_tree_name(p) for p in self.paths],
            )),
            "files": [asdict(f) for f in self.files],
            "stats": {
                "total_files": self._file_count,
                "total_size_bytes": self._total_size,
                "unknown_count": sum(1 for f in self.files if f.classification == "unknown"),
                "system_count": sum(1 for f in self.files if f.classification == "system"),
                "by_category": self._count_by("category"),
                "by_parent_tree": self._count_by("parent_tree"),
                "by_classification": self._count_by("classification"),
            }
        }

    def _count_by(self, field: str) -> dict:
        counts = {}
        for f in self.files:
            val = getattr(f, field)
            counts[val] = counts.get(val, 0) + 1
        return counts

def build_cross_manifest(paths: List[str], mode: str = "fast",
                          include_hidden: bool = False,
                          exclude_dirs: Optional[List[str]] = None,
                          hash_cache: Optional[dict] = None) -> dict:
    """Convenience function."""
    builder = ExtendedManifestBuilder(
        paths=paths,
        mode=mode,
        include_hidden=include_hidden,
        exclude_dirs=exclude_dirs,
        hash_cache=hash_cache,
    )
    return builder.scan()
