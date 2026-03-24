import os
import re
from datetime import datetime
from typing import Dict


def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}PB"


def get_parent_name(file: dict) -> str:
    rel = file.get("relative_path", "")
    parts = rel.split("/")
    if len(parts) >= 2:
        return parts[-2]
    return ""


def get_tree_name(file: dict) -> str:
    return file.get("parent_tree", "")


CATEGORY_MAP = {
    "images": "Images",
    "documents": "Documents",
    "video": "Video",
    "audio": "Audio",
    "code": "Code",
    "archives": "Archives",
    "other": "Other",
}


def _parse_date(file: dict) -> tuple:
    """Return (year, month, day, datetime_or_None) from file metadata."""
    modified_str = file.get("modified_ts", "")
    if not modified_str:
        return "", "", "", None
    try:
        dt = datetime.fromisoformat(modified_str.replace("Z", "+00:00"))
        return str(dt.year), f"{dt.month:02d}", f"{dt.day:02d}", dt
    except (ValueError, TypeError):
        return "", "", "", None


def apply_template(template: str, file: dict, default_category: str = "Other") -> str:
    """Expand template variables using file metadata.

    Variables:
        {original}  — original filename including extension
        {ext}       — extension without dot
        {year}      — 4-digit year
        {month}     — 2-digit month
        {day}       — 2-digit day
        {size}      — size in bytes (integer)
        {category}  — category display name
        {name}      — filename without extension
        {date}      — {year}-{month}-{day}
        {date:FORMAT} — strftime format, e.g. {date:%Y-%m} → 2024-03
        {parent}    — parent folder name
        {tree}      — parent tree path
        {size_human} — human-readable size (e.g. 1.5MB)
        {depth}     — depth integer
    """
    name = file.get("name", "")
    ext = file.get("ext", "")
    name_no_ext = os.path.splitext(name)[0]
    file_category = file.get("category", "other")
    category = CATEGORY_MAP.get(file_category, default_category)

    year, month, day, dt = _parse_date(file)

    replacements: Dict[str, str] = {
        "{original}": name,
        "{category}": category,
        "{subcategory}": "",
        "{name}": name_no_ext,
        "{ext}": ext.lstrip("."),
        "{year}": year,
        "{month}": month,
        "{day}": day,
        "{size}": str(file.get("size_bytes", 0)),
        "{date}": f"{year}-{month}-{day}" if year else "",
        "{parent}": get_parent_name(file),
        "{tree}": get_tree_name(file),
        "{size_human}": format_size(file.get("size_bytes", 0)),
        "{depth}": str(file.get("depth", 0)),
    }

    result = template
    for var, val in replacements.items():
        result = result.replace(var, val)

    # Handle {date:FORMAT} patterns — must come after {date} replacement so dt is available
    if dt is not None:
        date_pattern = re.compile(r'\{date:([^}]+)\}')
        result = date_pattern.sub(lambda m: dt.strftime(m.group(1)), result)

    # Clean up double slashes
    while "//" in result:
        result = result.replace("//", "/")

    return result
