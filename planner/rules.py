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
        elif self.type == "modified_after":
            return file.get("mtime", 0) > float(self.value or 0)
        elif self.type == "modified_before":
            return file.get("mtime", 0) < float(self.value or 0)
        elif self.type == "created_after":
            return file.get("ctime", 0) > float(self.value or 0)
        elif self.type == "created_before":
            return file.get("ctime", 0) < float(self.value or 0)
        elif self.type == "modified_within_days":
            import time
            days = int(self.value or 0)
            threshold = time.time() - days * 86400
            return file.get("mtime", 0) > threshold
        elif self.type == "all_of":
            return all(c.matches(file) for c in (self.values or []))
        elif self.type == "any_of":
            return any(c.matches(file) for c in (self.values or []))
        elif self.type == "none_of":
            return not any(c.matches(file) for c in (self.values or []))
        elif self.type == "no_extension":
            # Files with no extension
            name = file.get("name", "")
            return "." not in name
        elif self.type == "default":
            # Catch-all — always matches (for fallback rules)
            return True
        elif self.type == "duplicate":
            # Files that are duplicates (flagged in manifest)
            return file.get("is_duplicate", False)
        raise ValueError(f"Unknown filter type: {self.type}")


@dataclass
class Rule:
    id: str
    name: str
    enabled: bool = True
    priority: int = 0
    filter: Optional[FilterCondition] = None
    destination_template: str = ""
    conflict_mode: str = "rename"  # rename | skip | overwrite
    action: str = "move"  # move | skip | delete
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
                d["filter"] = cls._dict_to_filter(f)
        return cls(**d)

    @classmethod
    def _dict_to_filter(cls, f: dict) -> "FilterCondition":
        """Recursively convert a filter dict to FilterCondition, handling nested all_of/any_of."""
        ftype = f.get("type", "")
        # Support both "values" and "conditions" keys for composite filters
        values = f.get("values") if f.get("values") is not None else f.get("conditions")
        # Recursively convert nested conditions for all_of/any_of/none_of
        if ftype in ("all_of", "any_of", "none_of") and isinstance(values, list):
            converted_values = []
            for cond in values:
                if isinstance(cond, dict):
                    converted_values.append(cls._dict_to_filter(cond))
                elif isinstance(cond, FilterCondition):
                    converted_values.append(cond)
                else:
                    raise ValueError(f"Invalid nested condition in {ftype}: {cond!r}")
            return FilterCondition(type=ftype, values=converted_values)
        # Build kwargs — include value/values only if present in source dict
        kwargs = {"type": ftype}
        if "values" in f:
            kwargs["values"] = f["values"]
        elif "conditions" in f:
            kwargs["values"] = f["conditions"]
        if "value" in f:
            kwargs["value"] = f["value"]
        return FilterCondition(**kwargs)


