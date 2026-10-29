"""Start a deeper run's results folder from the current tables, so the scripts find their inputs.

    MM_RESULTS=results/v04 python scripts/deep_prepare.py

Copies results/tables into <MM_RESULTS>/tables, leaving out the archives and the checkpoints of the
studies a deeper run recomputes (the every-property trade curves and the per-size Vine Street curves
under meta play), so those run again at the new sample size. Safe to run again: a folder that was
prepared before is left as it is.
"""
import shutil

from run_config import ROOT, SCALE, TABLES

SOURCE = ROOT / "results" / "tables"
RECOMPUTED = ["property_trades", "meta_standard/trade_*p.csv", "meta_championship/trade_*p.csv",
              "meta_standard/exploit", "meta_championship/exploit"]


def shown(p):
    """A path relative to the repo when it is inside it (MM_RESULTS may also be an absolute path)."""
    try:
        return p.relative_to(ROOT)
    except ValueError:
        return p


def main():
    if TABLES.resolve() == SOURCE.resolve():
        raise SystemExit("Set MM_RESULTS to a new folder, e.g. MM_RESULTS=results/v04")
    marker = TABLES / ".prepared"
    if marker.exists():
        print(f"{shown(TABLES)} already prepared")
        return
    if TABLES.exists():  # an attempt that stopped half-way
        shutil.rmtree(TABLES)
    shutil.copytree(SOURCE, TABLES, ignore=shutil.ignore_patterns("archive_*"))
    for pattern in RECOMPUTED:
        for p in TABLES.glob(pattern):
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    marker.write_text(f"copied from results/tables; sample scale {SCALE:g}\n")
    print(f"prepared {shown(TABLES)} from results/tables (scale {SCALE:g})")


if __name__ == "__main__":
    main()
