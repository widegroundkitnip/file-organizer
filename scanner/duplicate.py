from collections import defaultdict
from typing import List, Dict
from .manifest import ScannedFile

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

    def find(self) -> dict:
        self.groups = []
        self._find_exact()
        self._find_likely()
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
            self.groups.append(DuplicateGroup(gid, "exact", group_files))
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
            self.groups.append(DuplicateGroup(gid, "likely", filtered))
            gid += 1

    def _build_result(self) -> dict:
        return {
            "duplicate_groups": [g.to_dict() for g in self.groups],
            "stats": {
                "total_groups": len(self.groups),
                "exact_count": sum(1 for g in self.groups if g.tier == "exact"),
                "likely_count": sum(1 for g in self.groups if g.tier == "likely"),
                "total_wasted_space": sum(g.to_dict()["wasted_space"] for g in self.groups),
            }
        }
