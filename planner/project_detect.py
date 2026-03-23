import os
from pathlib import Path
from typing import List

PROJECT_MARKERS = {
    ".git": "git",
    "package.json": "npm",
    "pyproject.toml": "python",
    "Cargo.toml": "rust",
    "requirements.txt": "python",
    "Gemfile": "ruby",
    "go.mod": "go",
    "pom.xml": "java",
    "build.gradle": "java",
    "venv": "python-venv",
    ".venv": "python-venv",
    "node_modules": "npm",
    "__pycache__": "python-cache",
    ".pytest_cache": "python-test",
    "Pods/": "ios",
    ".next": "nextjs",
    "dist/": "build",
    "build/": "build",
    ".cache": "cache",
}

def detect_project_roots(paths: List[str]) -> List[dict]:
    """Walk paths and detect likely project roots by markers."""
    roots = {}
    for base_path in paths:
        for dirpath, dirnames, files in os.walk(base_path):
            for marker in PROJECT_MARKERS:
                if marker in files or marker.rstrip("/") in dirnames:
                    project_type = PROJECT_MARKERS[marker]
                    rel = os.path.relpath(dirpath, base_path)
                    if rel == ".":
                        proj_root = base_path
                    else:
                        proj_root = dirpath
                    roots[proj_root] = {"type": project_type, "marker": marker}
    return [{"path": k, **v} for k, v in roots.items()]
