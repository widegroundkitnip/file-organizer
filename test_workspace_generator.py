#!/usr/bin/env python3
"""test_workspace_generator.py — Generate synthetic test workspace for File Organizer"""

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
    # Fill with random bytes but respect size
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


def make_downloads(root):
    ensure_dir(root)
    # Images
    make_fake_image(f"{root}/IMG_20240115_143022.jpg", 15 * 1024)       # 15MB
    make_fake_image(f"{root}/IMG_20240203_091145.jpg", 8 * 1024)        # 8MB
    make_fake_image(f"{root}/screenshot_2024-01-15.png", 2 * 1024)      # 2MB
    make_fake_image(f"{root}/Skärmbild_2024-02-10.png", 1 * 1024)       # 1MB (Swedish chars)
    # Documents
    make_fake_pdf(f"{root}/invoice_jan_2024.pdf", 200)                  # 200KB
    write_random_file(f"{root}/notes.txt", 50 * 1024)                    # 50KB
    # Archive
    make_fake_zip(f"{root}/archive_backup.zip", 5 * 1024)               # 5MB
    # Data
    write_random_file(f"{root}/data.csv", 100 * 1024)                   # 100KB
    # Presentation
    make_fake_zip(f"{root}/presentation_final_FINAL.pptx", 3 * 1024)     # 3MB (pptx is zip)
    # Word doc
    make_fake_zip(f"{root}/document.docx", 1 * 1024)                     # 1MB (docx is zip)
    # System/temp
    write_random_file(f"{root}/.DS_Store", 4 * 1024)                    # 4KB
    write_random_file(f"{root}/temp_file.tmp", 10 * 1024)               # 10KB
    # Video (sparse)
    make_sparse_file(f"{root}/large_video.mp4", 600 * 1024 * 1024)      # 600MB sparse
    # No extension
    write_random_file(f"{root}/broken_file_no_extension", 20 * 1024)   # 20KB
    # Dataset
    write_random_file(f"{root}/dataset.csv", 2 * 1024 * 1024)           # 2MB


def make_desktop(root):
    ensure_dir(root)
    make_fake_image(f"{root}/photo.jpg", 4 * 1024)                      # 4MB
    make_fake_image(f"{root}/PICT_0012.jpg", 3 * 1024)                   # 3MB
    make_fake_image(f"{root}/Screenshot 2024-01-20.png", 1 * 1024)       # 1MB
    write_random_file(f"{root}/code_snippet.py", 30 * 1024)             # 30KB
    write_random_file(f"{root}/todo.txt", 5 * 1024)                      # 5KB
    write_random_file(f"{root}/notes.md", 10 * 1024)                     # 10KB
    write_random_file(f"{root}/KEEP_this_file.txt", 5 * 1024)            # 5KB — protected
    write_random_file(f"{root}/.env", 1 * 1024)                          # 1KB — protected output
    write_random_file(f"{root}/output.json", 50 * 1024)                  # 50KB — protected output
    make_fake_zip(f"{root}/notebook.ipynb", 100 * 1024)                  # 100KB (jupyter is json zip)


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

    # Code
    write_random_file(f"{root}/Code/main.py", 20 * 1024)                 # 20KB
    write_random_file(f"{root}/Code/utils.js", 10 * 1024)                # 10KB
    write_random_file(f"{root}/Code/data.ts", 8 * 1024)                  # 8KB
    write_random_file(f"{root}/Code/config.yaml", 5 * 1024)              # 5KB
    ensure_dir(f"{root}/Code/__pycache__")
    write_random_file(f"{root}/Code/__pycache__/cache.pyc", 50 * 1024)  # 50KB

    # Film
    make_fake_pdf(f"{root}/Film/script_v3.pdf", 2 * 1024)               # 2MB
    make_sparse_file(f"{root}/Film/rushes.mov", 800 * 1024 * 1024)      # 800MB sparse
    make_sparse_file(f"{root}/Film/B-Roll.mp4", 400 * 1024 * 1024)      # 400MB sparse
    write_random_file(f"{root}/Film/.DS_Store", 4 * 1024)                # 4KB

    # DataScience
    make_sparse_file(f"{root}/DataScience/model.pt", 200 * 1024 * 1024) # 200MB sparse
    write_random_file(f"{root}/DataScience/train.csv", 50 * 1024 * 1024) # 50MB
    make_fake_zip(f"{root}/DataScience/notebook.ipynb", 2 * 1024 * 1024) # 2MB
    write_random_file(f"{root}/DataScience/requirements.txt", 5 * 1024)  # 5KB

    # Archives
    make_fake_zip(f"{root}/Archives/old_backup.zip", 10 * 1024)          # 10MB
    make_fake_zip(f"{root}/Archives/project_photos.rar", 8 * 1024)       # 8MB
    make_fake_zip(f"{root}/Archives/images_2023.tar", 20 * 1024)         # 20MB

    # Temp
    write_random_file(f"{root}/Temp/system_log.log", 500 * 1024)         # 500KB
    write_random_file(f"{root}/Temp/cache.tmp", 100 * 1024)              # 100KB
    write_random_file(f"{root}/Temp/backup.old", 50 * 1024)              # 50KB

    # Images (already correctly placed — should stay)
    make_fake_image(f"{root}/Images/holiday_photo.jpg", 6 * 1024)        # 6MB
    make_fake_image(f"{root}/Images/screenshot.png", 2 * 1024)           # 2MB

    # ProtectedFolder
    write_random_file(f"{root}/ProtectedFolder/secret.env", 1 * 1024)   # 1KB
    write_random_file(f"{root}/ProtectedFolder/important.txt", 2 * 1024) # 2KB
    write_random_file(f"{root}/ProtectedFolder/deep_nested/level1/level2/level3/level4/level5/level6/level7/level8/level9/deep_file.txt", 1 * 1024)  # 1KB


