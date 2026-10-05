from __future__ import annotations
from pathlib import Path
import csv, json, re
from .utils import finite_number, tokenize

SUPPORTED = {".csv", ".json", ".log", ".txt", ".yaml", ".yml", ".toml", ".py"}

NUM = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?"
KEYVAL_RE = re.compile(rf"\b([A-Za-z_][A-Za-z0-9_\- ]{{0,35}}?)\s*[:=]\s*({NUM})(%)?")
TRAILING_UNIT_RE = re.compile(rf"(?<![\w.])({NUM})(%)?\s*(trajs?|trajectories|tasks?|steps?|actions?|models?|monitors?)\b", re.I)
FPR_RE = re.compile(rf"({NUM})%\s*(?:step-wise\s*)?(?:FPR|false positive rate)\b", re.I)

def infer_role(label: str, context: str, is_percent=False):
    s = f"{label} {context}".lower()

    if re.search(r"\bfpr\b|false[_\s-]*positive", s):
        return "OPERATING_POINT_FPR"
    if re.search(r"\b(n|count|num|number|size|n_trajectories|trajs?|trajectories|tasks?|samples?|models?|monitors?)\b", s):
        return "COUNT"
    if re.search(r"\b(seed|random_seed)\b", s):
        return "SEED"
    if re.search(r"\b(step_cap|max_steps|action_limit|step_limit)\b", s):
        return "STEP_CAP"
    if re.search(r"\bthreshold\b", s):
        return "THRESHOLD"
    if re.search(r"\b(ci|confidence)\b", s):
        return "CONFIDENCE_LEVEL"
    if is_percent or re.search(r"\b(safety|success|sabotage|evasion|undetected|caught|accuracy|auc|auroc|precision|recall|f1|rate|loss|error)\b", s):
        return "RESULT_RATE"
    return "OTHER"

def classify_source(path: str):
    p = path.lower().replace("\\", "/")
    if any(x in p for x in ["safety_cache", "metrics", "results", "result", "evaluation", "eval_"]) and "run_ids" not in p:
        return "DERIVED_RESULT", 1.0
    if "run_ids" in p or "metadata" in p:
        return "RUN_METADATA", 0.55
    if p.endswith(".log"):
        return "LOG", 0.70
    if "task_sets" in p or "dataset" in p:
        return "DATA_DEFINITION", 0.70
    if any(x in p for x in ["config", ".yaml", ".yml", ".toml"]):
        return "CONFIG", 0.65
    if p.endswith(".py"):
        return "CODE", 0.45
    if "readme" in p or "docs" in p:
        return "DOCUMENTATION", 0.20
    return "OTHER", 0.30

def make_record(value, source, locator, evidence_text, is_percent=False, explicit_role=None):
    try:
        v = float(str(value).replace(",", ""))
    except Exception:
        return None
    if not finite_number(v):
        return None
    if is_percent:
        v = v / 100.0
    stype, sweight = classify_source(source)
    role = explicit_role or infer_role(locator, evidence_text, is_percent)
    all_text = f"{source} {locator} {evidence_text}"
    return {
        "value": v,
        "source": source,
        "locator": locator,
        "evidence_text": evidence_text[:240],
        "source_type": stype,
        "source_weight": sweight,
        "evidence_role": role,
        "tokens": sorted(tokenize(all_text)),
    }

def flatten_json(obj, prefix=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.extend(flatten_json(v, key))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(flatten_json(v, f"{prefix}[{i}]"))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool) and finite_number(obj):
        out.append((prefix, float(obj)))
    return out

def parse_text_line(line, source, line_no):
    recs = []
    occupied = []

    for m in FPR_RE.finditer(line):
        rec = make_record(m.group(1), source, f"line {line_no}: FPR", line, is_percent=True,
                          explicit_role="OPERATING_POINT_FPR")
        if rec: recs.append(rec)
        occupied.append(m.span())

    for m in KEYVAL_RE.finditer(line):
        label = m.group(1).strip()
        raw = m.group(2)
        pct = bool(m.group(3))
        rec = make_record(raw, source, f"line {line_no}: {label}", line, is_percent=pct)
        if rec: recs.append(rec)
        occupied.append(m.span())

    for m in TRAILING_UNIT_RE.finditer(line):
        raw, pct, unit = m.group(1), bool(m.group(2)), m.group(3)
        role = "COUNT" if not pct else "RESULT_RATE"
        rec = make_record(raw, source, f"line {line_no}: {unit}", line, is_percent=pct, explicit_role=role)
        if rec: recs.append(rec)
        occupied.append(m.span())

    # Conservative fallback: standalone comma-thousands counts.
    for m in re.finditer(r"\b\d{1,3}(?:,\d{3})+\b", line):
        if any(m.start() >= a and m.end() <= b for a,b in occupied):
            continue
        rec = make_record(m.group(0), source, f"line {line_no}: standalone_count", line, explicit_role="COUNT")
        if rec: recs.append(rec)

    return recs

def index_result_values(root: Path) -> list[dict]:
    values = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in SUPPORTED:
            continue
        rel = str(p.relative_to(root))
        try:
            if p.suffix.lower() == ".csv":
                with p.open("r", encoding="utf-8", errors="ignore", newline="") as f:
                    rows = list(csv.reader(f))
                if not rows:
                    continue
                headers = rows[0]
                for r_idx, row in enumerate(rows[1:], start=2):
                    for c, cell in enumerate(row):
                        try:
                            float(cell.strip().replace(",", ""))
                        except Exception:
                            continue
                        header = headers[c] if c < len(headers) else f"col_{c+1}"
                        pct = "%" in header
                        rec = make_record(cell, rel, f"row {r_idx}, {header}", header, is_percent=pct)
                        if rec: values.append(rec)

            elif p.suffix.lower() == ".json":
                obj = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                for key, v in flatten_json(obj):
                    rec = make_record(v, rel, key, key)
                    if rec: values.append(rec)

            else:
                for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                    values.extend(parse_text_line(line, rel, n))
        except Exception:
            continue

    # Deduplicate identical evidence records.
    seen, uniq = set(), []
    for r in values:
        k = (r["source"], r["locator"], r["value"], r["evidence_role"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq
