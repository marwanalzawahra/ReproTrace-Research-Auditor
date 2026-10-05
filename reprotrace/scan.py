from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib

SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".idea", ".vscode", "audit", "audit_v02", "audit_v03", "demo_report"
}

@dataclass
class FileRecord:
    path: str
    suffix: str
    size_bytes: int
    sha256: str
    mtime: float

def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def inventory(root: Path) -> list[dict]:
    rows = []
    for p in root.rglob("*"):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.parts):
            continue
        try:
            stat = p.stat()
            rows.append(asdict(FileRecord(
                path=str(p.relative_to(root)),
                suffix=p.suffix.lower(),
                size_bytes=stat.st_size,
                sha256=sha256_file(p),
                mtime=stat.st_mtime,
            )))
        except (OSError, PermissionError):
            continue
    return sorted(rows, key=lambda x: x["path"])
