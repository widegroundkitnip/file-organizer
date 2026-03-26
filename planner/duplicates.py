import uuid
from typing import Any, Iterable


def _iter_group_paths(files: Iterable[Any]) -> list[str]:
    paths: list[str] = []
    for entry in files or []:
        if isinstance(entry, dict):
            path = entry.get("path", "")
        else:
            path = str(entry or "")
        if path:
            paths.append(path)
    return paths


def resolve_duplicates(duplicate_group: dict) -> list[dict]:
    """
    Convert a duplicate-group decision into standard executor actions only.

    Expected keys:
      keeper_path: selected file to keep
      files: list of file dicts or plain paths
    Optional keys:
      canonical_path / destination_path: where the keeper should live
      group_id / plan_id: stable group identifier
    """
    keeper_path = duplicate_group.get("keeper_path", "")
    if not keeper_path:
        raise ValueError("duplicate_group.keeper_path is required")

    all_paths = set(_iter_group_paths(duplicate_group.get("files", [])))
    if keeper_path not in all_paths:
        all_paths.add(keeper_path)

    plan_id = duplicate_group.get("plan_id") or duplicate_group.get("group_id") or f"dup_resolve_{uuid.uuid4().hex[:8]}"
    canonical_path = (
        duplicate_group.get("canonical_path")
        or duplicate_group.get("destination_path")
        or keeper_path
    )

    actions: list[dict] = []

    if canonical_path and canonical_path != keeper_path:
        actions.append({
            "action": "move",
            "src": keeper_path,
            "dst": canonical_path,
            "plan_id": plan_id,
            "action_id": str(uuid.uuid4()),
            "src_identity": {},
            "verify_checksum": False,
            "conflict_mode": "rename",
        })
        keeper_path = canonical_path

    for path in sorted(p for p in all_paths if p != duplicate_group.get("keeper_path", "")):
        actions.append({
            "action": "delete",
            "path": path,
            "plan_id": plan_id,
            "action_id": str(uuid.uuid4()),
            "src_identity": {},
        })

    return actions
