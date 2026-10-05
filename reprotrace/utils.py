from __future__ import annotations
import math, re

STOPWORDS = {
    "the","a","an","of","to","and","or","in","on","for","with","at","by","from",
    "is","are","was","were","be","as","our","we","this","that","these","those",
    "using","use","used","across","against","paper","figure","table","results","result",
    "task","tasks","value","values","data","dataset","datasets","main","side"
}

def finite_number(x) -> bool:
    try:
        return math.isfinite(float(x))
    except Exception:
        return False

def tokenize(text: str) -> set[str]:
    toks = re.findall(r"[A-Za-z_][A-Za-z0-9_\-]{1,}", text.lower())
    return {t for t in toks if t not in STOPWORDS and len(t) > 2}

def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def normalize_term(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
