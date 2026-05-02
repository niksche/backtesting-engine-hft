"""Carve a head-of-file sample from data/lob.csv and data/trades.csv.

Both output files cover the same wall-clock window so the EventStream merge
makes sense on the carve-out. Window starts at the earlier of the two first
timestamps and runs for `--seconds` (default 30).

Usage:
    python scripts/make_sample.py [--seconds 30]
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
SAMPLES_DIR = DATA_DIR / "samples"


def _first_timestamp(path: Path) -> int:
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header
        first = next(reader)
        return int(first[1])


def _carve(src: Path, dst: Path, end_ts_us: int) -> int:
    """Copy rows from `src` into `dst` while local_timestamp <= end_ts_us.

    Returns the number of data rows written.
    """
    n = 0
    with open(src, newline="") as fin, open(dst, "w", newline="") as fout:
        reader = csv.reader(fin)
        writer = csv.writer(fout)
        writer.writerow(next(reader))  # header
        for row in reader:
            if int(row[1]) > end_ts_us:
                break
            writer.writerow(row)
            n += 1
    return n


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seconds", type=float, default=30.0, help="window length (default 30s)")
    p.add_argument("--lob", type=Path, default=DATA_DIR / "lob.csv")
    p.add_argument("--trades", type=Path, default=DATA_DIR / "trades.csv")
    p.add_argument("--out-dir", type=Path, default=SAMPLES_DIR)
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    start = min(_first_timestamp(args.lob), _first_timestamp(args.trades))
    end = start + int(args.seconds * 1_000_000)

    lob_dst = args.out_dir / "lob_sample.csv"
    trd_dst = args.out_dir / "trades_sample.csv"
    lob_n = _carve(args.lob, lob_dst, end)
    trd_n = _carve(args.trades, trd_dst, end)
    print(f"Wrote {lob_n} lob rows -> {lob_dst}")
    print(f"Wrote {trd_n} trade rows -> {trd_dst}")
    print(f"Window: {args.seconds}s starting at ts={start}us")


if __name__ == "__main__":
    main()
