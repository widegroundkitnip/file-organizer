"""
Learner — Local Deterministic Rule Suggestion (LOCKED 2026-03-25)

Architecture: local deterministic pattern aggregator. NO API models, NO local ML models in core.
Pattern aggregation + suggestion only. Privacy-first, deterministic, explainable.

Pattern types (prioritized):
  1. Extension → template  (.jpg → Images/{year}/{name}.{ext})
  2. Extension + context → template  (.jpg + parent=Screenshots → Images/Screenshots/...)
  3. Category → template  (category=documents → Documents/{name}.{ext})
  4. User rule creation → strong evidence pattern

Suggestion threshold:
  support_count >= 5
  consistency >= 0.8
  no active suppression

Confidence: capped at 0.95 (never 100%).

Storage:
  Linux: ~/.local/share/file-organizer/learner/
  macOS: ~/Library/Application Support/org.file-organizer/learner/
  Windows: %APPDATA%/FileOrganizer/learner/
"""

from __future__ import annotations

import json
import os
import platform
import uuid
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

def _learner_dir() -> Path:
    if platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "org.file-organizer"
    elif platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", "")) / "FileOrganizer"
    else:
        base = Path.home() / ".local" / "share" / "file-organizer"
    learner_dir = base / "learner"
    learner_dir.mkdir(parents=True, exist_ok=True)
    return learner_dir


EVENTS_FILE = str(_learner_dir() / "events.jsonl")
SUGGESTIONS_STATE_FILE = str(_learner_dir() / "suggestions_state.json")


# ---------------------------------------------------------------------------
# Event schema
# ---------------------------------------------------------------------------

# Supported event types
EVENT_TYPES = frozenset([
    "action_approved",
    "action_rejected",
    "rule_created",
    "rule_modified",
    "suggestion_accepted",
    "suggestion_dismissed",
    "project_marked",
    "project_unmarked",
])


@dataclass
class LearnerEvent:
    event_id: str
    timestamp: str          # ISO8601 UTC
    event_type: str         # one of EVENT_TYPES
    file: dict              # {path, ext, category, parent, tree, size_bucket}
    action: dict            # {type, src, dst, destination_template}
    context: dict           # {rule_id, profile_id, scope_mode, user_confirmed}


def _make_timestamp() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _size_bucket(size_bytes: int) -> str:
    """Bucket file size into a readable range."""
    for lo, hi, label in [
        (0,       1024*1024,          "lt_1mb"),
        (1024*1024, 10*1024*1024,     "1mb_10mb"),
        (10*1024*1024, 100*1024*1024, "10mb_100mb"),
        (100*1024*1024, float("inf"), "gt_100mb"),
    ]:
        if lo <= size_bytes < hi:
            return label
    return "lt_1mb"


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------

