from dataclasses import dataclass
from typing import Any, List, Optional


# Extended extension sets (PROF-009)
IMAGE_EXTS = ["jpg", "jpeg", "png", "webp", "gif", "bmp", "tiff", "tif", "heic", "heif", "dng", "arw", "cr2", "nef", "srw", "raw", "raf", "orf", "rw2"]
VIDEO_EXTS = ["mp4", "mov", "mkv", "avi", "flv", "wmv", "webm", "m4v", "mpg", "mpeg", "3gp"]
AUDIO_EXTS = ["mp3", "wav", "flac", "aac", "ogg", "m4a", "wma", "opus", "aiff"]
DOCUMENT_EXTS = ["pdf", "doc", "docx", "txt", "md", "rtf", "odt", "ods", "odp", "xlsx", "xls", "csv", "pptx", "ppt", "pptm"]
CODE_EXTS = ["py", "js", "ts", "jsx", "tsx", "java", "c", "cpp", "h", "hpp", "cs", "go", "rs", "rb", "php", "sh", "bash", "zsh", "css", "scss", "sass", "less", "html", "htm", "xml", "json", "yaml", "yml", "toml", "sql", "r", "ipynb", "swift", "kt", "scala", "lua", "pl", "pm", "sh", "ps1"]
ARCHIVE_EXTS = ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "iso", "dmg", "cab", "deb", "rpm"]


@dataclass
class RunProfile:
    id: str
    name: str
    description: str
    workflow_type: str
    safety_level: str
    profile_origin: str
    icon: str  # emoji
    # PROF-011: user-facing labels for each scope mode
    scope_labels: dict  # e.g. {"global_organize": "Organize across all folders", ...}
    categories: List[str]
    rule_bundle: List[dict]
    allowed_scope_modes: List[str]
    default_scope_mode: str


ALLOWED_WORKFLOW_TYPES = [
    "photo_organizer",
    "document_sorter",
    "dev_cleaner",
    "media_archiver",
    "custom",
]
ALLOWED_SAFETY_LEVELS = ["safe", "standard", "aggressive"]
ALLOWED_PROFILE_ORIGINS = ["builtin", "user"]
ALLOWED_SCOPE_MODES = ["global_organize", "preserve_parent_boundaries", "project_safe_mode"]
DEFAULT_SCOPE_LABELS = {
    "global_organize": "Organize across all folders",
    "preserve_parent_boundaries": "Keep files inside each folder",
    "project_safe_mode": "Protect detected projects",
}


