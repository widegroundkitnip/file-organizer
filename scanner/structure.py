import os
from collections import defaultdict
from typing import List, Dict
from .manifest import ScannedFile

class StructureAnalyzer:
    def __init__(self, manifest: dict, paths: List[str]):
        self.manifest = manifest
        self.paths = [p.rstrip("/") for p in paths]
        self.files = manifest.get("files", [])
        self.issues: List[dict] = []
        self.recommendations: List[dict] = []

    def analyze(self) -> dict:
        self.issues = []
        self.recommendations = []
        self._deep_nesting_check()
        self._single_child_chain_check()
        self._large_singular_dir_check()
        self._similar_subtrees_check()
        self._venv_detection()
        self._empty_dir_check()
        return self._build_report()

    def _get_tree(self, file) -> str:
        for path in self.paths:
            if file["path"].startswith(path):
                return os.path.basename(path.rstrip("/"))
        return file.get("parent_tree", "")

    def _deep_nesting_check(self, max_depth: int = 8):
        for f in self.files:
            depth = f.get("depth", 0) if isinstance(f, dict) else f.depth
            if depth > max_depth:
                path = f.get("path", "") if isinstance(f, dict) else f.path
                name = f.get("name", "") if isinstance(f, dict) else f.name
                self.issues.append({
                    "type": "deep_nesting",
                    "severity": "warning",
                    "path": os.path.dirname(path),
                    "depth": depth,
                    "file": name,
                    "message": f"File at depth {depth} — deeper than recommended {max_depth}"
                })

    def _single_child_chain_check(self):
        """Detect directory chains where each folder has exactly one subfolder."""
        dirs_with_files = defaultdict(int)
        for f in self.files:
            path = f.get("path", "") if isinstance(f, dict) else f.path
            parent = os.path.dirname(path)
            dirs_with_files[parent] += 1
        # placeholder — full impl needs dir scan
        for d, count in dirs_with_files.items():
            if count == 0:
                pass

    def _large_singular_dir_check(self, threshold: int = 500):
        """Find directories with >threshold files and no subdirs."""
        dir_file_count = defaultdict(int)
        for f in self.files:
            path = f.get("path", "") if isinstance(f, dict) else f.path
            parent = os.path.dirname(path)
            dir_file_count[parent] += 1
        for d, count in dir_file_count.items():
            if count > threshold:
                self.issues.append({
                    "type": "large_singular_dir",
                    "severity": "info",
                    "path": d,
                    "file_count": count,
                    "message": f"{count} files in single directory — consider organizing"
                })

    def _similar_subtrees_check(self, similarity_threshold: float = 0.5):
        """Find subtrees with similar relative file structures."""
        by_rel_path = defaultdict(list)
        for f in self.files:
            rel = f.get("relative_path", "") if isinstance(f, dict) else f.relative_path
            by_rel_path[rel].append(f)
        for rel, files in by_rel_path.items():
            if len(files) < 3:
                continue
            tree_map = defaultdict(int)
            for f in files:
                tree = f.get("parent_tree", "") if isinstance(f, dict) else f.parent_tree
                tree_map[tree] += 1
            if len(tree_map) > 1:
                total = sum(tree_map.values())
                top = max(tree_map.values())
                similarity = top / total
                if similarity < 0.7:
                    self.issues.append({
                        "type": "similar_subtrees",
                        "severity": "info",
                        "shared_path": rel,
                        "trees": dict(tree_map),
                        "similarity": round(similarity, 2),
                        "message": f"File '{rel}' appears in {len(tree_map)} different trees — possible shared dependency"
                    })

    def _venv_detection(self):
        """Find .venv directories."""
        seen_venvs = set()
        for f in self.files:
            rel = f.get("relative_path", "") if isinstance(f, dict) else f.relative_path
            parts = rel.split("/")
            for p in parts:
                if p == ".venv" or (p.startswith("venv") and p != "venv"):
                    seen_venvs.add(p)
        if seen_venvs:
            self.issues.append({
                "type": "venv_detected",
                "severity": "info",
                "names": list(seen_venvs),
                "count": len(seen_venvs),
                "message": f"{len(seen_venvs)} Python virtual environments detected — isolated environments"
            })

    def _empty_dir_check(self):
        """Find empty directories."""
        pass  # Would need dir scan, not just file scan

    def _build_report(self) -> dict:
        depths = []
        for f in self.files:
            d = f.get("depth", 0) if isinstance(f, dict) else f.depth
            depths.append(d)
        tree, tree_stats = self._build_tree()
        issue_paths = {
            issue.get("path")
            for issue in self.issues
            if isinstance(issue, dict) and issue.get("path")
        }
        return {
            "scan_roots": self.paths,
            "total_files": len(self.files),
            "total_folders": tree_stats["total_folders"],
            "total_size": tree_stats["total_size"],
            "depth": tree_stats["depth"],
            "tree": tree,
            "issues": [issue.get("message", str(issue)) for issue in self.issues],
            "issues_detail": self.issues,
            "issue_paths": sorted(issue_paths),
            "stats": {
                "total_files": len(self.files),
                "total_roots": len(self.paths),
                "max_depth": max(depths, default=0),
            },
            "recommendations": self.recommendations,
        }

    def _build_tree(self) -> tuple[list[dict], dict]:
        files_by_dir = defaultdict(list)
        all_dirs = set()
        issue_paths = {
            issue.get("path")
            for issue in self.issues
            if isinstance(issue, dict) and issue.get("path")
        }

        for f in self.files:
            path = f.get("path", "") if isinstance(f, dict) else f.path
            size = f.get("size_bytes", 0) if isinstance(f, dict) else f.size_bytes
            parent = os.path.dirname(path)
            if not parent:
                continue
            files_by_dir[parent].append(size)

            cur = parent
            while cur:
                all_dirs.add(cur)
                nxt = os.path.dirname(cur)
                if nxt == cur:
                    break
                cur = nxt

        children = defaultdict(set)
        for d in all_dirs:
            parent = os.path.dirname(d)
            if parent and parent != d:
                children[parent].add(d)

        def make_node(dir_path: str, depth: int) -> tuple[dict, int]:
            child_nodes = []
            folder_total = 0
            file_count = len(files_by_dir.get(dir_path, []))
            size_total = sum(files_by_dir.get(dir_path, []))
            max_depth = depth

            for child in sorted(children.get(dir_path, [])):
                child_node, child_depth = make_node(child, depth + 1)
                child_nodes.append(child_node)
                folder_total += 1 + child_node["folder_count"]
                file_count += child_node["file_count"]
                size_total += child_node["size"]
                if child_depth > max_depth:
                    max_depth = child_depth

            node_has_issue = any(
                ip == dir_path or ip.startswith(f"{dir_path}/")
                for ip in issue_paths
            )
            node = {
                "name": os.path.basename(dir_path.rstrip("/")) or dir_path,
                "path": dir_path,
                "file_count": file_count,
                "folder_count": folder_total,
                "size": size_total,
                "has_issue": node_has_issue,
                "children": child_nodes,
            }
            return node, max_depth

        roots = [p.rstrip("/") for p in self.paths if p]
        root_nodes = []
        total_folders = 0
        total_size = 0
        max_depth = 0

        for root in roots:
            all_dirs.add(root)
            node, depth = make_node(root, 0)
            root_nodes.append(node)
            total_folders += 1 + node["folder_count"]
            total_size += node["size"]
            if depth > max_depth:
                max_depth = depth

        return root_nodes, {
            "total_folders": total_folders,
            "total_size": total_size,
            "depth": max_depth,
        }
