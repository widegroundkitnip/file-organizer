"""Scanner module — cross-path scanning, duplicate detection, structure analysis."""
from .manifest import ExtendedManifestBuilder, build_cross_manifest
from .duplicate import CrossPathDuplicateFinder
from .structure import StructureAnalyzer

__all__ = ["ExtendedManifestBuilder", "build_cross_manifest", "CrossPathDuplicateFinder", "StructureAnalyzer"]