def _slugify_profile_id(text: str) -> str:
    chars = []
    for ch in (text or "").strip().lower():
        if ch.isalnum():
            chars.append(ch)
        else:
            chars.append("_")
    slug = "".join(chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                out.append(cleaned)
    return out


def validate_profile(profile_dict: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(profile_dict, dict):
        return ["profile must be an object"]

    profile_id = profile_dict.get("id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        errors.append("id is required and must be a non-empty string")

    name = profile_dict.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name is required and must be a non-empty string")

    description = profile_dict.get("description")
    if not isinstance(description, str):
        errors.append("description is required and must be a string")

    icon = profile_dict.get("icon")
    if not isinstance(icon, str) or not icon.strip():
        errors.append("icon is required and must be a non-empty string")

    workflow_type = profile_dict.get("workflow_type")
    if workflow_type not in ALLOWED_WORKFLOW_TYPES:
        errors.append(
            f"workflow_type must be one of: {', '.join(ALLOWED_WORKFLOW_TYPES)}"
        )

    safety_level = profile_dict.get("safety_level")
    if safety_level not in ALLOWED_SAFETY_LEVELS:
        errors.append(
            f"safety_level must be one of: {', '.join(ALLOWED_SAFETY_LEVELS)}"
        )

    profile_origin = profile_dict.get("profile_origin")
    if profile_origin not in ALLOWED_PROFILE_ORIGINS:
        errors.append(
            f"profile_origin must be one of: {', '.join(ALLOWED_PROFILE_ORIGINS)}"
        )

    scope_labels = profile_dict.get("scope_labels")
    if not isinstance(scope_labels, dict):
        errors.append("scope_labels must be an object")
    else:
        for scope_mode in ALLOWED_SCOPE_MODES:
            value = scope_labels.get(scope_mode)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"scope_labels must include non-empty label for '{scope_mode}'"
                )

    categories = profile_dict.get("categories")
    if not isinstance(categories, list) or not all(isinstance(x, str) for x in categories):
        errors.append("categories must be a list of strings")

    rule_bundle = profile_dict.get("rule_bundle")
    if not isinstance(rule_bundle, list) or not all(isinstance(x, dict) for x in rule_bundle):
        errors.append("rule_bundle must be a list of rule objects")

    allowed_scope_modes = profile_dict.get("allowed_scope_modes")
    if not isinstance(allowed_scope_modes, list) or not allowed_scope_modes:
        errors.append("allowed_scope_modes must be a non-empty list")
    else:
        invalid_modes = [m for m in allowed_scope_modes if m not in ALLOWED_SCOPE_MODES]
        if invalid_modes:
            errors.append(
                "allowed_scope_modes contains unsupported values: "
                + ", ".join(sorted(set(invalid_modes)))
            )

    default_scope_mode = profile_dict.get("default_scope_mode")
    if not isinstance(default_scope_mode, str) or not default_scope_mode.strip():
        errors.append("default_scope_mode must be a non-empty string")
    elif isinstance(allowed_scope_modes, list) and default_scope_mode not in allowed_scope_modes:
        errors.append("default_scope_mode must be included in allowed_scope_modes")

    return errors


def profile_from_dict(profile_dict: dict, default_origin: str = "user") -> RunProfile:
    name = str(profile_dict.get("name", "")).strip()
    profile_id = str(profile_dict.get("id", "")).strip()
    if not profile_id:
        profile_id = _slugify_profile_id(name) or "user_profile"

    allowed_scope_modes = _clean_string_list(profile_dict.get("allowed_scope_modes"))
    if not allowed_scope_modes:
        allowed_scope_modes = list(ALLOWED_SCOPE_MODES)
    else:
        allowed_scope_modes = [m for m in allowed_scope_modes if m in ALLOWED_SCOPE_MODES]
        if not allowed_scope_modes:
            allowed_scope_modes = list(ALLOWED_SCOPE_MODES)

    raw_scope_labels = profile_dict.get("scope_labels")
    scope_labels = dict(DEFAULT_SCOPE_LABELS)
    if isinstance(raw_scope_labels, dict):
        for key, value in raw_scope_labels.items():
            if isinstance(key, str) and isinstance(value, str) and value.strip():
                scope_labels[key] = value.strip()
    for scope_mode in ALLOWED_SCOPE_MODES:
        scope_labels.setdefault(scope_mode, DEFAULT_SCOPE_LABELS[scope_mode])

    default_scope_mode = str(profile_dict.get("default_scope_mode", "")).strip()
    if default_scope_mode not in allowed_scope_modes:
        default_scope_mode = allowed_scope_modes[0]

    workflow_type = str(profile_dict.get("workflow_type", "custom")).strip()
    if workflow_type not in ALLOWED_WORKFLOW_TYPES:
        workflow_type = "custom"

    safety_level = str(profile_dict.get("safety_level", "standard")).strip()
    if safety_level not in ALLOWED_SAFETY_LEVELS:
        safety_level = "standard"

    profile_origin = str(profile_dict.get("profile_origin", default_origin)).strip()
    if profile_origin not in ALLOWED_PROFILE_ORIGINS:
        profile_origin = default_origin if default_origin in ALLOWED_PROFILE_ORIGINS else "user"

    categories = _clean_string_list(profile_dict.get("categories")) or ["all"]
    rule_bundle_raw = profile_dict.get("rule_bundle")
    rule_bundle = [item for item in rule_bundle_raw if isinstance(item, dict)] if isinstance(rule_bundle_raw, list) else []

    return RunProfile(
        id=profile_id,
        name=name or profile_id,
        description=str(profile_dict.get("description", "")),
        workflow_type=workflow_type,
        safety_level=safety_level,
        profile_origin=profile_origin,
        icon=str(profile_dict.get("icon", "🧩")) or "🧩",
        scope_labels=scope_labels,
        categories=categories,
        rule_bundle=rule_bundle,
        allowed_scope_modes=allowed_scope_modes,
        default_scope_mode=default_scope_mode,
    )


def profile_to_dict(profile: RunProfile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "workflow_type": profile.workflow_type,
        "safety_level": profile.safety_level,
        "profile_origin": profile.profile_origin,
        "icon": profile.icon,
        "scope_labels": dict(profile.scope_labels),
        "categories": list(profile.categories),
        "rule_bundle": list(profile.rule_bundle),
        "allowed_scope_modes": list(profile.allowed_scope_modes),
        "default_scope_mode": profile.default_scope_mode,
    }


PROFILES = [
    RunProfile(
        id="generic",
        name="Generic",
        description="Neutral scan with no preset rules. Browse, inspect, and manually decide.",
        workflow_type="custom",
        safety_level="safe",
        profile_origin="builtin",
        icon="🔍",
        scope_labels={
            "global_organize": "Organize across all folders",
            "preserve_parent_boundaries": "Keep files inside each folder",
            "project_safe_mode": "Protect detected projects",
        },
        categories=["all"],
        rule_bundle=[],
        allowed_scope_modes=["global_organize", "preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="preserve_parent_boundaries",
    ),

    # PROF-012.1 — Downloads Cleanup
    RunProfile(
        id="downloads_cleanup",
        name="Downloads Cleanup",
        description="Tame your Downloads folder — sort files by type and age. Move old files to archive.",
        workflow_type="document_sorter",
        safety_level="standard",
        profile_origin="builtin",
        icon="📥",
        scope_labels={
            "global_organize": "Organize across all folders",
            "preserve_parent_boundaries": "Keep files inside each folder",
            "project_safe_mode": "Protect detected projects",
        },
        categories=["all"],
        rule_bundle=[
            {
                "name": "Recent Images (7d)",
                "filter": {"type": "and", "conditions": [
                    {"type": "extension", "values": IMAGE_EXTS},
                    {"type": "modified_within_days", "value": 7},
                ]},
                "action": "move",
                "destination_template": "Downloads/Recent Images/{name}.{ext}",
                "priority": 10,
            },
            {
                "name": "Recent Videos (7d)",
                "filter": {"type": "and", "conditions": [
                    {"type": "extension", "values": VIDEO_EXTS},
                    {"type": "modified_within_days", "value": 7},
                ]},
                "action": "move",
                "destination_template": "Downloads/Recent Videos/{name}.{ext}",
                "priority": 11,
            },
            {
                "name": "Recent Documents (7d)",
                "filter": {"type": "and", "conditions": [
                    {"type": "extension", "values": DOCUMENT_EXTS},
                    {"type": "modified_within_days", "value": 7},
                ]},
                "action": "move",
                "destination_template": "Downloads/Recent Documents/{name}.{ext}",
                "priority": 12,
            },
            {
                "name": "Archives",
                "filter": {"type": "extension", "values": ARCHIVE_EXTS},
                "action": "move",
                "destination_template": "Downloads/Archives/{name}.{ext}",
                "priority": 20,
            },
            {
                "name": "Images",
                "filter": {"type": "extension", "values": IMAGE_EXTS},
                "action": "move",
                "destination_template": "Downloads/Images/{name}.{ext}",
                "priority": 30,
            },
            {
                "name": "Videos",
                "filter": {"type": "extension", "values": VIDEO_EXTS},
                "action": "move",
                "destination_template": "Downloads/Videos/{name}.{ext}",
                "priority": 31,
            },
            {
                "name": "Documents",
                "filter": {"type": "extension", "values": DOCUMENT_EXTS},
                "action": "move",
                "destination_template": "Downloads/Documents/{name}.{ext}",
                "priority": 32,
            },
            {
                "name": "Code & Scripts",
                "filter": {"type": "extension", "values": CODE_EXTS},
                "action": "move",
                "destination_template": "Downloads/Code/{name}.{ext}",
                "priority": 33,
            },
            {
                "name": "Audio",
                "filter": {"type": "extension", "values": AUDIO_EXTS},
                "action": "move",
                "destination_template": "Downloads/Audio/{name}.{ext}",
                "priority": 34,
            },
        ],
        allowed_scope_modes=["global_organize", "preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="preserve_parent_boundaries",
    ),

    # PROF-012.2 — Duplicates Review
    RunProfile(
        id="duplicates_review",
        name="Duplicates Review",
        description="Find duplicate files across folders. Identify keepers and remove copies.",
        workflow_type="dev_cleaner",
        safety_level="safe",
        profile_origin="builtin",
        icon="🔀",
        scope_labels={
            "global_organize": "Scan across all folders",
            "preserve_parent_boundaries": "Keep files inside each folder",
            "project_safe_mode": "Protect detected projects",
        },
        categories=["all"],
        rule_bundle=[],
        allowed_scope_modes=["global_organize", "preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="global_organize",
    ),

    # PROF-012.3 — Screenshots
    RunProfile(
        id="screenshots",
        name="Screenshots",
        description="Gather all screenshots into one place, organized by month taken.",
        workflow_type="photo_organizer",
        safety_level="standard",
        profile_origin="builtin",
        icon="🖼",
        scope_labels={
            "global_organize": "Collect from all folders",
            "preserve_parent_boundaries": "Keep in current folder",
            "project_safe_mode": "Protect detected projects",
        },
        categories=["images"],
        rule_bundle=[
            {
                "name": "Screenshots by Month",
                "filter": {
                    "type": "any_of",
                    "conditions": [
                        {"type": "name_contains", "values": ["Screenshot", "Skärmbild", "Skärmavbild", "Capture", "screen"]},
                        {"type": "extension", "values": ["png", "jpg", "jpeg"]},
                    ],
                },
                "action": "move",
                "destination_template": "Screenshots/{year}-{month}/{name}.{ext}",
                "priority": 10,
            },
        ],
        allowed_scope_modes=["global_organize", "preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="global_organize",
    ),

    # PROF-012.4 — Camera Import
    RunProfile(
        id="camera_import",
        name="Camera Import",
        description="Organize photos from camera memory cards. Group by date, separate RAW from JPG.",
        workflow_type="photo_organizer",
        safety_level="safe",
        profile_origin="builtin",
        icon="📷",
        scope_labels={
            "global_organize": "Organize across all folders",
            "preserve_parent_boundaries": "Keep files inside each folder",
            "project_safe_mode": "Protect detected projects",
        },
        categories=["images"],
        rule_bundle=[
            {
                "name": "RAW Photos (Camera)",
                "filter": {"type": "extension", "values": ["dng", "arw", "cr2", "nef", "srw", "raf", "orf", "rw2"]},
                "action": "move",
                "destination_template": "Camera/RAW/{year}/{year}-{month}-{day}_{name}.{ext}",
                "priority": 10,
            },
            {
                "name": "Camera JPGs",
                "filter": {
                    "type": "any_of",
                    "conditions": [
                        {"type": "name_contains", "values": ["IMG_", "DSC_", "P00"]},
                        {"type": "extension", "values": ["jpg", "jpeg", "heic", "heif"]},
                    ],
                },
                "action": "move",
                "destination_template": "Camera/Photos/{year}/{year}-{month}-{day}_{name}.{ext}",
                "priority": 11,
            },
            {
                "name": "Videos",
                "filter": {"type": "extension", "values": VIDEO_EXTS},
                "action": "move",
                "destination_template": "Camera/Videos/{year}/{year}-{month}-{day}_{name}.{ext}",
                "priority": 12,
            },
        ],
        allowed_scope_modes=["global_organize", "preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="preserve_parent_boundaries",
    ),

    # PROF-012.5 — Project-Safe Scan
    RunProfile(
        id="project_safe",
        name="Project-Safe Scan",
        description="Scan broadly but never touch files inside project roots (repos, workspaces).",
        workflow_type="dev_cleaner",
        safety_level="safe",
        profile_origin="builtin",
        icon="🛡",
        scope_labels={
            "global_organize": "Scan across all folders",
            "preserve_parent_boundaries": "Keep files inside each folder",
            "project_safe_mode": "Protect detected projects",
        },
        categories=["all"],
        rule_bundle=[
            {
                "name": "Documents",
                "filter": {"type": "extension", "values": DOCUMENT_EXTS},
                "action": "move",
                "destination_template": "Documents/{name}.{ext}",
                "priority": 10,
            },
            {
                "name": "Images",
                "filter": {"type": "extension", "values": IMAGE_EXTS},
                "action": "move",
                "destination_template": "Images/{name}.{ext}",
                "priority": 11,
            },
            {
                "name": "Archives",
                "filter": {"type": "extension", "values": ARCHIVE_EXTS},
                "action": "move",
                "destination_template": "Archives/{name}.{ext}",
                "priority": 12,
            },
        ],
        allowed_scope_modes=["global_organize", "preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="project_safe_mode",
    ),

    # PROF-012.6 — Mixed Type Sort
    RunProfile(
        id="mixed_sort",
        name="Mixed Type Sort",
        description="Organize a mixed folder by type and date. Good for Downloads, Desktop, or project dumps.",
        workflow_type="media_archiver",
        safety_level="standard",
        profile_origin="builtin",
        icon="🗂",
        scope_labels={
            "global_organize": "Organize across all folders",
            "preserve_parent_boundaries": "Keep files inside each folder",
            "project_safe_mode": "Protect detected projects",
        },
        categories=["all"],
        rule_bundle=[
            {
                "name": "Images by Month",
                "filter": {"type": "extension", "values": IMAGE_EXTS},
                "action": "move",
                "destination_template": "Images/{year}/{year}-{month}/{name}.{ext}",
                "priority": 10,
            },
            {
                "name": "Videos by Month",
                "filter": {"type": "extension", "values": VIDEO_EXTS},
                "action": "move",
                "destination_template": "Videos/{year}/{year}-{month}/{name}.{ext}",
                "priority": 11,
            },
            {
                "name": "Documents by Month",
                "filter": {"type": "extension", "values": DOCUMENT_EXTS},
                "action": "move",
                "destination_template": "Documents/{year}/{year}-{month}/{name}.{ext}",
                "priority": 12,
            },
            {
                "name": "Audio by Month",
                "filter": {"type": "extension", "values": AUDIO_EXTS},
                "action": "move",
                "destination_template": "Audio/{year}/{year}-{month}/{name}.{ext}",
                "priority": 13,
            },
            {
                "name": "Code",
                "filter": {"type": "extension", "values": CODE_EXTS},
                "action": "move",
                "destination_template": "Code/{ext}/{name}.{ext}",
                "priority": 14,
            },
            {
                "name": "Archives",
                "filter": {"type": "extension", "values": ARCHIVE_EXTS},
                "action": "move",
                "destination_template": "Archives/{name}.{ext}",
                "priority": 15,
            },
        ],
        allowed_scope_modes=["global_organize", "preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="global_organize",
    ),

    # PROF-012.7 — Review Only
    RunProfile(
        id="review_only",
        name="Review Only",
        description="Deep scan to surface duplicates, unknowns, and structural issues. No rules fire.",
        workflow_type="custom",
        safety_level="safe",
        profile_origin="builtin",
        icon="📋",
        scope_labels={
            "global_organize": "Scan across all folders",
            "preserve_parent_boundaries": "Keep files inside each folder",
            "project_safe_mode": "Protect detected projects",
        },
        categories=["all"],
        rule_bundle=[],
        allowed_scope_modes=["global_organize", "preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="preserve_parent_boundaries",
    ),
]


def iter_profiles(user_profiles: Optional[list[dict]] = None) -> list[RunProfile]:
    merged = list(PROFILES)
    for raw in user_profiles or []:
        if not isinstance(raw, dict):
            continue
        if validate_profile(raw):
            continue
        merged.append(profile_from_dict(raw, default_origin="user"))
    return merged


def get_profile(profile_id: str, user_profiles: Optional[list[dict]] = None) -> Optional[RunProfile]:
    for p in iter_profiles(user_profiles):
        if p.id == profile_id:
            return p
    return None
