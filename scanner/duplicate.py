from collections import defaultdict
from typing import List, Dict
from .manifest import ScannedFile


def levenshtein_distance(s1: str, s2: str) -> int:
    """Simple Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def filename_similarity(name1: str, name2: str) -> float:
    """Returns a similarity ratio 0.0 to 1.0 based on filename."""
    n1 = name1.rsplit(".", 1)[0].lower()
    n2 = name2.rsplit(".", 1)[0].lower()
    if n1 == n2:
        return 1.0
    max_len = max(len(n1), len(n2))
    if max_len == 0:
        return 1.0
    dist = levenshtein_distance(n1, n2)
    return 1.0 - (dist / max_len)


def size_similar(size1: int, size2: int, tolerance_pct: float = 0.05) -> bool:
    """True if sizes are within tolerance_pct of each other."""
    if size1 == 0 or size2 == 0:
        return size1 == size2
    max_s = max(size1, size2)
    min_s = min(size1, size2)
    return (max_s - min_s) / max_s <= tolerance_pct


def recommend_keeper(files: list) -> dict:
    """
    SPRINT-10: Recommend the best keeper file from a duplicate group.

    Scoring factors (per LOCKED spec):
    - Newest modified time (highest weight)
    - Largest file size
    - Richest metadata (has EXIF, camera info, etc.)
    - Preferred folder/root (outside temp/trash)
    - Shortest/cleanest path

    Returns:
        keeper_path (str)
        reason (str)
        scores (dict of path -> score breakdown)
    """
    if not files:
        return {"keeper_path": "", "reason": "No files in group", "scores": {}}

    # Normalize to dict form
    def to_dict(f) -> dict:
        if isinstance(f, dict):
            return f
        return {
            "path": getattr(f, "path", ""),
            "name": getattr(f, "name", ""),
            "size_bytes": getattr(f, "size_bytes", 0),
            "mtime": getattr(f, "mtime", 0.0),
            "ctime": getattr(f, "ctime", 0.0),
            "relative_path": getattr(f, "relative_path", ""),
            "parent_tree": getattr(f, "parent_tree", ""),
            "extension": getattr(f, "ext") or getattr(f, "extension", ""),
            "classification": getattr(f, "classification", "known"),
        }

    scored: list[tuple[str, float, str]] = []  # (path, score, reason)

    # Collect scores per file
    all_scores: dict[str, dict] = {}
    for f in files:
        d = to_dict(f)
        path = d["path"]
        scores: dict[str, float] = {}

        # 1. Modified time score (0–1, newest = 1.0)
        mtime = d.get("mtime", 0.0)
        scores["modified_time"] = mtime  # raw mtime

        # 2. Size score — largest wins normalization
        size = d.get("size_bytes", 0)
        scores["size"] = size

        # 3. Path cleanliness score (fewer path segments = cleaner, prefer short)
        rel = d.get("relative_path", "")
        depth = rel.count("/") + (1 if rel else 0)
        scores["path_depth"] = depth  # lower = cleaner

        # 4. Location quality: outside temp/trash = better
        path_lower = path.lower()
        in_temp = any(
            seg in path_lower
            for seg in ("/tmp/", "/temp/", "temp\\", "trash", "/trash/")
        )
        scores["location_quality"] = 0.0 if in_temp else 1.0

        # 5. Preferred root/folder: prefer files that are in a structured tree vs deep nested
        tree = d.get("parent_tree", "")
        scores["has_tree"] = 1.0 if tree else 0.0

        all_scores[path] = scores

    # Normalize each factor to 0–1 and compute weighted total
    if not all_scores:
        return {"keeper_path": files[0]["path"] if isinstance(files[0], dict) else str(files[0]), "reason": "Single file", "scores": {}}

    max_mtime = max(s.get("modified_time", 0) for s in all_scores.values())
    max_size = max(s.get("size", 0) for s in all_scores.values())
    max_depth = max(s.get("path_depth", 1) for s in all_scores.values()) or 1

    # Weights per LOCKED spec
    WEIGHTS = {
        "modified_time": 0.30,
        "size": 0.20,
        "path_depth": 0.15,
        "location_quality": 0.20,
        "has_tree": 0.15,
    }

    totals: dict[str, float] = {}
    for path, scores in all_scores.items():
        mtime_norm = scores["modified_time"] / max_mtime if max_mtime > 0 else 0.0
        size_norm = scores["size"] / max_size if max_size > 0 else 0.0
        depth_norm = 1.0 - (scores["path_depth"] / max_depth) if max_depth > 0 else 1.0
        location_norm = scores["location_quality"]
        tree_norm = scores["has_tree"]

        total = (
            WEIGHTS["modified_time"] * mtime_norm
            + WEIGHTS["size"] * size_norm
            + WEIGHTS["path_depth"] * depth_norm
            + WEIGHTS["location_quality"] * location_norm
            + WEIGHTS["has_tree"] * tree_norm
        )
        totals[path] = total

    keeper_path = max(totals, key=lambda p: totals[p])

    # Build human-readable reason
    kscores = all_scores[keeper_path]
    reasons: list[str] = []
    if kscores["modified_time"] == max_mtime and max_mtime > 0:
        reasons.append("newest modified time")
    if kscores["size"] == max_size and max_size > 0:
        reasons.append("largest file")
    if kscores["location_quality"] == 1.0:
        reasons.append("outside temp/trash")
    if kscores["path_depth"] == 0:
        reasons.append("shortest path")
    if kscores["has_tree"] == 1.0:
        reasons.append("inside organized folder")
    if not reasons:
        reasons.append("best overall score")

    return {
        "keeper_path": keeper_path,
        "reason": "Recommended: " + ", ".join(reasons),
        "scores": {p: round(totals[p], 4) for p in totals},
    }


def find_similar_duplicates(
    files: list,
    similarity_threshold: float = 0.75,
    size_tolerance: float = 0.05,
) -> list:
    """Find Tier 3 similar duplicates from a list of files."""
    by_ext = defaultdict(list)
    for f in files:
        ext = (f.get("extension") or f.get("ext") or "").lower()
        if ext:
            by_ext[ext].append(f)

    groups = []
    used = set()

    for ext_files in by_ext.values():
        if len(ext_files) < 2:
            continue
        for i, f1 in enumerate(ext_files):
            f1_path = f1.get("path")
            if not f1_path or f1_path in used:
                continue
            group = {"tier": "similar", "files": [f1], "similarity": 1.0}
            used.add(f1_path)

            for f2 in ext_files[i + 1:]:
                f2_path = f2.get("path")
                if not f2_path or f2_path in used:
                    continue
                name1 = f1.get("name", "")
                name2 = f2.get("name", "")
                size1 = f1.get("size", f1.get("size_bytes", 0))
                size2 = f2.get("size", f2.get("size_bytes", 0))
                # Skip zero-size files — they are always identical and carry no meaning
                if size1 == 0 or size2 == 0:
                    continue
                sim = filename_similarity(name1, name2)
                size_ok = size_similar(size1, size2, size_tolerance)

                if sim >= similarity_threshold and size_ok:
                    group["files"].append(f2)
                    group["similarity"] = min(group["similarity"], sim)
                    used.add(f2_path)

            if len(group["files"]) > 1:
                groups.append(group)
            else:
                used.discard(f1_path)

    return groups


class DuplicateGroup:
    def __init__(self, group_id: int, tier: str, files: List[ScannedFile]):
        self.group_id = group_id
        self.tier = tier  # exact | likely | similar
        self.files = files

    @staticmethod
    def _attr(f, attr):
        return f[attr] if isinstance(f, dict) else getattr(f, attr)

    def to_dict(self) -> dict:
        # SPRINT-10: include keeper recommendation
        rec = recommend_keeper(self.files)
        return {
            "group_id": self.group_id,
            "tier": self.tier,
            "files": [self._attr(f, "path") for f in self.files],
            "shared_subpath": self._shared_subpath(),
            "trees": list(set(self._attr(f, "parent_tree") for f in self.files)),
            "total_size": sum(self._attr(f, "size_bytes") for f in self.files),
            "wasted_space": sum(self._attr(f, "size_bytes") for f in self.files[1:]),
            # SPRINT-10: keeper recommendation
            "keeper_recommendation": {
                "keeper_path": rec["keeper_path"],
                "reason": rec["reason"],
            },
        }

    def _shared_subpath(self) -> str:
        """Find the common relative path between all files."""
        if not self.files:
            return ""
        paths = [self._attr(f, "relative_path") for f in self.files]
        common = paths[0]
        for p in paths[1:]:
            while not p.startswith(common.rsplit("/", 1)[0] + "/") and common:
                common = common.rsplit("/", 1)[0]
        return common

class CrossPathDuplicateFinder:
    def __init__(self, files: List[ScannedFile]):
        self.files = files
        self.groups: List[DuplicateGroup] = []
        self.tier1_groups: List[DuplicateGroup] = []
        self.tier2_groups: List[DuplicateGroup] = []
        self.tier3_groups: List[dict] = []

    def find(self) -> dict:
        self.groups = []
        self.tier1_groups = []
        self.tier2_groups = []
        self.tier3_groups = []
        self._find_exact()
        self._find_likely()
        self._find_similar()
        return self._build_result()

    @staticmethod
    def _get(f, attr):
        """Get attribute from either a dict or a ScannedFile object."""
        return f[attr] if isinstance(f, dict) else getattr(f, attr)

    def _find_exact(self):
        """Tier 1: same hash (SHA256). Skip zero-size files."""
        by_hash = defaultdict(list)
        for f in self.files:
            h = self._get(f, "hash")
            size = self._get(f, "size_bytes")
            if h and size > 0:
                by_hash[h].append(f)
        gid = len(self.groups)
        for h, group_files in by_hash.items():
            if len(group_files) < 2:
                continue
            group = DuplicateGroup(gid, "exact", group_files)
            self.groups.append(group)
            self.tier1_groups.append(group)
            gid += 1

    def _find_likely(self):
        """Tier 2: same name + same size, no hash (skip zero-size files)."""
        by_name_size = defaultdict(list)
        for f in self.files:
            h = self._get(f, "hash")
            cls = self._get(f, "classification")
            size = self._get(f, "size_bytes")
            if not h and cls == "known" and size > 0:
                key = (self._get(f, "name"), self._get(f, "size_bytes"))
                by_name_size[key].append(f)
        gid = len(self.groups)
        for key, group_files in by_name_size.items():
            if len(group_files) < 2:
                continue
            # Skip if already in an exact group
            existing_paths = set()
            for g in self.groups:
                for gf in g.files:
                    existing_paths.add(self._get(gf, "path"))
            filtered = [f for f in group_files if self._get(f, "path") not in existing_paths]
            if len(filtered) < 2:
                continue
            group = DuplicateGroup(gid, "likely", filtered)
            self.groups.append(group)
            self.tier2_groups.append(group)
            gid += 1

    def _find_similar(self):
        """Tier 3: same extension + similar filename + similar size."""
        existing_paths = {
            self._get(gf, "path")
            for g in self.groups
            for gf in g.files
        }
        candidates = [f for f in self.files if self._get(f, "path") not in existing_paths]
        normalized = [self._to_file_dict(f) for f in candidates]
        self.tier3_groups = find_similar_duplicates(normalized)

    @staticmethod
    def _to_file_dict(f) -> dict:
        ext = f.get("ext") if isinstance(f, dict) else getattr(f, "ext")
        return {
            "path": CrossPathDuplicateFinder._get(f, "path"),
            "name": CrossPathDuplicateFinder._get(f, "name"),
            "size": CrossPathDuplicateFinder._get(f, "size_bytes"),
            "size_bytes": CrossPathDuplicateFinder._get(f, "size_bytes"),
            "extension": ext,
            "ext": ext,
            "relative_path": CrossPathDuplicateFinder._get(f, "relative_path"),
            "parent_tree": CrossPathDuplicateFinder._get(f, "parent_tree"),
            "classification": CrossPathDuplicateFinder._get(f, "classification"),
        }

    def _serialize_group(self, group: DuplicateGroup) -> dict:
        # SPRINT-10: include keeper recommendation
        rec = recommend_keeper(group.files)
        files = [self._to_file_dict(f) for f in group.files]
        return {
            "group_id": group.group_id,
            "tier": group.tier,
            "files": files,
            "shared_subpath": group._shared_subpath(),
            "trees": list(set(self._get(f, "parent_tree") for f in group.files)),
            "total_size": sum(self._get(f, "size_bytes") for f in group.files),
            "wasted_space": sum(self._get(f, "size_bytes") for f in group.files[1:]),
            # SPRINT-10: keeper recommendation
            "keeper_recommendation": {
                "keeper_path": rec["keeper_path"],
                "reason": rec["reason"],
            },
        }

    def _build_result(self) -> dict:
        tier1 = [self._serialize_group(g) for g in self.tier1_groups]
        tier2 = [self._serialize_group(g) for g in self.tier2_groups]
        # SPRINT-10: add keeper recommendation to Tier 3 similar groups
        tier3 = []
        for g in self.tier3_groups:
            rec = recommend_keeper(g.get("files", []))
            g_copy = dict(g)
            g_copy["keeper_recommendation"] = {
                "keeper_path": rec["keeper_path"],
                "reason": rec["reason"],
            }
            tier3.append(g_copy)
        duplicate_groups = tier1 + tier2 + tier3
        return {
            "tier1": tier1,
            "tier2": tier2,
            "tier3": tier3,
            "duplicate_groups": duplicate_groups,
            "stats": {
                "total_groups": len(duplicate_groups),
                "exact_count": len(tier1),
                "likely_count": len(tier2),
                "similar_count": len(tier3),
                "total_wasted_space": sum(g["wasted_space"] for g in (tier1 + tier2)),
            }
        }
