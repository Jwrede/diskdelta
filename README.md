# diskdelta

When a small server runs out of disk, the first question is what grew. `du` and `ncdu` show
what is large now; `diskdelta` shows what changed. Each run records the size of every directory
up to a chosen depth, then prints the growth since the previous run and since a week ago, and
can exit non-zero when free space falls below a threshold.

Run it from cron once a day and the next "disk full" starts with an answer.

## Install

```
pipx install git+https://github.com/Jwrede/diskdelta
```

or without installing:

```
uvx --from git+https://github.com/Jwrede/diskdelta diskdelta
```

Python 3.10+, no dependencies.

## Usage

```
$ diskdelta / --depth 3 --min-free 2G
2026-10-25 04:30  /  free 3.1G

Growth since last run (2026-10-24 04:30, free then 5.6G, change -2.5G):
      2.1G  /tmp/render-cache
    290.4M  /home/dev/.cache/uv
     61.0M  /var/log/journal

Growth since 7 days (2026-10-18 04:30, free then 8.4G, change -5.3G):
      2.1G  /tmp/render-cache
      1.9G  /home/dev/.local/share/claude/versions
    ...

Largest directories:
     14.2G  /home
      ...
```

(Example output with illustrative paths.)

| Option | Meaning |
|---|---|
| `root` | directory to scan, default `/` |
| `--depth N` | directory levels recorded below root (default 3) |
| `--min-free SIZE` | print `ALERT` and exit 2 when free space is below SIZE (`2G`, `500M`) |
| `--top N` | rows per table (default 10) |
| `--state DIR` | where snapshots are stored (default `~/.local/state/diskdelta`) |
| `--keep N` | snapshots to keep (default 30) |

How sizes are measured:

- Sizes are allocated blocks, as `du` reports them.
- Hard links count once.
- Symlinks are not followed, and the scan stays on the filesystem of `root`.
- Unreadable directories are skipped, so run it as root for a full picture of `/`.

The growth table names the deepest recorded directory that explains a change, so a 2 GB cache
is listed once and does not repeat for each of its parents.

## Cron example

```
30 4 * * * timeout 900 diskdelta / --depth 3 --min-free 2G >> ~/diskdelta.log 2>&1
```

## License

MIT
