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


def apply_template(template: str, file: dict, default_category: str = "Other") -> str:
    """Expand template variables using file metadata."""
    name = file.get("name", "")
    ext = file.get("ext", "")
    name_no_ext = os.path.splitext(name)[0]
    category = CATEGORY_MAP.get(file.get("category", "other"), "Other")

    # Parse modified date
    modified_str = file.get("modified_ts", "")
    year = month = day = ""
    if modified_str:
        try:
            dt = datetime.fromisoformat(modified_str.replace("Z", "+00:00"))
            year = str(dt.year)
            month = f"{dt.month:02d}"
            day = f"{dt.day:02d}"
        except (ValueError, TypeError):
            pass

    replacements = {
        "{category}": category,
        "{subcategory}": "",
        "{name}": name_no_ext,
        "{ext}": ext.lstrip("."),
        "{year}": year,
        "{month}": month,
        "{day}": day,
        "{date}": f"{year}-{month}-{day}" if year else "",
        "{parent}": get_parent_name(file),
        "{tree}": get_tree_name(file),
        "{size_human}": format_size(file.get("size_bytes", 0)),
        "{depth}": str(file.get("depth", 0)),
    }

    result = template
    for var, val in replacements.items():
        result = result.replace(var, val)

    # Clean up double slashes
    while "//" in result:
        result = result.replace("//", "/")

    return result
