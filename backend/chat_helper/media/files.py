"""Temporary file management with path-traversal protection and automatic cleanup."""
from __future__ import annotations

import os
import secrets
import shutil
import time
from pathlib import Path

from ..security.sanitize import safe_filename, safe_join


class TempFiles:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.base.mkdir(parents=True, exist_ok=True)

    def job_dir(self, prefix: str = "job") -> Path:
        d = safe_join(self.base, f"{safe_filename(prefix)}_{int(time.time())}_{secrets.token_hex(4)}")
        d.mkdir(parents=True, exist_ok=False)
        return d

    def path(self, directory: Path, name: str) -> Path:
        return safe_join(directory, safe_filename(name))

    def discard(self, path: Path | str) -> None:
        p = Path(path)
        try:
            target = p if p.is_dir() else p.parent
            target = safe_join(self.base, str(target.resolve().relative_to(self.base.resolve())))
            if target != self.base.resolve():
                shutil.rmtree(target, ignore_errors=True)
            elif p.is_file():
                p.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    def cleanup(self, max_age_sec: int = 3600) -> tuple[int, int]:
        """Remove stale job directories. Returns (removed_entries, freed_bytes)."""
        removed, freed = 0, 0
        now = time.time()
        for entry in self.base.iterdir():
            try:
                if now - entry.stat().st_mtime < max_age_sec:
                    continue
                size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file()) if entry.is_dir() else entry.stat().st_size
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
                removed += 1
                freed += size
            except OSError:
                continue
        return removed, freed

    def usage(self) -> dict[str, int]:
        total, count = 0, 0
        for root, _d, files in os.walk(self.base):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                    count += 1
                except OSError:
                    pass
        return {"bytes": total, "files": count}
