from dataclasses import dataclass, field
from typing import List, Optional


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
    icon: str  # emoji
    # PROF-011: user-facing labels for each scope mode
    scope_labels: dict  # e.g. {"global_organize": "Organize across all folders", ...}
    categories: List[str]
    rule_bundle: List[dict]
    allowed_scope_modes: List[str]
    default_scope_mode: str


PROFILES = [
    RunProfile(
        id="generic",
        name="Generic",
        description="Neutral scan with no preset rules. Browse, inspect, and manually decide.",
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


def get_profile(profile_id: str) -> Optional[RunProfile]:
    for p in PROFILES:
        if p.id == profile_id:
            return p
    return None
