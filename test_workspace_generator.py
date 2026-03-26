#!/usr/bin/env python3
"""test_workspace_generator.py — Massive synthetic test workspace for File Organizer

Usage:
  python3 test_workspace_generator.py --output ~/test_workspace --size-gb 100 \
    --categories '["images","videos","documents","code","archives","audio","design","datasets","temp","duplicates","nested","unknown","system"]'
"""

import argparse
import hashlib
import json
import math
import os
import random
import secrets
import shutil
import string

TEST_ROOT = os.path.expanduser("~/test_workspace")

# ── Helpers ────────────────────────────────────────────────────────────────────

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def make_sparse_file(path, size_bytes):
    """Create a sparse file of exact claimed size (fast for large files)."""
    with open(path, "wb") as f:
        f.truncate(size_bytes)


def make_real_file(path, size_bytes):
    """Write real random bytes (for small files only, ≤1 MB)."""
    with open(path, "wb") as f:
        f.write(os.urandom(size_bytes))


def write_random_file(path, size_bytes):
    """Write file: sparse if >1 MB, real bytes otherwise."""
    if size_bytes > 1024 * 1024:
        make_sparse_file(path, size_bytes)
    else:
        make_real_file(path, size_bytes)


def make_fake_pdf(path, size_kb):
    size_bytes = size_kb * 1024
    header = b"%PDF-1.4\n"
    body = size_bytes - len(header)
    if body <= 0:
        make_real_file(path, size_bytes)
    elif body > 1024 * 1024:
        with open(path, "wb") as f:
            f.write(header)
            f.truncate(size_bytes)  # sparse tail
    else:
        with open(path, "wb") as f:
            f.write(header)
            f.write(os.urandom(body))


def make_fake_image(path, size_kb):
    size_bytes = size_kb * 1024
    header = b"\x89PNG\r\n\x1a\n"
    body = size_bytes - len(header)
    if body <= 0:
        make_real_file(path, size_bytes)
    elif body > 1024 * 1024:
        with open(path, "wb") as f:
            f.write(header)
            f.truncate(size_bytes)
    else:
        with open(path, "wb") as f:
            f.write(header)
            f.write(os.urandom(body))


def make_fake_zip(path, size_kb):
    size_bytes = size_kb * 1024
    header = b"PK\x03\x04"
    body = size_bytes - len(header)
    if body <= 0:
        make_real_file(path, size_bytes)
    elif body > 1024 * 1024:
        with open(path, "wb") as f:
            f.write(header)
            f.truncate(size_bytes)
    else:
        with open(path, "wb") as f:
            f.write(header)
            f.write(os.urandom(body))


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def gen_name(prefix="", length=8):
    """Randomish printable name (unique-ish per run)."""
    chars = string.ascii_lowercase + string.digits
    rnd = "".join(secrets.choice(chars) for _ in range(length))
    return f"{prefix}{rnd}" if prefix else rnd


SWEDISH_CHARS = "åäöÅÄÖéèüß"
SWEDISH_NAMES = [
    "Fika_Bild", "Svensk_Text", "Förårad", "Älskling", "Övning",
    "Skärmdump", "Björk_Fil", "Gräsmatta", "Återställ", "Västerås"
]

NO_EXT_NAMES = [
    "README", "Makefile", "CHANGELOG", "TODO", "NOTES",
    "INSTALL", "LICENSE", "AUTHORS", "CONTRIBUTORS", "HISTORY",
    "COMPILE", "SCRIPT", "DOCKERFILE", "MANIFEST", "METADATA"
]

# ── Category generators ────────────────────────────────────────────────────────

def make_images(root, count, scale):
    """JPEG, PNG, WebP, GIF, TIFF, BMP — proportional to scale."""
    ensure_dir(root)
    exts = ["jpg", "png", "webp", "gif", "bmp", "tiff"]
    for i in range(count):
        ext = exts[i % len(exts)]
        size_kb = (i % 20 + 1) * 512  # 512 KB to 10 MB
        # Add some Swedish filenames
        if i < len(SWEDISH_NAMES):
            make_fake_image(f"{root}/{SWEDISH_NAMES[i]}_{i}.{ext}", size_kb)
        else:
            make_fake_image(f"{root}/photo_{i}.{ext}", size_kb)


