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
        return {
            "group_id": self.group_id,
            "tier": self.tier,
            "files": [self._attr(f, "path") for f in self.files],
            "shared_subpath": self._shared_subpath(),
            "trees": list(set(self._attr(f, "parent_tree") for f in self.files)),
            "total_size": sum(self._attr(f, "size_bytes") for f in self.files),
            "wasted_space": sum(self._attr(f, "size_bytes") for f in self.files[1:]),
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
        """Tier 1: same hash (SHA256)."""
        by_hash = defaultdict(list)
        for f in self.files:
            h = self._get(f, "hash")
            if h:
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
        """Tier 2: same name + same size, no hash."""
        by_name_size = defaultdict(list)
        for f in self.files:
            h = self._get(f, "hash")
            cls = self._get(f, "classification")
            if not h and cls == "known":
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
        files = [self._to_file_dict(f) for f in group.files]
        return {
            "group_id": group.group_id,
            "tier": group.tier,
            "files": files,
            "shared_subpath": group._shared_subpath(),
            "trees": list(set(self._get(f, "parent_tree") for f in group.files)),
            "total_size": sum(self._get(f, "size_bytes") for f in group.files),
            "wasted_space": sum(self._get(f, "size_bytes") for f in group.files[1:]),
        }

    def _build_result(self) -> dict:
        tier1 = [self._serialize_group(g) for g in self.tier1_groups]
        tier2 = [self._serialize_group(g) for g in self.tier2_groups]
        tier3 = self.tier3_groups
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
