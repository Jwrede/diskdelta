import os
from pathlib import Path

import pytest

from diskdelta.cli import main
from diskdelta.core import growth, human, parse_size, pick_baseline, scan


def write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(os.urandom(size))


def test_scan_depth_and_sizes(tmp_path):
    write(tmp_path / "a/b/c/big.bin", 200_000)
    write(tmp_path / "a/small.bin", 10_000)
    sizes = scan(tmp_path, depth=2)
    root = str(tmp_path.resolve())
    assert set(sizes) == {root, f"{root}/a", f"{root}/a/b"}
    assert sizes[f"{root}/a/b"] >= 200_000
    assert sizes[f"{root}/a"] >= sizes[f"{root}/a/b"] + 10_000
    assert sizes[root] >= sizes[f"{root}/a"]


def test_scan_counts_hardlinks_once_and_skips_symlinks(tmp_path):
    write(tmp_path / "x/data.bin", 300_000)
    os.link(tmp_path / "x/data.bin", tmp_path / "x/link.bin")
    (tmp_path / "loop").symlink_to(tmp_path)
    sizes = scan(tmp_path, depth=1)
    assert sizes[str((tmp_path / "x").resolve())] < 2 * 300_000


def test_growth_points_at_deepest_directory():
    old = {"/r": 100, "/r/a": 60, "/r/a/cache": 10, "/r/b": 40}
    new = {"/r": 600, "/r/a": 560, "/r/a/cache": 510, "/r/b": 40}
    rows = dict(growth(new, old))
    assert rows == {"/r/a/cache": 500}


def test_growth_hides_parent_explained_by_child():
    # /var/log grew by a log file directly inside it; /var only adds a few KB on top.
    old = {"/": 1000, "/var": 300, "/var/log": 200, "/var/log/journal": 50}
    new = {"/": 1000 + 119_000, "/var": 300 + 113_900, "/var/log": 200 + 113_700, "/var/log/journal": 50 + 24_500}
    rows = dict(growth(new, old))
    assert "/var" not in rows and "/" not in rows
    assert rows["/var/log"] == 113_700
    assert rows["/var/log/journal"] == 24_500


def test_growth_keeps_parent_when_children_share_the_change():
    old = {"/r": 0, "/r/a": 0, "/r/b": 0}
    new = {"/r": 100, "/r/a": 50, "/r/b": 50}
    assert dict(growth(new, old)) == {"/r": 100, "/r/a": 50, "/r/b": 50}


def test_growth_reports_new_and_shrinking_paths():
    rows = dict(growth({"/r": 50, "/r/new": 70}, {"/r": 100, "/r/gone": 100}))
    assert rows["/r/new"] == 70
    assert rows["/r"] == -50


def test_pick_baseline():
    snaps = [{"time": 0}, {"time": 100}, {"time": 500}]
    assert pick_baseline(snaps, now=600, age_seconds=400)["time"] == 100
    assert pick_baseline(snaps, now=600, age_seconds=1000) is None


@pytest.mark.parametrize(
    "text,value", [("2G", 2 * 1024**3), ("500M", 500 * 1024**2), ("1.5GiB", int(1.5 * 1024**3)), ("10", 10)]
)
def test_parse_size(text, value):
    assert parse_size(text) == value


def test_human():
    assert human(512) == "512B"
    assert human(3 * 1024**3) == "3.0G"
    assert human(-2048) == "-2.0K"


def test_cli_reports_growth_and_alert(tmp_path, capsys):
    data, state = tmp_path / "data", tmp_path / "state"
    write(data / "keep/file.bin", 50_000)
    assert main([str(data), "--state", str(state)]) == 0
    first = capsys.readouterr().out
    assert "no snapshot yet" in first

    write(data / "keep/logs/huge.log", 400_000)
    assert main([str(data), "--state", str(state)]) == 0
    second = capsys.readouterr().out
    assert "Growth since last run" in second
    growth_lines = second.split("Growth since last run")[1].split("\n\n")[0]
    assert str((data / "keep/logs").resolve()) in growth_lines

    assert main([str(data), "--state", str(state), "--min-free", "1000T"]) == 2
    assert "ALERT" in capsys.readouterr().out


def test_cli_keeps_limited_snapshots(tmp_path):
    data, state = tmp_path / "data", tmp_path / "state"
    data.mkdir()
    for _ in range(4):
        main([str(data), "--state", str(state), "--keep", "2"])
    assert len(list(state.glob("snapshot-*.json"))) <= 2