def make_videos(root, count, scale):
    ensure_dir(root)
    exts = ["mp4", "mov", "mkv", "avi", "webm", "m4v"]
    for i in range(count):
        ext = exts[i % len(exts)]
        # Sparse for large files
        size_mb = (i % 10 + 1) * 100  # 100 MB to 1 GB
        make_sparse_file(f"{root}/video_{i}.{ext}", size_mb * 1024 * 1024)


def make_documents(root, count, scale):
    ensure_dir(root)
    exts_pdf = ["pdf"]
    exts_office = ["docx", "pptx", "xlsx", "odt", "rtf"]
    exts_text = ["txt", "md", "rst", "tex"]
    all_exts = exts_pdf + exts_office + exts_text
    for i in range(count):
        ext = all_exts[i % len(all_exts)]
        if ext == "pdf":
            make_fake_pdf(f"{root}/document_{i}.{ext}", (i % 50 + 1) * 50)
        else:
            make_fake_zip(f"{root}/document_{i}.{ext}", (i % 20 + 1) * 50)


def make_audio(root, count, scale):
    ensure_dir(root)
    exts = ["mp3", "wav", "m4a", "flac", "ogg", "aac", "wma"]
    for i in range(count):
        ext = exts[i % len(exts)]
        size_kb = (i % 15 + 1) * 1024  # 1 MB to 15 MB
        make_fake_zip(f"{root}/track_{i}.{ext}", size_kb)


