"""EXIF date extraction (optional dependency."""
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

def extract_exif_date(path: str):
    """Return EXIF DateTimeOriginal or None."""
    if not HAS_PIL: return None
    try:
        img = Image.open(path)
        exif = img._getexif() or {}
        for tag, val in exif.items():
            if tag in (306, 36867, 36868):
                return str(val)
    except: pass
    return None
