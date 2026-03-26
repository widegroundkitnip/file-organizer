import os
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any


ILLEGAL_PATH_CHARS_RE = re.compile(r'[<>:"|?*\x00]')
PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
TRAVERSAL_RE = re.compile(r"(^|[\\/])\.\.([\\/]|$)")


SUPPORTED_VARS = {
    "name",
    "ext",
    "size",
    "year",
    "month",
    "date",
    "mime_cat",
    "hash",
    "counter",
    "original",
}

# Backward-compatibility variables used elsewhere in existing rules/templates.
COMPAT_VARS = {
    "category",
    "subcategory",
    "day",
    "parent",
    "tree",
    "size_human",
    "depth",
}


CATEGORY_MAP = {
    "images": "Images",
    "documents": "Documents",
    "video": "Video",
    "audio": "Audio",
    "code": "Code",
    "archives": "Archives",
    "other": "Other",
}

ALL_VARS = SUPPORTED_VARS | COMPAT_VARS


def format_size(size_bytes: int) -> str:
    size = float(max(0, int(size_bytes or 0)))
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PB"


def get_parent_name(file: dict) -> str:
    rel = str(file.get("relative_path", "") or "")
    parts = rel.replace("\\", "/").split("/")
    if len(parts) >= 2:
        return parts[-2]
    return ""


def get_tree_name(file: dict) -> str:
    return str(file.get("parent_tree", "") or "")


def _as_file_dict(file_obj: Any) -> dict[str, Any]:
    if isinstance(file_obj, dict):
        return file_obj
    if is_dataclass(file_obj):
        return asdict(file_obj)
    if hasattr(file_obj, "__dict__"):
        return dict(vars(file_obj))
    return {}


def _parse_datetime(raw: Any) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None

    formats = (
        None,  # ISO parser path
        "%Y:%m:%d %H:%M:%S",  # common EXIF format
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            if fmt is None:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            return datetime.strptime(text, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _mime_category(mime_type: str) -> str:
    mtype = (mime_type or "").strip().lower()
    if "/" not in mtype:
        return ""
    major = mtype.split("/", 1)[0]
    return major or ""


def _size_category(size_bytes: int) -> str:
    size = max(0, int(size_bytes or 0))
    if size < 100 * 1024:
        return "tiny"
    if size < 1024 * 1024:
        return "small"
    if size < 10 * 1024 * 1024:
        return "medium"
    if size < 100 * 1024 * 1024:
        return "large"
    return "huge"


def _default_counter(counter: int | None) -> str:
    if counter is None:
        return "001"
    try:
        value = int(counter)
    except (TypeError, ValueError):
        text = str(counter).strip()
        return text or "001"
    return f"{value:03d}"


def _truncate_filename(name: str, max_len: int) -> str:
    if len(name) <= max_len:
        return name
    stem, ext = os.path.splitext(name)
    if ext and len(ext) < max_len:
        keep = max_len - len(ext)
        if keep <= 0:
            return name[:max_len]
        return f"{stem[:keep]}{ext}"
    return name[:max_len]


def _sanitize_path(path: str, replace_spaces_with_underscores: bool, max_filename_len: int) -> str:
    text = (path or "").replace("\x00", "")
    text = text.replace("\\", "/")
    text = re.sub(r"/+", "/", text)

    sanitized_parts: list[str] = []
    for raw_part in text.split("/"):
        raw_trimmed = raw_part.strip()
        if raw_trimmed in {"", ".", ".."}:
            continue
        part = ILLEGAL_PATH_CHARS_RE.sub("_", raw_part).strip()
        if replace_spaces_with_underscores:
            part = re.sub(r"\s+", "_", part)
        part = part.replace("..", "_")
        if part in {"", ".", ".."}:
            continue
        sanitized_parts.append(part)

    if not sanitized_parts:
        return "untitled"

    sanitized_parts[-1] = _truncate_filename(sanitized_parts[-1], max_filename_len)
    result = "/".join(sanitized_parts)
    result = result.replace("../", "").replace("..\\", "")
    return result.lstrip("/") or "untitled"


class TemplateEngine:
    def __init__(self, replace_spaces_with_underscores: bool = False, max_filename_len: int = 200):
        self.replace_spaces_with_underscores = replace_spaces_with_underscores
        self.max_filename_len = max_filename_len

    def build_context(self, file_obj: Any, counter: int | None = None, default_category: str = "Other") -> dict[str, str]:
        file_data = _as_file_dict(file_obj)

        original = str(file_data.get("name") or "")
        if not original:
            original = os.path.basename(str(file_data.get("path") or "")) or os.path.basename(str(file_data.get("relative_path") or ""))

        ext = str(file_data.get("ext") or "").lstrip(".")
        if not ext and original:
            ext = os.path.splitext(original)[1].lstrip(".")

        name = os.path.splitext(original)[0] if original else ""

        dt = _parse_datetime(file_data.get("exif_date_taken")) or _parse_datetime(file_data.get("modified_ts"))
        year = f"{dt.year:04d}" if dt else ""
        month = f"{dt.month:02d}" if dt else ""
        day = f"{dt.day:02d}" if dt else ""
        date = f"{year}-{month}-{day}" if dt else ""

        size_bytes = file_data.get("size_bytes") or 0
        try:
            size_as_int = int(size_bytes)
        except (TypeError, ValueError):
            size_as_int = 0
        size = _size_category(size_as_int)

        category_key = str(file_data.get("category") or "other").lower()
        category = CATEGORY_MAP.get(category_key, default_category)

        hash_value = str(file_data.get("hash") or "")[:8]
        mime_cat = _mime_category(str(file_data.get("mime_type") or ""))
        counter_value = _default_counter(counter)

        return {
            "name": name,
            "ext": ext,
            "size": size,
            "year": year,
            "month": month,
            "date": date,
            "mime_cat": mime_cat,
            "hash": hash_value,
            "counter": counter_value,
            "original": original,
            # compatibility values
            "category": category,
            "subcategory": "",
            "day": day,
            "parent": get_parent_name(file_data),
            "tree": get_tree_name(file_data),
            "size_human": format_size(size_as_int),
            "depth": str(file_data.get("depth") or 0),
            "_dt": dt.isoformat() if dt else "",
        }

    def _resolve_token(self, token: str, context: dict[str, str]) -> str:
        content = token.strip()
        fallback = None
        if "|" in content:
            left, right = content.split("|", 1)
            content = left.strip()
            fallback = right

        var_name = content
        fmt = None
        if ":" in content:
            var_name, fmt = content.split(":", 1)
            var_name = var_name.strip()
            fmt = fmt.strip()

        value = context.get(var_name, "")
        if fmt and value:
            if var_name == "counter" and fmt.isdigit():
                value = value.zfill(int(fmt))
            elif var_name == "hash" and fmt.isdigit():
                value = value[: int(fmt)]
            elif var_name == "date":
                dt = _parse_datetime(context.get("_dt"))
                if dt is not None:
                    try:
                        value = dt.strftime(fmt)
                    except ValueError:
                        pass

        if not value and fallback is not None:
            value = fallback

        return str(value or "")

    def render(
        self,
        template_str: str,
        file_obj: Any,
        counter: int | None = None,
        default_category: str = "Other",
        replace_spaces_with_underscores: bool | None = None,
    ) -> str:
        context = self.build_context(file_obj, counter=counter, default_category=default_category)
        rendered = PLACEHOLDER_RE.sub(lambda m: self._resolve_token(m.group(1), context), template_str or "")
        replace_spaces = self.replace_spaces_with_underscores if replace_spaces_with_underscores is None else replace_spaces_with_underscores
        return _sanitize_path(rendered, replace_spaces, self.max_filename_len)


def _template_tokens(template_str: str) -> list[tuple[str, str | None]]:
    tokens: list[tuple[str, str | None]] = []
    for match in PLACEHOLDER_RE.finditer(template_str or ""):
        token = match.group(1).strip()
        fallback = None
        if "|" in token:
            token, fallback = token.split("|", 1)
            token = token.strip()
        if ":" in token:
            token = token.split(":", 1)[0].strip()
        tokens.append((token, fallback))
    return tokens


def validate_template(template_str: str) -> list[str]:
    issues: list[str] = []
    template = template_str or ""

    if not template.strip():
        return ["ERROR: template is empty."]

    if "\x00" in template:
        issues.append("ERROR: template contains null bytes.")
    if TRAVERSAL_RE.search(template):
        issues.append("ERROR: template contains unsafe traversal pattern ('..').")
    if template.lstrip().startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", template.strip()):
        issues.append("WARNING: template looks like an absolute path; relative paths are safer.")
    literal_only = re.sub(r"\{[^{}]+\}", "", template)
    if ILLEGAL_PATH_CHARS_RE.search(literal_only):
        issues.append("WARNING: template includes illegal path characters that will be sanitized.")

    tokens = _template_tokens(template)
    if not tokens:
        if not re.search(r"[A-Za-z0-9]", template):
            issues.append("WARNING: template may sanitize to an empty result.")
        return issues

    for var_name, fallback in tokens:
        if var_name not in ALL_VARS:
            issues.append(f"WARNING: unknown template variable '{{{var_name}}}'.")
        if fallback is not None and ("{" in fallback or "}" in fallback):
            issues.append(f"WARNING: fallback for '{{{var_name}}}' should be a single literal value.")

    maybe_empty = {"ext", "year", "month", "date", "mime_cat", "hash", "day", "parent", "tree", "subcategory"}
    all_risky = all(var in maybe_empty and not fallback for var, fallback in tokens)
    only_placeholders = not re.sub(r"\{[^{}]+\}", "", template).strip()
    if all_risky and only_placeholders:
        issues.append("WARNING: template may resolve to empty output for files missing optional metadata.")

    return issues


def explain_template(template_str: str, sample_file: Any) -> str:
    engine = TemplateEngine()
    file_data = _as_file_dict(sample_file)
    source = (
        str(file_data.get("path") or "")
        or str(file_data.get("relative_path") or "")
        or str(file_data.get("name") or "")
        or "<unknown>"
    )
    preview = engine.render(template_str, sample_file)
    issues = validate_template(template_str)
    explanation = f'Using template "{template_str}" maps "{source}" -> "{preview}"'
    if issues:
        return explanation + " | Notes: " + "; ".join(issues)
    return explanation


def apply_template(template: str, file: Any, default_category: str = "Other") -> str:
    """Backward-compatible helper used by planner.engine."""
    engine = TemplateEngine()
    return engine.render(template, file, default_category=default_category)