class RuleManager:
    def __init__(self, rules_path: str = "rules.json"):
        self.rules_path = rules_path
        self.rules: List[Rule] = []
        self.load()

    def load(self):
        if Path(self.rules_path).exists():
            with open(self.rules_path) as f:
                data = json.load(f)
                # Support both {"rules": [...]} and bare [...]
                if isinstance(data, list):
                    self.rules = [Rule.from_dict(r) for r in data]
                else:
                    self.rules = [Rule.from_dict(r) for r in data.get("rules", [])]
        else:
            self.rules = self._default_rules()
            self.save()

    def save(self):
        with open(self.rules_path, "w") as f:
            json.dump({"rules": [r.to_dict() for r in self.rules]}, f, indent=2)

    def _default_rules(self) -> List[Rule]:
        return [
            # ── Skip / Protected ──────────────────────────────────────
            Rule(id=str(uuid.uuid4()), name="Protected Files", enabled=True, priority=0,
                 filter=FilterCondition(type="extension", values=["env","ini","cfg","toml","gitignore","gitattributes"]),
                 destination_template="", action="skip", conflict_mode="skip", tags=["protected"]),
            Rule(id=str(uuid.uuid4()), name="Keep Tagged", enabled=True, priority=1,
                 filter=FilterCondition(type="name_contains", values=["KEEP","TODO","WIP","DRAFT"]),
                 destination_template="", action="skip", conflict_mode="skip", tags=["protected"]),

            # ── Type Sorting ─────────────────────────────────────────
            Rule(id=str(uuid.uuid4()), name="Images", enabled=True, priority=10,
                 filter=FilterCondition(type="extension", values=["jpg","jpeg","png","webp","heic","gif","bmp","tiff","raw"]),
                 destination_template="{category}/Images/{name}.{ext}", conflict_mode="rename", tags=["media"]),
            Rule(id=str(uuid.uuid4()), name="Videos", enabled=True, priority=11,
                 filter=FilterCondition(type="extension", values=["mp4","mov","mkv","avi","webm","flv","wmv","m4v"]),
                 destination_template="{category}/Videos/{name}.{ext}", conflict_mode="rename", tags=["media"]),
            Rule(id=str(uuid.uuid4()), name="Documents", enabled=True, priority=12,
                 filter=FilterCondition(type="extension", values=["pdf","docx","txt","md","doc","odt","rtf","xlsx","xls","pptx","ppt"]),
                 destination_template="{category}/Documents/{name}.{ext}", conflict_mode="rename", tags=["docs"]),
            Rule(id=str(uuid.uuid4()), name="Audio", enabled=True, priority=13,
                 filter=FilterCondition(type="extension", values=["mp3","wav","m4a","aac","flac","ogg","wma","aiff"]),
                 destination_template="{category}/Audio/{name}.{ext}", conflict_mode="rename", tags=["media"]),
            Rule(id=str(uuid.uuid4()), name="Code", enabled=True, priority=14,
                 filter=FilterCondition(type="extension", values=["py","js","ts","jsx","tsx","java","c","cpp","h","hpp","go","rs","rb","php","swift","kt","scala","sh","bash","zsh","css","html","xml","yaml","yml","toml","json","sql","r","m"]),
                 destination_template="{category}/Code/{name}.{ext}", conflict_mode="rename", tags=["code"]),
            Rule(id=str(uuid.uuid4()), name="Notebooks", enabled=True, priority=15,
                 filter=FilterCondition(type="extension", values=["ipynb"]),
                 destination_template="{category}/Code/Notebooks/{name}.{ext}", conflict_mode="rename", tags=["code"]),
            Rule(id=str(uuid.uuid4()), name="Archives", enabled=True, priority=16,
                 filter=FilterCondition(type="extension", values=["zip","rar","7z","tar","gz","bz2","xz","dmg","iso"]),
                 destination_template="{category}/Archives/{name}.{ext}", conflict_mode="rename", tags=["data"]),
            Rule(id=str(uuid.uuid4()), name="Datasets", enabled=True, priority=17,
                 filter=FilterCondition(type="extension", values=["csv","xlsx","parquet","jsonl","feather","pickle","pkl"]),
                 destination_template="{category}/Datasets/{name}.{ext}", conflict_mode="rename", tags=["data"]),
            Rule(id=str(uuid.uuid4()), name="Design Assets", enabled=True, priority=18,
                 filter=FilterCondition(type="extension", values=["psd","ai","fig","sketch","afdesign","xd"]),
                 destination_template="{category}/Assets/Design/{name}.{ext}", conflict_mode="rename", tags=["assets"]),
            Rule(id=str(uuid.uuid4()), name="Fonts", enabled=True, priority=19,
                 filter=FilterCondition(type="extension", values=["ttf","otf","woff","woff2","eot"]),
                 destination_template="{category}/Assets/Fonts/{name}.{ext}", conflict_mode="rename", tags=["assets"]),
            Rule(id=str(uuid.uuid4()), name="Executables", enabled=True, priority=20,
                 filter=FilterCondition(type="extension", values=["exe","msi","app","dmg","pkg","deb","rpm","apk"]),
                 destination_template="{category}/Apps/{name}.{ext}", conflict_mode="rename", tags=["apps"]),

            # ── Special Rules ─────────────────────────────────────────
            Rule(id=str(uuid.uuid4()), name="Screenshots", enabled=True, priority=50,
                 filter=FilterCondition(type="name_contains", values=["Screenshot","Skärmbild","Skärmavbild"]),
                 destination_template="{category}/Screenshots/{year}/{month}/{name}.{ext}", conflict_mode="rename", tags=["special","images"]),
            Rule(id=str(uuid.uuid4()), name="Camera Photos", enabled=True, priority=51,
                 filter=FilterCondition(type="name_contains", values=["IMG_","DSC_","PICT_","DSC0"]),
                 destination_template="{category}/Camera/{year}/{month}/{name}.{ext}", conflict_mode="rename", tags=["special","images"]),
            Rule(id=str(uuid.uuid4()), name="Temp Files", enabled=True, priority=95,
                 filter=FilterCondition(type="extension", values=["tmp","temp","log","cache","lock","bak","old","swp","swo"]),
                 destination_template="{category}/Temp/{name}.{ext}", conflict_mode="rename", tags=["temp"]),

            # ── Fallback ───────────────────────────────────────────────
            Rule(id=str(uuid.uuid4()), name="Unknown / No Extension", enabled=True, priority=98,
                 filter=FilterCondition(type="no_extension"),
                 destination_template="{category}/Unknown/{name}", conflict_mode="skip", tags=["unknown"]),
            Rule(id=str(uuid.uuid4()), name="Fallback", enabled=True, priority=99,
                 filter=FilterCondition(type="default"),
                 destination_template="{category}/{name}.{ext}", conflict_mode="rename", tags=["fallback"]),
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
