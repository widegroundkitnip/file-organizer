#!/usr/bin/env python3
"""test_workspace_generator.py — Generate synthetic test workspace for File Organizer

Usage:
  python3 test_workspace_generator.py --output /path/to/workspace --size-gb 10 --categories '["images","videos","documents"]'
"""

import argparse
import json
import os
import shutil
import hashlib
import secrets
import math

TEST_ROOT = os.path.expanduser("~/test_workspace")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def make_sparse_file(path, size_bytes):
    """Create a sparse file of exact size (fast for large files)."""
    with open(path, "wb") as f:
        f.truncate(size_bytes)


def make_fake_pdf(path, size_kb):
    """Create a fake PDF with valid header and random body."""
    size_bytes = size_kb * 1024
    header = b"%PDF-1.4\n"
    body_size = max(0, size_bytes - len(header))
    with open(path, "wb") as f:
        f.write(header)
        f.write(os.urandom(body_size))


def make_fake_image(path, size_kb):
    """Create a fake PNG with valid header and random body."""
    size_bytes = size_kb * 1024
    header = b"\x89PNG\r\n\x1a\n"
    body_size = max(0, size_bytes - len(header))
    with open(path, "wb") as f:
        f.write(header)
        f.write(os.urandom(body_size))


def make_fake_zip(path, size_kb):
    """Create a fake ZIP with valid header and random body."""
    size_bytes = size_kb * 1024
    header = b"PK\x03\x04"
    body_size = max(0, size_bytes - len(header))
    with open(path, "wb") as f:
        f.write(header)
        f.write(os.urandom(body_size))


def write_random_file(path, size_bytes):
    """Write a file of exact size with random bytes."""
    with open(path, "wb") as f:
        f.write(os.urandom(size_bytes))


