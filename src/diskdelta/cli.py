from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from diskdelta import __version__
from diskdelta.core import free_bytes, growth, human, list_snapshots, load, parse_size, pick_baseline, save, scan

DEFAULT_STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "diskdelta"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="diskdelta",
        description="Snapshot directory sizes and show what grew since the last run and since a week ago.",
    )
    ap.add_argument("root", nargs="?", default="/", type=Path, help="directory to scan (default /)")
    ap.add_argument("--depth", type=int, default=3, help="directory levels to record below root (default 3)")
    ap.add_argument("--top", type=int, default=10, help="rows per table (default 10)")
    ap.add_argument("--min-free", type=parse_size, help="exit 2 and print ALERT when free space is below this, e.g. 2G")
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE, help=f"snapshot directory (default {DEFAULT_STATE})")
    ap.add_argument("--keep", type=int, default=30, help="snapshots to keep (default 30)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    now = time.time()
    previous = [load(p) for p in list_snapshots(args.state)]
    sizes = scan(args.root, args.depth)
    free = free_bytes(args.root)
    save(args.state, sizes, free, now, args.keep)

    print(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(now))}  {args.root}  free {human(free)}")
    for label, base in (
        ("last run", previous[-1] if previous else None),
        ("7 days", pick_baseline(previous, now, 7 * 86400)),
    ):
        if base is None:
            print(f"\nGrowth since {label}: no snapshot yet")
            continue
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(base["time"]))
        print(f"\nGrowth since {label} ({when}, free then {human(base['free'])}, change {human(free - base['free'])}):")
        rows = [r for r in growth(sizes, base["sizes"]) if r[1] > 0][: args.top]
        for path, delta in rows:
            print(f"  {human(delta):>8}  {path}")
        if not rows:
            print("  nothing grew")

    print("\nLargest directories:")
    largest = sorted(((p, s) for p, s in sizes.items() if p != str(args.root.resolve())), key=lambda x: -x[1])
    for path, size in largest[: args.top]:
        print(f"  {human(size):>8}  {path}")

    if args.min_free is not None and free < args.min_free:
        print(f"\nALERT: free space {human(free)} is below {human(args.min_free)}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
