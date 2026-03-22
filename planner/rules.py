import json
import uuid
import fnmatch
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from pathlib import Path

@dataclass
class FilterCondition:
    type: str  # extension | name_contains | name_pattern | path_contains | size_gt | size_lt | all_of | any_of | none_of
    values: Optional[List[Any]] = None
    value: Optional[Any] = None

    def matches(self, file: dict) -> bool:
        name = file.get("name", "")
        path = file.get("path", "")
        ext = file.get("ext", "")
        size = file.get("size_bytes", 0)
        rel = file.get("relative_path", "")

        if self.type == "extension":
            return ext.lstrip(".") in [v.lstrip(".") for v in (self.values or [])]
        elif self.type == "name_contains":
            return any(v.lower() in name.lower() for v in (self.values or []))
        elif self.type == "name_pattern":
            return any(fnmatch.fnmatch(name, p) for p in (self.values or []))
        elif self.type == "path_contains":
            return any(v.lower() in rel.lower() for v in (self.values or []))
        elif self.type == "size_gt":
            return size > (self.value or 0)
        elif self.type == "size_lt":
            return size < (self.value or 0)
        elif self.type == "all_of":
            return all(c.matches(file) for c in (self.values or []))
        elif self.type == "any_of":
            return any(c.matches(file) for c in (self.values or []))
        elif self.type == "none_of":
            return not any(c.matches(file) for c in (self.values or []))
        return False


@dataclass
class Rule:
    id: str
    name: str
    enabled: bool = True
    priority: int = 0
    filter: Optional[FilterCondition] = None
    destination_template: str = ""
    conflict_mode: str = "rename"  # rename | skip | overwrite
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        d = dict(d)
        d["id"] = d.get("id", str(uuid.uuid4()))
        if "filter" in d and d["filter"]:
            f = d["filter"]
            if isinstance(f, dict):
                d["filter"] = FilterCondition(**f)
        return cls(**d)


class RuleManager:
    def __init__(self, rules_path: str = "rules.json"):
        self.rules_path = rules_path
        self.rules: List[Rule] = []
        self.load()

    def load(self):
        if Path(self.rules_path).exists():
            with open(self.rules_path) as f:
                data = json.load(f)
                self.rules = [Rule.from_dict(r) for r in data.get("rules", [])]
        else:
            self.rules = self._default_rules()
            self.save()

    def save(self):
        with open(self.rules_path, "w") as f:
            json.dump({"rules": [r.to_dict() for r in self.rules]}, f, indent=2)

    def _default_rules(self) -> List[Rule]:
        return [
            Rule(
                id=str(uuid.uuid4()),
                name="Images → Images",
                enabled=True,
                priority=0,
                filter=FilterCondition(type="extension", values=["jpg","jpeg","png","gif","webp","bmp","tiff","raw","heic"]),
                destination_template="{category}/Images/{name}.{ext}",
                conflict_mode="rename",
                tags=["media"]
            ),
            Rule(
                id=str(uuid.uuid4()),
                name="Documents → Documents",
                enabled=True,
                priority=1,
                filter=FilterCondition(type="extension", values=["pdf","doc","docx","txt","md","rtf","odt"]),
                destination_template="{category}/Documents/{name}.{ext}",
                conflict_mode="rename",
                tags=["media"]
            ),
            Rule(
                id=str(uuid.uuid4()),
                name="Code → Code",
                enabled=True,
                priority=2,
                filter=FilterCondition(type="extension", values=["py","js","ts","java","c","cpp","go","rs","rb","sh","bash"]),
                destination_template="{category}/Code/{name}.{ext}",
                conflict_mode="rename",
                tags=["media"]
            ),
            Rule(
                id=str(uuid.uuid4()),
                name="Archives → Archives",
                enabled=True,
                priority=3,
                filter=FilterCondition(type="extension", values=["zip","tar","gz","rar","7z"]),
                destination_template="{category}/Archives/{name}.{ext}",
                conflict_mode="rename",
                tags=["media"]
            ),
        ]

    def add_rule(self, rule: Rule):
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority)
        self.save()

    def remove_rule(self, rule_id: str):
        self.rules = [r for r in self.rules if r.id != rule_id]
        self.save()

    def update_rule(self, rule: Rule):
        for i, r in enumerate(self.rules):
            if r.id == rule.id:
                self.rules[i] = rule
                break
        self.save()
