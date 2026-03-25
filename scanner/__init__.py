"""Scanner module — cross-path scanning, duplicate detection, structure analysis."""
from .manifest import ExtendedManifestBuilder, build_cross_manifest
from .duplicate import CrossPathDuplicateFinder
from .structure import StructureAnalyzer
from .project_detect import scan_for_project_roots, projects_to_manifest_format

__all__ = [
    "ExtendedManifestBuilder", "build_cross_manifest",
    "CrossPathDuplicateFinder", "StructureAnalyzer",
    "scan_for_project_roots", "projects_to_manifest_format",
]
