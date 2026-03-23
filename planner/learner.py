"""Rule learning — tracks approved actions and suggests rules."""
import os, json
from pathlib import Path
from collections import Counter
DATA = Path("data/learner.jsonl")

def log_approved(path: str, rule_id: str, action: str):
    """Log an approved action."""
    ext = os.path.splitext(path)[1].lower()
    with open(DATA, "a") as f:
        f.write(json.dumps({"path": path, "rule_id": rule_id, "action": action, "ext": ext}) + "\n")

def suggest(n: int = 5):
    """Suggest rules based on learned patterns."""
    counter = Counter()
    if DATA.exists():
        with open(DATA) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    counter[(e.get("ext",""), e.get("action",""))] += 1
                except: pass
    out = []
    for (ext, action), count in counter.most_common(n):
        if count < 3: continue
        out.append({"ext": ext, "action": action, "confidence": min(count/10, 1.0), "count": count})
    return out

# Required aliases
log_approved_action = log_approved
suggest_rules = suggest
