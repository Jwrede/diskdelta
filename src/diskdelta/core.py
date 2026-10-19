from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path


def scan(root: Path, depth: int) -> dict[str, int]:
    """Return the on-disk size in bytes of `root` and of every directory up to `depth` levels below it.

    Sizes count allocated blocks (like `du`), each inode once, and stay on the
    filesystem of `root`. Symlinks are not followed. Unreadable entries are skipped.
    """
    root = root.resolve()
    root_dev = root.stat().st_dev
    sizes: dict[str, int] = {}
    seen: set[tuple[int, int]] = set()

    def walk(path: Path, level: int) -> int:
        total = 0
        try:
            entries = list(os.scandir(path))
        except OSError:
            return 0
        for e in entries:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if st.st_dev != root_dev:
                continue
            key = (st.st_dev, st.st_ino)
            if st.st_nlink > 1:
                if key in seen:
                    continue
                seen.add(key)
            if e.is_dir(follow_symlinks=False):
                total += st.st_blocks * 512 + walk(Path(e.path), level + 1)
            else:
                total += st.st_blocks * 512
        if level <= depth:
            sizes[str(path)] = total
        return total

    walk(root, 0)
    return sizes


def save(state_dir: Path, sizes: dict[str, int], free: int, now: float | None = None, keep: int = 30) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    now = time.time() if now is None else now
    path = state_dir / f"snapshot-{int(now)}.json"
    path.write_text(json.dumps({"time": now, "free": free, "sizes": sizes}))
    for old in list_snapshots(state_dir)[:-keep]:
        old.unlink()
    return path


def list_snapshots(state_dir: Path) -> list[Path]:
    if not state_dir.is_dir():
        return []
    return sorted(state_dir.glob("snapshot-*.json"), key=lambda p: int(p.stem.split("-")[1]))


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def pick_baseline(snapshots: list[dict], now: float, age_seconds: float) -> dict | None:
    """The newest snapshot that is at least `age_seconds` old."""
    old = [s for s in snapshots if now - s["time"] >= age_seconds]
    return max(old, key=lambda s: s["time"]) if old else None


def growth(new: dict[str, int], old: dict[str, int], share: float = 0.9) -> list[tuple[str, int]]:
    """Size change per path, largest growth first. Paths only in `new` count from zero.

    A directory is left out when one of its recorded subdirectories accounts for at
    least `share` of its change, so the output points at the deepest directory that
    explains the growth.
    """
    deltas = {p: new[p] - old.get(p, 0) for p in new}
    out = []
    for p, d in deltas.items():
        if d == 0:
            continue
        children = [c for c in deltas if os.path.dirname(c) == p and c != p]
        if any(deltas[c] * d > 0 and abs(deltas[c]) >= share * abs(d) for c in children):
            continue
        out.append((p, d))
    return sorted(out, key=lambda x: x[1], reverse=True)


def free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def parse_size(text: str) -> int:
    units = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    t = text.strip().upper().removesuffix("B").removesuffix("I")
    num = t.rstrip("KMGT")
    unit = t[len(num) :]
    if unit not in units or not num:
        raise ValueError(f"cannot parse size {text!r}")
    return int(float(num) * units[unit])


def human(n: int) -> str:
    sign = "-" if n < 0 else ""
    n = abs(n)
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024 or unit == "T":
            return f"{sign}{n:.0f}{unit}" if unit == "B" else f"{sign}{n:.1f}{unit}"
        n /= 1024
    return f"{sign}{n:.1f}T"