def file_hash(path):
    """Return SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def same_hash(p1, p2):
    return file_hash(p1) == file_hash(p2)


def make_downloads(root, scale=1):
    ensure_dir(root)
    # Images (scale = number of extra batches beyond base)
    for i in range(max(1, scale)):
        make_fake_image(f"{root}/IMG_{i}_20240115_143022.jpg", 15 * 1024)
        make_fake_image(f"{root}/screenshot_{i}_2024-01-15.png", 2 * 1024)
    make_fake_image(f"{root}/IMG_20240115_143022.jpg", 15 * 1024)
    make_fake_image(f"{root}/IMG_20240203_091145.jpg", 8 * 1024)
    make_fake_image(f"{root}/screenshot_2024-01-15.png", 2 * 1024)
    make_fake_image(f"{root}/Skärmbild_2024-02-10.png", 1 * 1024)
    make_fake_pdf(f"{root}/invoice_jan_2024.pdf", 200)
    write_random_file(f"{root}/notes.txt", 50 * 1024)
    make_fake_zip(f"{root}/archive_backup.zip", 5 * 1024)
    write_random_file(f"{root}/data.csv", 100 * 1024)
    make_fake_zip(f"{root}/presentation_final_FINAL.pptx", 3 * 1024)
    make_fake_zip(f"{root}/document.docx", 1 * 1024)
    write_random_file(f"{root}/.DS_Store", 4 * 1024)
    write_random_file(f"{root}/temp_file.tmp", 10 * 1024)
    make_sparse_file(f"{root}/large_video.mp4", 600 * 1024 * 1024)
    write_random_file(f"{root}/broken_file_no_extension", 20 * 1024)
    write_random_file(f"{root}/dataset.csv", 2 * 1024 * 1024)


def make_desktop(root):
    ensure_dir(root)
    make_fake_image(f"{root}/photo.jpg", 4 * 1024)
    make_fake_image(f"{root}/PICT_0012.jpg", 3 * 1024)
    make_fake_image(f"{root}/Screenshot 2024-01-20.png", 1 * 1024)
    write_random_file(f"{root}/code_snippet.py", 30 * 1024)
    write_random_file(f"{root}/todo.txt", 5 * 1024)
    write_random_file(f"{root}/notes.md", 10 * 1024)
    write_random_file(f"{root}/KEEP_this_file.txt", 5 * 1024)
    write_random_file(f"{root}/.env", 1 * 1024)
    write_random_file(f"{root}/output.json", 50 * 1024)
    make_fake_zip(f"{root}/notebook.ipynb", 100 * 1024)


def make_projects(root):
    ensure_dir(root)
    ensure_dir(f"{root}/Code")
    ensure_dir(f"{root}/Film")
    ensure_dir(f"{root}/DataScience")
    ensure_dir(f"{root}/Archives")
    ensure_dir(f"{root}/Temp")
    ensure_dir(f"{root}/Images")
    ensure_dir(f"{root}/ProtectedFolder")
    ensure_dir(f"{root}/ProtectedFolder/deep_nested/level1/level2/level3/level4/level5/level6/level7/level8/level9")

    write_random_file(f"{root}/Code/main.py", 20 * 1024)
    write_random_file(f"{root}/Code/utils.js", 10 * 1024)
    write_random_file(f"{root}/Code/data.ts", 8 * 1024)
    write_random_file(f"{root}/Code/config.yaml", 5 * 1024)
    ensure_dir(f"{root}/Code/__pycache__")
    write_random_file(f"{root}/Code/__pycache__/cache.pyc", 50 * 1024)

    make_fake_pdf(f"{root}/Film/script_v3.pdf", 2 * 1024)
    make_sparse_file(f"{root}/Film/rushes.mov", 800 * 1024 * 1024)
    make_sparse_file(f"{root}/Film/B-Roll.mp4", 400 * 1024 * 1024)
    write_random_file(f"{root}/Film/.DS_Store", 4 * 1024)

    make_sparse_file(f"{root}/DataScience/model.pt", 200 * 1024 * 1024)
    write_random_file(f"{root}/DataScience/train.csv", 50 * 1024 * 1024)
    make_fake_zip(f"{root}/DataScience/notebook.ipynb", 2 * 1024 * 1024)
    write_random_file(f"{root}/DataScience/requirements.txt", 5 * 1024)

    make_fake_zip(f"{root}/Archives/old_backup.zip", 10 * 1024)
    make_fake_zip(f"{root}/Archives/project_photos.rar", 8 * 1024)
    make_fake_zip(f"{root}/Archives/images_2023.tar", 20 * 1024)

    write_random_file(f"{root}/Temp/system_log.log", 500 * 1024)
    write_random_file(f"{root}/Temp/cache.tmp", 100 * 1024)
    write_random_file(f"{root}/Temp/backup.old", 50 * 1024)

    make_fake_image(f"{root}/Images/holiday_photo.jpg", 6 * 1024)
    make_fake_image(f"{root}/Images/screenshot.png", 2 * 1024)

    write_random_file(f"{root}/ProtectedFolder/secret.env", 1 * 1024)
    write_random_file(f"{root}/ProtectedFolder/important.txt", 2 * 1024)
    write_random_file(f"{root}/ProtectedFolder/deep_nested/level1/level2/level3/level4/level5/level6/level7/level8/level9/deep_file.txt", 1 * 1024)


def make_images(root, scale=1):
    ensure_dir(root)
    exts = ["jpg", "png", "webp", "gif", "bmp", "tiff"]
    for i in range(10 * max(1, scale)):
        ext = exts[i % len(exts)]
        size_kb = (i % 10 + 1) * 1024  # 1MB to 10MB
        make_fake_image(f"{root}/photo_{i}.{ext}", size_kb)


def make_videos(root, scale=1):
    ensure_dir(root)
    exts = ["mp4", "mov", "mkv", "avi", "webm"]
    for i in range(5 * max(1, scale)):
        ext = exts[i % len(exts)]
        make_sparse_file(f"{root}/video_{i}.{ext}", (i % 5 + 1) * 100 * 1024 * 1024)


def make_documents(root, scale=1):
    ensure_dir(root)
    for i in range(10 * max(1, scale)):
        make_fake_pdf(f"{root}/document_{i}.pdf", (i % 20 + 1) * 100)
        write_random_file(f"{root}/notes_{i}.txt", (i % 5 + 1) * 10 * 1024)


def make_audio(root, scale=1):
    ensure_dir(root)
    exts = ["mp3", "wav", "m4a", "flac", "ogg"]
    for i in range(8 * max(1, scale)):
        ext = exts[i % len(exts)]
        make_fake_zip(f"{root}/track_{i}.{ext}", (i % 10 + 1) * 1024)


def make_code(root, scale=1):
    ensure_dir(root)
    ensure_dir(f"{root}/Notebooks")
    exts = ["py", "js", "ts", "java", "cpp", "go", "rs", "sh", "css", "html", "json", "yaml", "sql"]
    for i in range(10 * max(1, scale)):
        ext = exts[i % len(exts)]
        write_random_file(f"{root}/file_{i}.{ext}", (i % 5 + 1) * 10 * 1024)
    for i in range(3 * max(1, scale)):
        make_fake_zip(f"{root}/Notebooks/notebook_{i}.ipynb", (i + 1) * 100 * 1024)


def make_archives(root, scale=1):
    ensure_dir(root)
    exts = ["zip", "rar", "7z", "tar", "gz", "bz2", "dmg", "iso"]
    for i in range(8 * max(1, scale)):
        ext = exts[i % len(exts)]
        make_fake_zip(f"{root}/archive_{i}.{ext}", (i % 20 + 1) * 1024)


def make_design(root, scale=1):
    ensure_dir(root)
    exts = ["psd", "ai", "fig", "sketch", "xd", "svg"]
    for i in range(6 * max(1, scale)):
        ext = exts[i % len(exts)]
        make_fake_zip(f"{root}/design_{i}.{ext}", (i % 15 + 1) * 1024)


def make_datasets(root, scale=1):
    ensure_dir(root)
    for i in range(8 * max(1, scale)):
        write_random_file(f"{root}/dataset_{i}.csv", (i % 10 + 1) * 1024 * 1024)
    for i in range(4 * max(1, scale)):
        make_fake_zip(f"{root}/dataset_{i}.parquet", (i % 5 + 1) * 1024 * 1024)


def make_temp(root, scale=1):
    ensure_dir(root)
    for i in range(10 * max(1, scale)):
        write_random_file(f"{root}/temp_{i}.tmp", (i % 5 + 1) * 10 * 1024)
        write_random_file(f"{root}/log_{i}.log", (i % 10 + 1) * 1024)


def make_duplicates(root, scale=1):
    """Create duplicate files (same hash)."""
    ensure_dir(root)
    # Create a source file then copy it multiple times
    src_data = os.urandom(5 * 1024 * 1024)  # 5MB source
    for i in range(5 * max(1, scale)):
        with open(f"{root}/dup_source_{i}.bin", "wb") as f:
            f.write(src_data)
        with open(f"{root}/dup_copy_{i}_{i}.bin", "wb") as f:
            f.write(src_data)


def make_nested(root, scale=1):
    """Create deeply nested directories with files."""
    base = root
    for depth in range(10):
        base = f"{base}/level_{depth}"
        ensure_dir(base)
        for i in range(2):
            write_random_file(f"{base}/file_{i}.txt", (i + 1) * 1024)


def make_unknown(root, scale=1):
    """Files with no extension or unknown types."""
    ensure_dir(root)
    names = ["README", "Makefile", "CHANGELOG", "TODO", "NOTES", "INSTALL", "LICENSE", "AUTHORS"]
    for i in range(len(names) * max(1, scale)):
        name = names[i % len(names)]
        write_random_file(f"{root}/{name}_{i}", (i % 10 + 1) * 1024)


def count_stats(root):
    count = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(root):
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                total_bytes += os.path.getsize(fpath)
                count += 1
            except OSError:
                pass
    return count, total_bytes


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic test workspace for File Organizer")
    parser.add_argument("--output", default=os.path.expanduser("~/test_workspace"),
                        help="Output directory path")
    parser.add_argument("--size-gb", type=int, default=10,
                        help="Fake size in GB (sparse files, uses minimal real storage)")
    parser.add_argument("--categories", default='["images","videos","documents","audio","code","archives","temp","duplicates","nested","unknown","design","datasets"]',
                        help='JSON list of categories to generate')
    args = parser.parse_args()

    output_dir = os.path.expanduser(args.output)
    size_gb = args.size_gb
    categories = json.loads(args.categories)

    # Scale factor: base ~10GB produces ~50-100 files.
    # Scale proportionally for requested size.
    scale = max(1, round(size_gb / 10))

    # Wipe and recreate
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    ensure_dir(output_dir)

    category_map = {
        "images": ("Images", make_images),
        "videos": ("Videos", make_videos),
        "documents": ("Documents", make_documents),
        "audio": ("Audio", make_audio),
        "code": ("Code", make_code),
        "archives": ("Archives", make_archives),
        "temp": ("Temp", make_temp),
        "duplicates": ("Duplicates", make_duplicates),
        "nested": ("Nested", make_nested),
        "unknown": ("Unknown", make_unknown),
        "design": ("Design", make_design),
        "datasets": ("Datasets", make_datasets),
    }

    print(f"Generating workspace at: {output_dir}")
    print(f"Requested size: {size_gb} GB (sparse) | Scale: {scale}x")

    for cat in categories:
        cat_lower = cat.lower()
        if cat_lower in category_map:
            folder, func = category_map[cat_lower]
            print(f"  Building {folder}/ ...")
            func(f"{output_dir}/{folder}", scale)
        else:
            print(f"  Unknown category: {cat} — skipping")

    count, total_bytes = count_stats(output_dir)
    total_mb = total_bytes / (1024 * 1024)
    print(f"\n✅ Created {count} files, {total_mb:.1f}MB total (sparse — minimal real disk used)")
    print(f"   Requested fake size: {size_gb} GB")
    print(f"   Workspace: {output_dir}")


if __name__ == "__main__":
    main()
