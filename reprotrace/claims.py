from __future__ import annotations
from pathlib import Path
import re

NUMBER_RE = re.compile(
    r"(?<![\w.])(?<!-)[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?%?"
)

MODEL_PATTERNS = [
    re.compile(r"\bGPT[-\s]?\d+(?:\.\d+)?(?:\s+(?:Nano|Mini|Pro|Turbo))?\b", re.I),
    re.compile(r"\bClaude\s+(?:Opus|Haiku|Sonnet)\s+\d+(?:\.\d+)?\b", re.I),
    re.compile(r"\b(?:Opus|Haiku|Sonnet)\s+\d+(?:\.\d+)?\b", re.I),
    re.compile(r"\bGemini\s+(?:Pro|Flash)?\s*\d*(?:\.\d+)?\b", re.I),
    re.compile(r"\bGLM\s+\d+(?:\.\d+)?\b", re.I),
    re.compile(r"\bGrok\s+\d+(?:\.\d+)?\b", re.I),
]

FORMAT_LINE_PATTERNS = [
    re.compile(r"^\s*\\documentclass", re.I),
    re.compile(r"^\s*\\usepackage", re.I),
    re.compile(r"^\s*(linkcolor|citecolor|urlcolor)\s*=", re.I),
    re.compile(r"\\includegraphics\s*\[", re.I),
    re.compile(r"^\s*\\(?:setlength|vspace|hspace|fontsize|geometry)", re.I),
]

RATE_TERMS = {
    "rate","success","accuracy","auc","auroc","ap","precision","recall","f1",
    "evasion","undetected","sabotage","safety","caught","performance","error","loss"
}
COUNT_TERMS = {
    "task","tasks","environment","environments","trajectory","trajectories","container",
    "containers","sample","samples","image","images","video","videos","pair","pairs",
    "model","models","monitor","monitors","category","categories","contractor","contractors"
}
HYPER_TERMS = {"seed","seeds","epoch","epochs","batch","lambda","temperature","top-k","topk"}

def normalize_latex_text(text: str) -> str:
    text = re.sub(r"(?<=\d)\{,\}(?=\d)", ",", text)
    text = text.replace(r"\%", "%")
    return text

def parse_number(raw: str):
    s = raw.replace(",", "")
    pct = s.endswith("%")
    if pct:
        s = s[:-1]
    try:
        v = float(s)
        return (v / 100.0 if pct else v), pct
    except ValueError:
        return None, pct

def spans(patterns, line):
    out = []
    for p in patterns:
        out.extend(m.span() for m in p.finditer(line))
    return out

def inside(span, spans_):
    a, b = span
    return any(a >= x and b <= y for x, y in spans_)

def clause_for(line: str, start: int, end: int) -> str:
    # Local clause, not a 280-character indiscriminate window.
    lefts = [line.rfind(x, 0, start) for x in [". ", "; ", r"\\"]]
    left = max(lefts)
    left = 0 if left < 0 else left + 2
    rights = [p for x in [". ", "; ", r"\\"] if (p := line.find(x, end)) >= 0]
    right = min(rights) if rights else len(line)
    return line[left:right].strip()

def enumeration_spans(line: str):
    return [m.span(1) for m in re.finditer(r"\((\d{1,2})\)\s*\\?(?:textbf)?", line)]

def range_spans(line: str):
    return [m.span() for m in re.finditer(r"\b\d+(?:\.\d+)?\s*--?\s*\d+(?:\.\d+)?\b", line)]

def classify_number(line: str, clause: str, m, raw: str, pct: bool):
    stripped = line.strip()
    if any(p.search(stripped) for p in FORMAT_LINE_PATTERNS):
        return "IGNORED", "OTHER", "latex_formatting"

    if inside(m.span(), spans(MODEL_PATTERNS, line)):
        return "IGNORED", "OTHER", "model_version"

    if inside(m.span(), enumeration_spans(line)):
        return "IGNORED", "ENUMERATION", "enumeration_marker"

    around = line[max(0, m.start()-6):min(len(line), m.end()+8)]
    if re.search(r"\d+(?:\.\d+)?\s*(?:em|pt|in|cm|mm)\b", around, re.I):
        return "IGNORED", "OTHER", "layout_dimension"

    low = clause.lower()
    words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]*", low))

    # Statistical confidence metadata, not a reported measured value.
    if pct and re.search(r"\b(?:ci|confidence\s+interval|confidence\s+level)\b", low):
        return "IGNORED", "CONFIDENCE_LEVEL", "confidence_metadata"

    # Operating point: only when FPR is immediately tied to THIS number.
    after = line[m.end():m.end()+45].lower()
    before = line[max(0,m.start()-35):m.start()].lower()
    if pct and (
        re.match(r"\s*(?:step-wise\s*)?(?:fpr|false\s+positive\s+rate)\b", after)
        or re.search(r"(?:fpr|false\s+positive\s+rate)\s*(?:of|=|:)??\s*$", before)
    ):
        return "CONDITION", "OPERATING_POINT_FPR", "fpr_operating_point"

    # Step caps / counts.
    if re.search(r"\b(step|steps|action|actions)[-\s]*(?:cap|limit)\b", low) or \
       re.search(r"\b(?:cap|limit)\b.{0,20}\b(step|steps|action|actions)\b", low):
        return "HYPERPARAM", "STEP_CAP", "step_cap"

    if words & HYPER_TERMS:
        return "HYPERPARAM", "OTHER", "hyperparameter_context"

    # Percentages in performance clauses are result rates.
    if pct and (words & RATE_TERMS):
        return "RESULT_METRIC", "RESULT_RATE", "rate_context"

    # Count nouns near integer.
    if words & COUNT_TERMS and not pct:
        return "DATASET_FACT", "COUNT", "count_context"

    # Table rows tend to be structured facts; keep conservative.
    if "&" in line and r"\\" in line and not pct:
        return "DATASET_FACT", "COUNT", "table_numeric_fact"

    # Ranges are conditions/bins, not primary result claims.
    if inside(m.span(), range_spans(line)):
        return "CONDITION", "OTHER", "range_bound"

    if pct:
        return "RESULT_METRIC", "RESULT_RATE", "generic_percentage"

    return "NON_RESULT", "OTHER", "no_research_signal"

def extract_claims(manuscript: Path) -> list[dict]:
    if manuscript.suffix.lower() not in {".tex", ".md", ".txt"}:
        raise ValueError("v0.3 supports manuscript files: .tex, .md, .txt")
    text = normalize_latex_text(manuscript.read_text(encoding="utf-8", errors="ignore"))
    out = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        for m in NUMBER_RE.finditer(line):
            raw = m.group(0)
            value, pct = parse_number(raw)
            if value is None:
                continue
            clause = clause_for(line, m.start(), m.end())
            ctype, role, reason = classify_number(line, clause, m, raw, pct)
            out.append({
                "value": value,
                "raw": raw,
                "display_value": raw,
                "is_percent": pct,
                "line": line_no,
                "context": clause,
                "claim_type": ctype,
                "claim_role": role,
                "classification_reason": reason,
            })
    return out
