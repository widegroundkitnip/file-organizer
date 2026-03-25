"""
Project detection — scanner-side.
Detects project-like directory roots by marker files/folders.
schema_version 1 output.
"""
import os
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, asdict

# ---------------------------------------------------------------------------
# Marker definitions
# ---------------------------------------------------------------------------

STRONG_MARKERS = {
    ".git", "Cargo.toml", "go.mod",
}
STRONG_EXT_MARKERS = {
    ".xcodeproj", ".uproject", ".blend",
}
MEDIUM_MARKERS = {
    "package.json", "pyproject.toml", "requirements.txt",
    "Gemfile", "Pods/", ".venv/", ".next/", "src/",
}
WEAK_MARKERS = {
    "__pycache__/", ".cache/", "dist/", "build/",
    ".pytest_cache/", "node_modules/",
}

# All markers (dirs have trailing slash in WEAK/MEDIUM that need special handling)
ALL_FILE_MARKERS = STRONG_MARKERS | {m.rstrip("/") for m in MEDIUM_MARKERS | WEAK_MARKERS if m.endswith("/")}
ALL_DIR_MARKERS = {m.rstrip("/") for m in MEDIUM_MARKERS | WEAK_MARKERS if m.endswith("/")}


def _is_project_ext(name: str) -> bool:
    """Check if filename ends with a strong project extension marker."""
    for ext in STRONG_EXT_MARKERS:
        if name.endswith(ext):
            return True
    return False


@dataclass
class ProjectRoot:
    path: str
    relative_path: str
    tree: str
    kind: str
    confidence_score: float
    confidence_label: str
    markers: List[str]
    strong_marker_count: int
    medium_marker_count: int
    weak_marker_count: int
    nested_under: Optional[str]
    depth: int
    recommended_handling: str
    why_detected: str
    schema_version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


def _kind_from_markers(markers: List[str]) -> str:
    """Infer project kind from detected markers."""
    marker_set = {m.lower() for m in markers}
    if any(m.endswith(".xcodeproj") or m == "pods/" for m in marker_set):
        return "code"
    if any(m in {"package.json", "go.mod", "cargo.toml", "go.mod"} for m in marker_set):
        return "code"
    if any(m in {"pyproject.toml", "requirements.txt", ".venv/", "pods/"} for m in marker_set):
        return "code"
    if any(m.endswith(".blend") for m in marker_set):
        return "media"
    if "src/" in marker_set:
        return "code"
    return "workspace"


def _score_to_label(score: float) -> str:
    if score <= 0:
        return "informational"
    if score <= 0.5:
        return "low"
    if score <= 1.4:
        return "medium"
    return "high"


def _recommended_handling(score: float, label: str) -> str:
    if label == "informational":
        return "ignore"
    if label == "low":
        return "warn"
    return "protect_in_project_safe_mode"


def detect_projects_in_dir(dirpath: str, files: Set[str], dirnames: Set[str]) -> Optional[ProjectRoot]:
    """
    Given a directory path and the sets of filenames/dirnames within it,
    return a ProjectRoot if any markers are found, else None.

    We do NOT flag weak-only markers as a signal.
    """
    strong = 0
    medium = 0
    weak = 0
    found_markers: List[str] = []

    # Strong file markers (.git can be a file or directory depending on repo type)
    for m in STRONG_MARKERS:
        if m == ".git":
            if m in files or m in dirnames:
                strong += 1
                found_markers.append(m)
        elif m in files:
            strong += 1
            found_markers.append(m)

    # Strong ext markers
    for f in files:
        if _is_project_ext(f):
            strong += 1
            found_markers.append(f)

    # Medium markers
    for m in MEDIUM_MARKERS:
        base = m.rstrip("/")
        if m in files or base in files:
            medium += 1
            found_markers.append(m)
        elif m in dirnames or base in dirnames:
            medium += 1
            found_markers.append(m)

    # Weak markers (supporting evidence only — never alone creates signal)
    for m in WEAK_MARKERS:
        base = m.rstrip("/")
        if m in files or base in files:
            weak += 1
            found_markers.append(m)
        elif m in dirnames or base in dirnames:
            weak += 1
            found_markers.append(m)

    # No meaningful markers found
    if strong == 0 and medium == 0:
        return None

    # Weak-only = informational signal, not a project
    if strong == 0 and medium == 0 and weak > 0:
        return None

    # Compute confidence score
    # Per spec:
    #   low    (0–0.5): weak-only → no signal, or 1 medium alone
    #   medium (0.6–1.4): 2 medium, or 1 strong + weak
    #   high   (1.5+): 1 strong alone, 2+ strong, 1 strong + 2+ medium
    #
    # Formula: strong=1.0, medium=0.5, weak=0 (supporting only, no score)
    # This satisfies: 1 strong=1.0(low?? no—raise strong to 1.5), 2 strong=3.0(high),
    #   1 strong+2 medium=2.5(high), 2 medium=1.0(medium), 1 medium=0.5(low)
    #
    # Final settled weights (strong=1.5 ensures 1 strong alone=high):
    #   1 strong = 1.5 (high), 1 strong + 1 weak = 1.5 (high), 1 strong + 2 medium = 2.5 (high)
    #   2 medium = 1.0 (medium), 1 medium = 0.5 (low)
    score = strong * 1.5
    score += medium * 0.5
    # Note: weak markers do not add to the numeric score — they are supporting evidence only

    label = _score_to_label(score)
    handling = _recommended_handling(score, label)
    kind = _kind_from_markers(found_markers)
    why = f"Contains project markers: {', '.join(sorted(found_markers))}"

    return ProjectRoot(
        path=dirpath,
        relative_path=os.path.basename(dirpath.rstrip("/")) or dirpath,
        tree="",  # filled in by caller
        kind=kind,
        confidence_score=round(score, 2),
        confidence_label=label,
        markers=sorted(found_markers),
        strong_marker_count=strong,
        medium_marker_count=medium,
        weak_marker_count=weak,
        nested_under=None,  # filled in by caller
        depth=0,  # filled in by caller
        recommended_handling=handling,
        why_detected=why,
        schema_version=1,
    )


def scan_for_project_roots(
    scan_roots: List[str],
    include_hidden: bool = False,
) -> List[ProjectRoot]:
    """
    Walk scan_roots and detect project roots.
    Skips directories that are already under a detected project root
    (no double-reporting nested projects).
    """
    results: List[ProjectRoot] = []
    # Track paths that are under an already-detected project root
    suppressed_paths: Set[str] = set()

    for root in scan_roots:
        root = os.path.abspath(os.path.expanduser(root))
        root_depth = root.count(os.sep)
        tree_name = os.path.basename(root.rstrip("/")) or root

        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Normalize
            dirpath_n = os.path.abspath(dirpath)

            # Skip if this path is inside a previously detected project root
            is_suppressed = any(
                dirpath_n.startswith(s) and dirpath_n != s
                for s in suppressed_paths
            )
            if is_suppressed:
                # Don't descend — the os.walk will still visit children unless we prune
                # We prune to avoid extra work
                dirnames[:] = []
                continue

            files_set = {f for f in filenames if not f.startswith(".") or include_hidden}
            dirs_set = {d for d in dirnames if not d.startswith(".") or include_hidden}

            # Also include hidden if include_hidden=True
            if include_hidden:
                files_set = set(filenames)
                dirs_set = set(dirnames)

            pr = detect_projects_in_dir(dirpath_n, files_set, dirs_set)
            if pr is not None:
                # Determine depth relative to scan root
                depth = dirpath_n.count(os.sep) - root_depth
                rel = os.path.relpath(dirpath_n, root)
                rel_name = rel if rel != "." else os.path.basename(dirpath_n.rstrip("/"))

                pr.tree = tree_name
                pr.relative_path = rel_name
                pr.depth = depth
                pr.nested_under = None  # only set if nested under another detected root

                # If there's a parent in results that contains this, mark it
                for existing in results:
                    if dirpath_n.startswith(existing.path + os.sep):
                        pr.nested_under = existing.path
                        break

                results.append(pr)
                # Suppress children of this detected project
                suppressed_paths.add(dirpath_n)

                # Prune subdirs from walk to save time
                # (only if there are actual subdirs to skip)
                if dirnames:
                    dirnames[:] = []

    return results


def projects_to_manifest_format(projects: List[ProjectRoot]) -> dict:
    """Serialize a list of ProjectRoot into the manifest section format."""
    return {
        "schema_version": 1,
        "detected_project_roots": [p.to_dict() for p in projects],
        "stats": {
            "total_detected": len(projects),
            "by_confidence_label": _stats_by_label(projects),
            "by_kind": _stats_by_kind(projects),
        }
    }


def _stats_by_label(projects: List[ProjectRoot]) -> dict:
    counts: Dict[str, int] = {}
    for p in projects:
        counts[p.confidence_label] = counts.get(p.confidence_label, 0) + 1
    return counts


def _stats_by_kind(projects: List[ProjectRoot]) -> dict:
    counts: Dict[str, int] = {}
    for p in projects:
        counts[p.kind] = counts.get(p.kind, 0) + 1
    return counts