def make_code(root, count, scale):
    ensure_dir(root)
    ensure_dir(f"{root}/Notebooks")
    exts = ["py", "js", "ts", "java", "cpp", "go", "rs", "sh", "css", "html",
            "json", "yaml", "yml", "sql", "c", "h", "rb", "php", "swift", "kt"]
    for i in range(count):
        ext = exts[i % len(exts)]
        size_kb = (i % 10 + 1) * 10  # 10 KB to 100 KB
        write_random_file(f"{root}/file_{i}.{ext}", size_kb * 1024)
    # Notebooks
    nb_count = max(3, count // 4)
    for i in range(nb_count):
        make_fake_zip(f"{root}/Notebooks/notebook_{i}.ipynb", (i % 5 + 1) * 1024)


def make_archives(root, count, scale):
    ensure_dir(root)
    exts = ["zip", "rar", "7z", "tar", "gz", "bz2", "dmg", "iso", "tar.gz"]
    for i in range(count):
        ext = exts[i % len(exts)]
        size_kb = (i % 30 + 1) * 1024  # 1 MB to 30 MB
        make_fake_zip(f"{root}/archive_{i}.{ext}", size_kb)


def make_design(root, count, scale):
    ensure_dir(root)
    exts = ["psd", "ai", "fig", "sketch", "xd", "svg", "eps", "indd"]
    for i in range(count):
        ext = exts[i % len(exts)]
        size_kb = (i % 20 + 1) * 1024  # 1 MB to 20 MB
        make_fake_zip(f"{root}/design_{i}.{ext}", size_kb)


def make_datasets(root, count, scale):
    ensure_dir(root)
    csv_count = count * 2 // 3
    other_count = count - csv_count
    for i in range(csv_count):
        size_mb = (i % 10 + 1)  # 1 MB to 10 MB CSV
        write_random_file(f"{root}/dataset_{i}.csv", size_mb * 1024 * 1024)
    for i in range(other_count):
        exts_parq = ["parquet", "arrow", "feather"]
        ext = exts_parq[i % len(exts_parq)]
        size_mb = (i % 5 + 1)  # 1 MB to 5 MB
        make_fake_zip(f"{root}/dataset_{csv_count + i}.{ext}", size_mb * 1024 * 1024)


def make_temp(root, count, scale):
    ensure_dir(root)
    for i in range(count):
        rnd_name = gen_name("temp_")
        size_kb = (i % 10 + 1) * 10  # 10 KB to 100 KB
        write_random_file(f"{root}/{rnd_name}.tmp", size_kb * 1024)
        write_random_file(f"{root}/{gen_name('log_')}.log", size_kb * 1024)


def make_duplicates(root, count, scale):
    """Create tiered duplicates: exact (same hash), likely (same name+size), similar."""
    ensure_dir(root)
    ensure_dir(f"{root}/exact")
    ensure_dir(f"{root}/likely")
    ensure_dir(f"{root}/similar")

    # Tier 1: Exact duplicates — at least 10 hash-identical pairs
    # Create a pool of source blobs
    tier1_pairs = min(12, max(5, count // 6))
    source_blobs = []
    for s in range(tier1_pairs):
        blob_size = (s % 10 + 1) * 1024 * 1024  # 1–10 MB
        blob = os.urandom(min(blob_size, 5 * 1024 * 1024))  # cap real bytes at 5 MB
        source_blobs.append((blob, blob_size))

    exact_dupes = 0
    for s, (blob, blob_size) in enumerate(source_blobs):
        # Write source
        src_path = f"{root}/exact/source_{s}.bin"
        with open(src_path, "wb") as f:
            f.write(blob)
            if blob_size > len(blob):
                f.truncate(blob_size)
        # Create 2-3 exact copies with different names
        for copy in range(2):
            copy_name = f"{root}/exact/copy_{s}_{copy}_{gen_name()}.bin"
            with open(copy_name, "wb") as f:
                f.write(blob)
                if blob_size > len(blob):
                    f.truncate(blob_size)
        exact_dupes += 1 + 2  # source + 2 copies = 3 files per pair

    # Tier 2: Likely duplicates — same name + size, different content
    tier2_groups = min(8, max(3, count // 8))
    for g in range(tier2_groups):
        base_name = f"file_{g}"
        for v in range(3):
            size_kb = (g % 20 + 1) * 512  # same size bucket
            write_random_file(f"{root}/likely/{base_name}_variant_{v}.bin", size_kb * 1024)

    # Tier 3: Similar names + same extension + size ±5%
    tier3_groups = min(5, max(2, count // 10))
    base_sizes = [(i % 10 + 1) * 1024 for i in range(tier3_groups)]  # KB
    for g in range(tier3_groups):
        base_sz = base_sizes[g]
        for v in range(4):
            sz_var = int(base_sz * (0.95 + v * 0.02))  # ±5%
            make_real_file(f"{root}/similar/report_{g}_variant_{v}.csv", sz_var * 1024)

    return tier1_pairs, tier2_groups, tier3_groups


def make_nested(root, count, scale):
    """Deeply nested: 10 levels with files at each level."""
    base = root
    for depth in range(10):
        base = f"{base}/level_{depth}"
        ensure_dir(base)
        files_here = max(1, (count // 10) // 10)
        for i in range(files_here):
            exts = ["txt", "log", "csv", "json"]
            ext = exts[i % len(exts)]
            write_random_file(f"{base}/file_d{depth}_{i}.{ext}", (i % 10 + 1) * 1024)
    # Deepest file
    write_random_file(f"{base}/deepest.txt", 512)


def make_unknown(root, count, scale):
    """Files with no extension or hidden system-like names."""
    ensure_dir(root)
    # No-extension files
    for i in range(count // 2):
        base = NO_EXT_NAMES[i % len(NO_EXT_NAMES)]
        write_random_file(f"{root}/{base}_{i}", (i % 10 + 1) * 1024)
    # Unknown extension
    for i in range(count // 2):
        exts_unknown = ["dat", "bag", "blob", "cache", "dump", "core"]
        ext = exts_unknown[i % len(exts_unknown)]
        write_random_file(f"{root}/unknown_{i}.{ext}", (i % 5 + 1) * 1024)


def make_system(output_dir, root, count, scale):
    """System files: .git, package.json, __pycache__, venv, node_modules, .DS_Store, ProtectedFolder."""
    ensure_dir(root)
    # .git/HEAD
    ensure_dir(f"{root}/.git")
    write_random_file(f"{root}/.git/HEAD", 40)
    write_random_file(f"{root}/.git/config", 256)

    # package.json (JavaScript)
    pkg = json.dumps({
        "name": "test-project", "version": "1.0.0",
        "dependencies": {"lodash": "^4.17.21", "express": "^4.18.0"}
    }, indent=2)
    with open(f"{root}/package.json", "w") as f:
        f.write(pkg)

    # Python __pycache__
    ensure_dir(f"{root}/__pycache__")
    write_random_file(f"{root}/__pycache__/cache.cpython-312.pyc", 4096)

    # venv (sparse marker files)
    ensure_dir(f"{root}/venv/lib/python3.12/site-packages")
    write_random_file(f"{root}/venv/pyvenv.cfg", 128)

    # node_modules (sparse)
    ensure_dir(f"{root}/node_modules/lodash")
    write_random_file(f"{root}/node_modules/lodash/package.json", 256)

    # macOS .DS_Store
    write_random_file(f"{root}/.DS_Store", 1024)

    # .env / secrets in ProtectedFolder — at workspace root, not inside System/
    ensure_dir(f"{output_dir}/ProtectedFolder")
    write_random_file(f"{output_dir}/ProtectedFolder/.env", 256)
    write_random_file(f"{output_dir}/ProtectedFolder/secrets.json", 512)
    ensure_dir(f"{output_dir}/ProtectedFolder/.git")
    write_random_file(f"{output_dir}/ProtectedFolder/.git/HEAD", 40)
    write_random_file(f"{output_dir}/ProtectedFolder/.git/config", 256)


def count_stats(root):
    total_files = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip sparse dirs like venv/node_modules from full walk
        skip_dirs = {"venv", "node_modules", "__pycache__"}
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                total_bytes += os.path.getsize(fpath)
                total_files += 1
            except OSError:
                pass
    return total_files, total_bytes


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate massive synthetic test workspace for File Organizer")
    parser.add_argument("--output", default=os.path.expanduser("~/test_workspace"),
                        help="Output directory path (default: ~/test_workspace)")
    parser.add_argument("--size-gb", type=int, default=10,
                        help="Fake size in GB (1–2000). Sparse files use minimal real storage.")
    parser.add_argument("--categories", type=json.loads,
                        default='["images","videos","documents","code","archives","audio","design","datasets","temp","duplicates","nested","unknown","system"]',
                        help='JSON list of categories to generate')
    args = parser.parse_args()

    output_dir = os.path.expanduser(args.output)
    size_gb = args.size_gb
    categories = args.categories

    if not (1 <= size_gb <= 2000):
        raise SystemExit("--size-gb must be between 1 and 2000")

    # Base count proportional to GB
    base_count = size_gb * 5  # ~5 files per GB
    per_cat = base_count // len(categories)

    # Wipe and recreate
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    ensure_dir(output_dir)

    category_map = {
        "images":    ("Images",    make_images),
        "videos":    ("Videos",    make_videos),
        "documents": ("Documents", make_documents),
        "audio":     ("Audio",     make_audio),
        "code":      ("Code",      make_code),
        "archives":  ("Archives",  make_archives),
        "design":    ("Design",    make_design),
        "datasets":  ("Datasets",  make_datasets),
        "temp":      ("Temp",      make_temp),
        "duplicates":("Duplicates",make_duplicates),
        "nested":    ("Nested",    make_nested),
        "unknown":   ("Unknown",   make_unknown),
        "system":    ("System",    lambda r, c, s: make_system(output_dir, r, c, s)),
    }

    print(f"Generating workspace at: {output_dir}")
    print(f"Requested size: {size_gb} GB (sparse) | ~{base_count} total files | {per_cat}/category")

    tier1_pairs = tier2_groups = tier3_groups = 0
    deepest_nest = 0

    for cat in categories:
        cat_lower = cat.lower()
        if cat_lower in category_map:
            folder, func = category_map[cat_lower]
            print(f"  Building {folder}/ ...")
            if cat_lower == "duplicates":
                tier1_pairs, tier2_groups, tier3_groups = func(f"{output_dir}/{folder}", per_cat, size_gb)
            elif cat_lower == "nested":
                func(f"{output_dir}/{folder}", per_cat, size_gb)
                deepest_nest = 10
            else:
                func(f"{output_dir}/{folder}", per_cat, size_gb)
        else:
            print(f"  Unknown category: {cat} — skipping")

    count, total_bytes = count_stats(output_dir)
    total_mb = total_bytes / (1024 * 1024)
    fake_gb = size_gb
    print(f"\nCreated {count} files, {fake_gb:.0f}GB fake / {total_mb:.1f}MB actual")
    if tier1_pairs:
        print(f"Tier 1 exact dupes: {tier1_pairs} pairs")
    if tier2_groups:
        print(f"Tier 2 likely dupes: {tier2_groups} groups")
    if tier3_groups:
        print(f"Tier 3 similar: {tier3_groups} groups")
    if deepest_nest:
        print(f"Deepest nest: level {deepest_nest}")
    print(f"Protected: ProtectedFolder/")
    print(f"Workspace: {output_dir}")


if __name__ == "__main__":
    main()