def main():
    # Wipe and recreate
    if os.path.exists(TEST_ROOT):
        shutil.rmtree(TEST_ROOT)
    ensure_dir(TEST_ROOT)

    print("Building Downloads/ ...")
    make_downloads(f"{TEST_ROOT}/Downloads")
    print("Building Desktop/ ...")
    make_desktop(f"{TEST_ROOT}/Desktop")
    print("Building Projects/ ...")
    make_projects(f"{TEST_ROOT}/Projects")

    # — Known duplicates —
    # We create duplicates by copying the same bytes (same hash).
    # Strategy: open the source, read bytes, write to destination.
    # For small files: actual bytes. For large (sparse): re-generate from same seed.

    print("Creating known duplicate pairs ...")

    # Pair 1: Downloads/IMG_20240115_143022.jpg == Desktop/PICT_0012.jpg (same hash)
    src1 = f"{TEST_ROOT}/Downloads/IMG_20240115_143022.jpg"
    dst1 = f"{TEST_ROOT}/Desktop/PICT_0012.jpg"
    with open(src1, "rb") as sf:
        data = sf.read()
    with open(dst1, "wb") as df:
        df.write(data)

    # Pair 2: Desktop/photo.jpg == Archives/photo_copy.jpg (same hash)
    src2 = f"{TEST_ROOT}/Desktop/photo.jpg"
    dst2 = f"{TEST_ROOT}/Projects/Archives/photo_copy.jpg"
    with open(src2, "rb") as sf:
        data = sf.read()
    with open(dst2, "wb") as df:
        df.write(data)

    # Count files and total size
    count = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(TEST_ROOT):
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                total_bytes += os.path.getsize(fpath)
                count += 1
            except OSError:
                pass

    total_mb = total_bytes / (1024 * 1024)

    # Verify hashes
    h1 = file_hash(src1)
    h1b = file_hash(dst1)
    h2 = file_hash(src2)
    h2b = file_hash(dst2)

    print(f"\n✅ Created {count} files, {total_mb:.1f}MB total (sparse files for large sizes)")
    print(f"\n📋 Known duplicate pairs:")
    print(f"  Pair 1: Downloads/IMG_20240115_143022.jpg ↔ Desktop/PICT_0012.jpg")
    print(f"    Hash match: {h1 == h1b}  ({h1[:16]}...)")
    print(f"  Pair 2: Desktop/photo.jpg ↔ Projects/Archives/photo_copy.jpg")
    print(f"    Hash match: {h2 == h2b}  ({h2[:16]}...)")
    print(f"\nWorkspace: {TEST_ROOT}")


if __name__ == "__main__":
    main()
