from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RunProfile:
    id: str
    name: str
    description: str
    icon: str  # emoji
    categories: List[str]
    rule_bundle: List[dict]
    allowed_scope_modes: List[str]
    default_scope_mode: str


PROFILES = [
    RunProfile(
        id="generic",
        name="Generic",
        description="Neutral scan with no preset rules.",
        icon="🔍",
        categories=["all"],
        rule_bundle=[],
        allowed_scope_modes=["global_organize", "preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="preserve_parent_boundaries",
    ),
    RunProfile(
        id="images",
        name="Images",
        description="Organize image files: photos, screenshots, camera shots.",
        icon="🖼",
        categories=["images"],
        rule_bundle=[
            {
                "name": "Images",
                "filter": {"type": "extension", "values": ["jpg", "jpeg", "png", "webp", "heic", "gif", "bmp", "tiff", "raw"]},
                "action": "move",
                "destination_template": "Images/{name}.{ext}",
                "priority": 10,
            },
            {
                "name": "Screenshots",
                "filter": {"type": "name_contains", "values": ["Screenshot", "Skärmbild"]},
                "action": "move",
                "destination_template": "Images/Screenshots/{name}.{ext}",
                "priority": 5,
            },
            {
                "name": "Camera Photos",
                "filter": {
                    "type": "any_of",
                    "conditions": [
                        {"type": "name_contains", "values": ["IMG_"]},
                        {"type": "name_contains", "values": ["DSC_"]},
                    ],
                },
                "action": "move",
                "destination_template": "Images/Camera/{name}.{ext}",
                "priority": 6,
            },
        ],
        allowed_scope_modes=["preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="preserve_parent_boundaries",
    ),
    RunProfile(
        id="videos",
        name="Videos",
        description="Organize video files.",
        icon="🎬",
        categories=["videos"],
        rule_bundle=[
            {
                "name": "Videos",
                "filter": {"type": "extension", "values": ["mp4", "mov", "mkv", "avi", "webm", "m4v"]},
                "action": "move",
                "destination_template": "Videos/{name}.{ext}",
                "priority": 10,
            },
        ],
        allowed_scope_modes=["preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="preserve_parent_boundaries",
    ),
    RunProfile(
        id="documents",
        name="Documents",
        description="Organize documents.",
        icon="📄",
        categories=["documents"],
        rule_bundle=[
            {
                "name": "Documents",
                "filter": {"type": "extension", "values": ["pdf", "doc", "docx", "txt", "md", "rtf", "odt", "xlsx", "xls", "pptx", "ppt"]},
                "action": "move",
                "destination_template": "Documents/{name}.{ext}",
                "priority": 10,
            },
        ],
        allowed_scope_modes=["preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="preserve_parent_boundaries",
    ),
    RunProfile(
        id="duplicates",
        name="Duplicates",
        description="Find and remove duplicate files.",
        icon="🔀",
        categories=["duplicates"],
        rule_bundle=[],
        allowed_scope_modes=["preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="preserve_parent_boundaries",
    ),
    RunProfile(
        id="code",
        name="Code",
        description="Organize code files.",
        icon="💻",
        categories=["code"],
        rule_bundle=[
            {
                "name": "Code",
                "filter": {"type": "extension", "values": ["py", "js", "ts", "jsx", "tsx", "java", "c", "cpp", "cs", "go", "rs", "sh", "bash", "css", "html", "yaml", "yml", "json", "sql"]},
                "action": "move",
                "destination_template": "Code/{name}.{ext}",
                "priority": 10,
            },
            {
                "name": "Notebooks",
                "filter": {"type": "extension", "values": ["ipynb"]},
                "action": "move",
                "destination_template": "Code/Notebooks/{name}.{ext}",
                "priority": 11,
            },
        ],
        allowed_scope_modes=["preserve_parent_boundaries", "project_safe_mode"],
        default_scope_mode="project_safe_mode",
    ),
]


def get_profile(profile_id: str) -> Optional[RunProfile]:
    for p in PROFILES:
        if p.id == profile_id:
            return p
    return None