def log_event(
    event_type: str,
    file_info: dict,
    action_info: dict,
    context_info: Optional[dict] = None,
) -> str:
    """
    Log a learner event to events.jsonl.

    Args:
        event_type:  one of EVENT_TYPES
        file_info:   {path, ext, category, parent, tree, size_bytes}
        action_info: {type, src, dst, destination_template}
        context_info: optional {rule_id, profile_id, scope_mode, user_confirmed}
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Invalid event_type: {event_type!r}")

    # Derive missing fields from file_info
    size_bytes = file_info.get("size_bytes", 0)
    size_bucket = _size_bucket(size_bytes)
    parent = file_info.get("parent", "")
    tree = file_info.get("tree", "")
    ext = file_info.get("ext", "")
    category = file_info.get("category", "other")
    path = file_info.get("path", "")

    event = LearnerEvent(
        event_id=str(uuid.uuid4()),
        timestamp=_make_timestamp(),
        event_type=event_type,
        file={
            "path": path,
            "ext": ext.lstrip(".") if ext else "",
            "category": category,
            "parent": parent,
            "tree": tree,
            "size_bucket": size_bucket,
        },
        action={
            "type": action_info.get("type", "move"),
            "src": action_info.get("src", ""),
            "dst": action_info.get("dst", ""),
            "destination_template": action_info.get("destination_template", ""),
        },
        context=context_info or {},
    )

    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    return event.event_id


# Convenience wrappers for each event type
def log_action_approved(
    file_info: dict,
    action_info: dict,
    context_info: Optional[dict] = None,
) -> str:
    return log_event("action_approved", file_info, action_info, context_info)


def log_action_rejected(
    file_info: dict,
    action_info: dict,
    context_info: Optional[dict] = None,
) -> str:
    return log_event("action_rejected", file_info, action_info, context_info)


def log_rule_created(rule_dict: dict, context_info: Optional[dict] = None) -> str:
    return log_event(
        "rule_created",
        file_info={"path": "", "ext": "", "category": "", "parent": "", "tree": "", "size_bytes": 0},
        action_info={
            "type": "move",
            "src": "",
            "dst": "",
            "destination_template": rule_dict.get("destination_template", ""),
        },
        context_info={
            "rule_id": rule_dict.get("id", ""),
            "rule_filter": rule_dict.get("filter", {}),
            "rule_name": rule_dict.get("name", ""),
            **(context_info or {}),
        },
    )


def log_rule_modified(rule_dict: dict, context_info: Optional[dict] = None) -> str:
    return log_event(
        "rule_modified",
        file_info={"path": "", "ext": "", "category": "", "parent": "", "tree": "", "size_bytes": 0},
        action_info={
            "type": "move",
            "src": "",
            "dst": "",
            "destination_template": rule_dict.get("destination_template", ""),
        },
        context_info={
            "rule_id": rule_dict.get("id", ""),
            "rule_filter": rule_dict.get("filter", {}),
            "rule_name": rule_dict.get("name", ""),
            **(context_info or {}),
        },
    )


def log_suggestion_accepted(suggestion_id: str, pattern_key: str, context_info: Optional[dict] = None) -> str:
    return log_event(
        "suggestion_accepted",
        file_info={"path": "", "ext": "", "category": "", "parent": "", "tree": "", "size_bytes": 0},
        action_info={"type": "move", "src": "", "dst": "", "destination_template": ""},
        context_info={
            "suggestion_id": suggestion_id,
            "pattern_key": pattern_key,
            **(context_info or {}),
        },
    )


def log_suggestion_dismissed(
    suggestion_id: str,
    pattern_key: str,
    pattern_type: str,
    context_info: Optional[dict] = None,
) -> str:
    return log_event(
        "suggestion_dismissed",
        file_info={"path": "", "ext": "", "category": "", "parent": "", "tree": "", "size_bytes": 0},
        action_info={"type": "move", "src": "", "dst": "", "destination_template": ""},
        context_info={
            "suggestion_id": suggestion_id,
            "pattern_key": pattern_key,
            "pattern_type": pattern_type,
            **(context_info or {}),
        },
    )


def log_project_marked(path: str, markers: list, folder_characteristics: Optional[dict] = None) -> str:
    return log_event(
        "project_marked",
        file_info={"path": path, "ext": "", "category": "", "parent": "", "tree": "", "size_bytes": 0},
        action_info={"type": "move", "src": "", "dst": "", "destination_template": ""},
        context_info={
            "markers_detected": markers,
            "folder_characteristics": folder_characteristics or {},
        },
    )


def log_project_unmarked(path: str, reason: str = "") -> str:
    return log_event(
        "project_unmarked",
        file_info={"path": path, "ext": "", "category": "", "parent": "", "tree": "", "size_bytes": 0},
        action_info={"type": "move", "src": "", "dst": "", "destination_template": ""},
        context_info={"reason": reason},
    )


# ---------------------------------------------------------------------------
# Suppression / dismissal state
# ---------------------------------------------------------------------------

def _load_suppressions() -> dict:
    """Load suppression/dismissal state from suggestions_state.json."""
    if not Path(SUGGESTIONS_STATE_FILE).exists():
        return {}
    try:
        with open(SUGGESTIONS_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_suppressions(state: dict) -> None:
    with open(SUGGESTIONS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _is_suppressed(pattern_key: str) -> tuple[bool, int]:
    """Return (is_suppressed, days_remaining)."""
    state = _load_suppressions()
    entry = state.get(pattern_key)
    if not entry:
        return False, 0
    dismissed_at = datetime.fromisoformat(entry["dismissed_at"].replace("Z", "+00:00"))
    # First dismiss: 7 days.  Second+: 14 days.
    days = 7 if entry.get("dismissal_count", 1) == 1 else 14
    expiry = dismissed_at + timedelta(days=days)
    if datetime.now(tz=timezone.utc) < expiry:
        remaining = (expiry - datetime.now(tz=timezone.utc)).days + 1
        return True, remaining
    # Expired — clear it
    del state[pattern_key]
    _save_suppressions(state)
    return False, 0


def _record_dismissal(pattern_key: str, pattern_type: str, suggestion_id: str) -> None:
    state = _load_suppressions()
    if pattern_key in state:
        state[pattern_key]["dismissal_count"] = state[pattern_key].get("dismissal_count", 1) + 1
    else:
        state[pattern_key] = {
            "pattern_type": pattern_type,
            "dismissed_at": _make_timestamp(),
            "dismissal_count": 1,
            "last_suggestion_id": suggestion_id,
        }
    _save_suppressions(state)


def _clear_suppression(pattern_key: str) -> None:
    state = _load_suppressions()
    if pattern_key in state:
        del state[pattern_key]
        _save_suppressions(state)


# ---------------------------------------------------------------------------
# Event loading helpers
# ---------------------------------------------------------------------------

def _iter_events(days_back: Optional[int] = None):
    """Yield events from events.jsonl, optionally filtered by recency."""
    if not Path(EVENTS_FILE).exists():
        return
    cutoff = None
    if days_back is not None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff:
                ts = event.get("timestamp", "")
                try:
                    ev_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if ev_time < cutoff:
                        continue
                except ValueError:
                    pass
            yield event


# ---------------------------------------------------------------------------
# Template normalisation (for consistency grouping)
# ---------------------------------------------------------------------------

def _normalise_template(template: str) -> str:
    """
    Normalise a destination template so two templates that differ only in
    variable values (e.g. year) still collapse to the same pattern key.

    Strips {year}/{month}/{day} segments and replaces numeric {size} with {size}.
    """
    import re
    # Replace {year}/{month}/{day} sequences with {date_vars}
    t = re.sub(r'\{year\}', '{Y}', template)
    t = re.sub(r'\{month\}', '{M}', t)
    t = re.sub(r'\{day\}', '{D}', t)
    # Replace {date:FORMAT} with {date}
    t = re.sub(r'\{date:[^}]+\}', '{date}', t)
    # Replace numeric size values (placeholder)
    t = re.sub(r'\{size_human\}', '{size_h}', t)
    t = re.sub(r'\{size\}', '{size}', t)
    # Normalise multiple consecutive slashes
    while "//" in t:
        t = t.replace("//", "/")
    return t.strip("/")


# ---------------------------------------------------------------------------
# Pattern aggregation
# ---------------------------------------------------------------------------

# Suggestion thresholds (LOCKED)
SUPPORT_THRESHOLD = 5       # >= 5 approved actions
CONSISTENCY_THRESHOLD = 0.8 # >= 80% same template
CONFIDENCE_CAP = 0.95       # never 100%


def _compute_confidence(support_count: int, consistency: float, recency_weight: float = 0.0) -> float:
    """
    Weighted confidence score.
    Components: support (normalised), consistency, recency boost.
    Capped at 0.95.
    """
    support_score = min(support_count / 20.0, 1.0)  # 20+ actions = max support
    raw = (support_score * 0.4) + (consistency * 0.5) + (recency_weight * 0.1)
    return min(raw, CONFIDENCE_CAP)


@dataclass
class Suggestion:
    suggestion_id: str
    pattern_type: str       # extension_to_template | ext_context_to_template | category_to_template | user_rule_creation
    title: str
    explanation: str
    support_count: int
    consistency: float
    confidence: float
    examples: list         # list of "src → dst" strings (max 5)
    proposed_rule: dict    # Rule.to_dict()-compatible
    pattern_key: str       # stable key for suppression tracking
    conflict_status: str   # no_conflict | similar | contradicts

    def to_dict(self) -> dict:
        return {
            "suggestion_id": self.suggestion_id,
            "type": "rule_suggestion",
            "pattern_type": self.pattern_type,
            "title": self.title,
            "explanation": self.explanation,
            "support_count": self.support_count,
            "consistency": round(self.consistency, 3),
            "confidence": round(self.confidence, 3),
            "examples": self.examples,
            "proposed_rule": self.proposed_rule,
            "pattern_key": self.pattern_key,
            "conflict_status": self.conflict_status,
        }


def _extract_parent_from_path(path: str) -> str:
    """Extract immediate parent folder name from a file path."""
    parent = os.path.basename(os.path.dirname(path))
    return parent


def _build_examples(file_actions: list, n: int = 5) -> list:
    """Build example strings from a list of {file, action} dicts."""
    examples = []
    for item in sorted(file_actions, key=lambda x: x.get("timestamp", ""))[:n]:
        f = item["file"]
        a = item["action"]
        src = f.get("path", "")
        dst = a.get("dst", "")
        if src and dst:
            examples.append(f"{src} → {dst}")
        elif src:
            examples.append(src)
    return examples


# Pattern 1: Extension → Template
def _pattern_ext_to_template(events: list) -> list:
    """
    Aggregate: all action_approved events with the same extension + destination_template.
    Group by (ext, normalised_template). If support >= 5 and consistency >= 0.8 → suggestion.
    """
    # Group (ext, norm_template) → [(file, action, timestamp), ...]
    buckets: dict = defaultdict(list)
    for ev in events:
        if ev.get("event_type") != "action_approved":
            continue
        f = ev.get("file", {})
        a = ev.get("action", {})
        ext = f.get("ext", "").lower().lstrip(".")
        dst = a.get("destination_template", "")
        if not ext or not dst:
            continue
        norm = _normalise_template(dst)
        buckets[(ext, norm)].append({"file": f, "action": a, "timestamp": ev.get("timestamp", "")})

    suggestions = []
    for (ext, norm_tpl), items in buckets.items():
        total = len(items)
        if total < SUPPORT_THRESHOLD:
            continue
        # Consistency: most common concrete dst
        concrete_dsts = [i["action"].get("destination_template", "") for i in items]
        dst_counter: dict = defaultdict(int)
        for d in concrete_dsts:
            dst_counter[d] += 1
        dominant_dst, dominant_count = max(dst_counter.items(), key=lambda x: x[1])
        consistency = dominant_count / total
        if consistency < CONSISTENCY_THRESHOLD:
            continue

        # Recency weight: fraction of events in last 14 days
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=14)
        recent = 0
        for item in items:
            try:
                ts = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    recent += 1
            except ValueError:
                pass
        recency_weight = recent / total

        confidence = _compute_confidence(total, consistency, recency_weight)
        pattern_key = f"ext|{ext}|{norm_tpl}"
        suppressed, _ = _is_suppressed(pattern_key)
        if suppressed:
            continue

        examples = _build_examples(items)
        suggestions.append(Suggestion(
            suggestion_id=f"sug-{uuid.uuid4().hex[:8]}",
            pattern_type="extension_to_template",
            title=f"Create rule for .{ext} files",
            explanation=(
                f"You approved moving {total} .{ext} file{'s' if total != 1 else ''} "
                f"to {dominant_dst} with {consistency*100:.0f}% consistency in recent activity."
            ),
            support_count=total,
            consistency=consistency,
            confidence=confidence,
            examples=examples,
            proposed_rule={
                "name": f"{ext.upper()} files → organized",
                "enabled": True,
                "priority": 100,
                "filter": {"type": "extension", "values": [ext]},
                "destination_template": dominant_dst,
                "action": "move",
                "conflict_mode": "rename",
                "tags": ["learner"],
            },
            pattern_key=pattern_key,
            conflict_status="no_conflict",
        ))
    return suggestions


# Pattern 2: Extension + Context → Template
def _pattern_ext_context_to_template(events: list) -> list:
    """
    Aggregate: action_approved events with the same extension + parent context + destination_template.
    Good contexts: parent folder name (most reliable), tree name.
    """
    buckets: dict = defaultdict(list)
    for ev in events:
        if ev.get("event_type") != "action_approved":
            continue
        f = ev.get("file", {})
        a = ev.get("action", {})
        ext = f.get("ext", "").lower().lstrip(".")
        parent = f.get("parent", "")
        tree = f.get("tree", "")
        dst = a.get("destination_template", "")
        if not ext or not dst or not parent:
            continue
        norm = _normalise_template(dst)
        # Use parent as the strongest context signal
        buckets[(ext, parent, norm)].append({"file": f, "action": a, "timestamp": ev.get("timestamp", "")})

    suggestions = []
    for (ext, parent, norm_tpl), items in buckets.items():
        total = len(items)
        if total < SUPPORT_THRESHOLD:
            continue
        concrete_dsts = [i["action"].get("destination_template", "") for i in items]
        dst_counter: dict = defaultdict(int)
        for d in concrete_dsts:
            dst_counter[d] += 1
        dominant_dst, dominant_count = max(dst_counter.items(), key=lambda x: x[1])
        consistency = dominant_count / total
        if consistency < CONSISTENCY_THRESHOLD:
            continue

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=14)
        recent = 0
        for item in items:
            try:
                ts = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    recent += 1
            except ValueError:
                pass
        recency_weight = recent / total

        confidence = _compute_confidence(total, consistency, recency_weight)
        pattern_key = f"extctx|{ext}|{parent}|{norm_tpl}"
        suppressed, _ = _is_suppressed(pattern_key)
        if suppressed:
            continue

        examples = _build_examples(items)
        suggestions.append(Suggestion(
            suggestion_id=f"sug-{uuid.uuid4().hex[:8]}",
            pattern_type="ext_context_to_template",
            title=f"Organize .{ext} files from {parent}/",
            explanation=(
                f"You approved moving {total} .{ext} file{'s' if total != 1 else ''} "
                f"from folder '{parent}' to {dominant_dst} ({consistency*100:.0f}% consistent)."
            ),
            support_count=total,
            consistency=consistency,
            confidence=confidence,
            examples=examples,
            proposed_rule={
                "name": f"{ext.upper()} from {parent} → organized",
                "enabled": True,
                "priority": 90,
                "filter": {
                    "type": "all_of",
                    "values": [
                        {"type": "extension", "values": [ext]},
                        {"type": "path_contains", "values": [parent]},
                    ],
                },
                "destination_template": dominant_dst,
                "action": "move",
                "conflict_mode": "rename",
                "tags": ["learner"],
            },
            pattern_key=pattern_key,
            conflict_status="no_conflict",
        ))
    return suggestions


# Pattern 3: Category → Template
def _pattern_category_to_template(events: list) -> list:
    """
    Aggregate: action_approved events with the same category + destination_template.
    Fires when multiple different extensions with the same category behave identically.
    """
    buckets: dict = defaultdict(list)
    for ev in events:
        if ev.get("event_type") != "action_approved":
            continue
        f = ev.get("file", {})
        a = ev.get("action", {})
        category = f.get("category", "other")
        dst = a.get("destination_template", "")
        if not category or not dst:
            continue
        norm = _normalise_template(dst)
        buckets[(category, norm)].append({"file": f, "action": a, "timestamp": ev.get("timestamp", "")})

    suggestions = []
    for (category, norm_tpl), items in buckets.items():
        total = len(items)
        if total < SUPPORT_THRESHOLD:
            continue
        concrete_dsts = [i["action"].get("destination_template", "") for i in items]
        dst_counter: dict = defaultdict(int)
        for d in concrete_dsts:
            dst_counter[d] += 1
        dominant_dst, dominant_count = max(dst_counter.items(), key=lambda x: x[1])
        consistency = dominant_count / total
        if consistency < CONSISTENCY_THRESHOLD:
            continue

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=14)
        recent = 0
        for item in items:
            try:
                ts = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    recent += 1
            except ValueError:
                pass
        recency_weight = recent / total

        confidence = _compute_confidence(total, consistency, recency_weight)
        pattern_key = f"cat|{category}|{norm_tpl}"
        suppressed, _ = _is_suppressed(pattern_key)
        if suppressed:
            continue

        examples = _build_examples(items)
        suggestions.append(Suggestion(
            suggestion_id=f"sug-{uuid.uuid4().hex[:8]}",
            pattern_type="category_to_template",
            title=f"Organize {category} files",
            explanation=(
                f"You approved moving {total} {category} file{'s' if total != 1 else ''} "
                f"to {dominant_dst} with {consistency*100:.0f}% consistency."
            ),
            support_count=total,
            consistency=consistency,
            confidence=confidence,
            examples=examples,
            proposed_rule={
                "name": f"Organize {category}",
                "enabled": True,
                "priority": 100,
                "filter": {"type": "extension", "values": _category_extensions(category)},
                "destination_template": dominant_dst,
                "action": "move",
                "conflict_mode": "rename",
                "tags": ["learner"],
            },
            pattern_key=pattern_key,
            conflict_status="no_conflict",
        ))
    return suggestions


def _category_extensions(category: str) -> list:
    """Return the list of extensions mapped to a category (from scanner/manifest.py)."""
    mapping = {
        "images": ["jpg","jpeg","png","gif","bmp","svg","webp","heic","tiff","raw","psd","ico","jfif","pnm"],
        "documents": ["pdf","doc","docx","txt","rtf","odt","xls","xlsx","ppt","pptx","csv","md","pages","numbers","keynote"],
        "video": ["mp4","mkv","mov","avi","wmv","flv","webm","m4v","mpeg","mpg","ts","mts"],
        "audio": ["mp3","wav","flac","aac","ogg","m4a","wma","opus","aiff"],
        "code": ["py","js","ts","java","c","cpp","h","hpp","cs","go","rs","rb","php","swift","kt","scala","r","sh","bash","zsh","ps1","sql","html","css","json","xml","yaml","yml","toml","ini","cfg","env"],
        "archives": ["zip","tar","gz","bz2","xz","rar","7z","tgz","bz","lz","lzma"],
    }
    return mapping.get(category, [])


# Pattern 4: User rule creation → strong evidence pattern
def _pattern_user_rule_creation(events: list, active_rules: list) -> list:
    """
    When user creates or modifies a rule manually, store it as strong evidence.
    This is NOT a suggestion — it immediately boosts confidence for matching patterns
    and is stored as a learner_signal for future reference.
    """
    suggestions = []
    for ev in events:
        if ev.get("event_type") not in ("rule_created", "rule_modified"):
            continue
        ctx = ev.get("context", {})
        rule_filter = ctx.get("rule_filter", {})
        rule_name = ctx.get("rule_name", "")
        rule_id = ctx.get("rule_id", "")
        dst = ev.get("action", {}).get("destination_template", "")

        if not dst:
            continue

        ftype = rule_filter.get("type", "")
        fvalues = rule_filter.get("values", [])
        fvalue = rule_filter.get("value", "")

        if ftype == "extension" and fvalues:
            ext = fvalues[0].lstrip(".")
            pattern_key = f"user_rule|ext|{ext}"
            suggestions.append(Suggestion(
                suggestion_id=f"sug-{uuid.uuid4().hex[:8]}",
                pattern_type="user_rule_creation",
                title=f"You created a rule for .{ext} files: {rule_name}",
                explanation=(
                    f"You manually created a rule '{rule_name}' routing .{ext} files to {dst}. "
                    f"This strong evidence pattern boosts learner confidence for .{ext} routing."
                ),
                support_count=10,  # User-created = strong signal
                consistency=1.0,
                confidence=min(CONFIDENCE_CAP, 0.90),  # Capped at 0.95 but below so user still confirms
                examples=[],
                proposed_rule={
                    "name": rule_name,
                    "enabled": True,
                    "priority": 50,
                    "filter": rule_filter,
                    "destination_template": dst,
                    "action": "move",
                    "conflict_mode": "rename",
                    "tags": ["learner", "user_created"],
                },
                pattern_key=pattern_key,
                conflict_status="no_conflict",
            ))
    return suggestions


# ---------------------------------------------------------------------------
# Conflict detection against active rules
# ---------------------------------------------------------------------------

def _check_conflict(suggestion: Suggestion, active_rules: list) -> str:
    """
    Check proposed rule against active rules.
    Returns: no_conflict | similar | contradicts
    """
    prop_filter = suggestion.proposed_rule.get("filter", {})
    prop_type = prop_filter.get("type", "")
    prop_dst = suggestion.proposed_rule.get("destination_template", "")

    # Extract extension values safely (only for flat extension filters)
    raw_exts = prop_filter.get("values", [])
    prop_exts: set = set()
    if prop_type == "extension" and raw_exts and isinstance(raw_exts[0], str):
        prop_exts = {v.lstrip(".").lower() for v in raw_exts}
    elif prop_type == "extension" and raw_exts and isinstance(raw_exts[0], dict):
        # Composite filter with extension inside — skip conflict check for simplicity
        prop_exts = set()

    for rule in active_rules:
        rf = rule.filter if hasattr(rule, "filter") else rule.get("filter", {})
        rf_type = rf.get("type", "") if rf else ""
        rf_values = set(rf.get("values", []) if rf else [])

        # Check extension overlap
        if prop_type == rf_type == "extension" and prop_exts & rf_values:
            existing_dst = rule.destination_template if hasattr(rule, "destination_template") else rule.get("destination_template", "")
            if existing_dst == prop_dst:
                return "similar"  # Same ext, same destination — redundant
            else:
                return "contradicts"  # Same ext, different destination

        # Check ext+context overlap
        if prop_type == "all_of" and rf_type == "all_of":
            # Simple check: any shared extension condition
            prop_conds = prop_filter.get("values", [])
            rf_conds = rf.get("values", [])
            for pc in prop_conds:
                if pc.get("type") == "extension":
                    for rc in rf_conds:
                        if rc.get("type") == "extension" and set(pc.get("values", [])) & set(rc.get("values", [])):
                            existing_dst = rule.destination_template if hasattr(rule, "destination_template") else rule.get("destination_template", "")
                            if existing_dst == prop_dst:
                                return "similar"
                            else:
                                return "contradicts"

    return "no_conflict"


# ---------------------------------------------------------------------------
# Main suggestion engine
# ---------------------------------------------------------------------------

def get_suggestions(
    days_back: int = 30,
    active_rules: Optional[list] = None,
) -> list[dict]:
    """
    Run the full suggestion engine.

    Args:
        days_back:     only consider events from the last N days (default 30)
        active_rules:  list of Rule objects (from RuleManager.rules) for conflict detection

    Returns:
        List of suggestion dicts (all types merged, sorted by confidence descending).
    """
    events = list(_iter_events(days_back=days_back))
    active_rules = active_rules or []

    # Run all 4 pattern aggregators
    all_suggestions: list[Suggestion] = []
    all_suggestions.extend(_pattern_ext_to_template(events))
    all_suggestions.extend(_pattern_ext_context_to_template(events))
    all_suggestions.extend(_pattern_category_to_template(events))
    all_suggestions.extend(_pattern_user_rule_creation(events, active_rules))

    # Check conflicts against active rules
    for sug in all_suggestions:
        sug.conflict_status = _check_conflict(sug, active_rules)

    # Sort by confidence descending, then deduplicate by (pattern_type, pattern_key).
    # For same pattern_type + key, keep highest confidence entry.
    # Also deduplicate proposed rules by (filter_type + values_json) to prevent
    # the same rule being surfaced twice via different pattern aggregators.
    all_suggestions.sort(key=lambda s: s.confidence, reverse=True)
    seen_type_key: set = set()
    seen_rule_key: set = set()
    deduped: list[Suggestion] = []
    for sug in all_suggestions:
        type_key = (sug.pattern_type, sug.pattern_key)
        # Rule-level dedup: serialise filter values to JSON string for stable hash
        prop = sug.proposed_rule
        f = prop.get("filter", {})
        ftype = f.get("type", "")
        try:
            fvals_json = json.dumps(f.get("values", []), sort_keys=True)
        except TypeError:
            fvals_json = str(f.get("values", []))
        rule_key = (ftype, fvals_json, prop.get("destination_template", ""))
        if type_key in seen_type_key or rule_key in seen_rule_key:
            continue
        seen_type_key.add(type_key)
        seen_rule_key.add(rule_key)
        deduped.append(sug)

    return [s.to_dict() for s in deduped]


# ---------------------------------------------------------------------------
# Accept / dismiss workflow
# ---------------------------------------------------------------------------

def accept_suggestion(suggestion: dict) -> str:
    """
    User accepted a suggestion → log event + clear any suppression + return rule_id.
    """
    pattern_key = suggestion.get("pattern_key", "")
    suggestion_id = suggestion.get("suggestion_id", "")
    _clear_suppression(pattern_key)
    event_id = log_suggestion_accepted(suggestion_id, pattern_key)
    return event_id


def dismiss_suggestion(suggestion: dict) -> str:
    """
    User dismissed a suggestion → log event + record suppression.
    """
    pattern_key = suggestion.get("pattern_key", "")
    pattern_type = suggestion.get("pattern_type", "")
    suggestion_id = suggestion.get("suggestion_id", "")
    _record_dismissal(pattern_key, pattern_type, suggestion_id)
    event_id = log_suggestion_dismissed(suggestion_id, pattern_key, pattern_type)
    return event_id


# ---------------------------------------------------------------------------
# Stats / debug
# ---------------------------------------------------------------------------

def learner_stats(days_back: int = 30) -> dict:
    """Return basic learner statistics for the dashboard."""
    events = list(_iter_events(days_back=days_back))
    by_type: dict = defaultdict(int)
    for ev in events:
        by_type[ev.get("event_type", "unknown")] += 1

    # Count suppression entries
    suppressions = _load_suppressions()

    return {
        "total_events": len(events),
        "by_event_type": dict(by_type),
        "active_suppressions": len(suppressions),
        "suppressed_patterns": list(suppressions.keys()),
        "storage_path": str(_learner_dir()),
    }
