"""Check that this machine is ready for the Monopoly Meta jobs, and print a pass/warn/fail table.

    make doctor        (or: python scripts/doctor.py [--quick])

Sections that later phases need (Rust, the GPU) are reported as "later" until then.
Exit code 1 if anything fails.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
rows: list[tuple[str, str, str]] = []


def add(status: str, check: str, detail: str) -> None:
    rows.append((status, check, detail))


def sh(*cmd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=600)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def meminfo_gb() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 1024 ** 2
    except OSError:
        return None
    return None


def free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1024 ** 3


def system() -> None:
    v = Path("/proc/version").read_text() if Path("/proc/version").exists() else platform.platform()
    wsl = "microsoft" in v.lower()
    add("PASS" if wsl else "WARN", "Running under WSL2", "yes" if wsl else f"no ({platform.platform()})")
    n = os.cpu_count() or 1
    add("PASS" if n >= 16 else "WARN", "CPU threads", f"{n} (the jobs use all of them)")
    mem = meminfo_gb()
    if mem is not None:
        add("PASS" if mem >= 12 else "WARN", "Memory available to Linux",
            f"{mem:.1f} GB" + ("" if mem >= 12 else "; raise it in %UserProfile%\\.wslconfig ([wsl2] memory=...)"))
    repo_free = free_gb(ROOT)
    add("PASS" if repo_free >= 5 else "FAIL", "Free disk where the repo lives", f"{repo_free:.0f} GB at {ROOT}")
    home_free = free_gb(Path.home())
    add("PASS" if home_free >= 60 else "WARN", "Free disk on the WSL disk (later: 10-40 GB of positions)",
        f"{home_free:.0f} GB at {Path.home()}")
    on_windows_drive = str(ROOT).startswith("/mnt/")
    add("PASS", "Repo location", f"{ROOT}" + (" (Windows drive: fine for these jobs)" if on_windows_drive else ""))


def git_checks() -> None:
    code, out = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    add("PASS" if code == 0 and out == "main" else "WARN", "Git branch", out or "not a git repo")
    _, crlf = sh("git", "config", "--get", "core.autocrlf")
    _, mode = sh("git", "config", "--get", "core.fileMode")
    ok = crlf in ("", "false", "input") and mode == "false"
    add("PASS" if ok else "WARN", "Git settings for a Windows-drive checkout",
        f"core.autocrlf={crlf or 'unset'}, core.fileMode={mode or 'unset'} (bootstrap.sh sets these)")
    _, eol = sh("git", "ls-files", "--eol")
    n_crlf = sum("w/crlf" in line for line in eol.splitlines())
    add("PASS" if n_crlf == 0 else "WARN", "Line endings in the working tree",
        "all LF" if n_crlf == 0 else f"{n_crlf} files still CRLF; rerun bash bootstrap.sh")
    _, email = sh("git", "config", "--get", "user.email")
    add("PASS" if email else "FAIL", "Git identity for result commits", email or "missing; rerun bash bootstrap.sh")


def python_checks(quick: bool) -> None:
    ok = sys.version_info[:2] == (3, 12)
    add("PASS" if ok else "WARN", "Python", f"{platform.python_version()} at {sys.executable}")
    try:
        import numpy
        import pandas

        import monopoly_meta  # noqa: F401
        add("PASS", "Packages", f"monopoly_meta, numpy {numpy.__version__}, pandas {pandas.__version__}")
    except ImportError as e:
        add("FAIL", "Packages", f"{e}; run make setup")
        return
    code, out = sh(sys.executable, "tests/golden.py")
    add("PASS" if code == 0 else "FAIL", "Regression digests (identical games to v0.3)",
        out.splitlines()[-1] if out else "")
    if not quick:
        code, out = sh(sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider")
        last = out.splitlines()[-1] if out else ""
        add("PASS" if code == 0 else "FAIL", "Test suite", last)


def benchmark() -> None:
    from monopoly_meta import Game
    from monopoly_meta.policies import make_bot
    from monopoly_meta.tournament import run_games

    t, turns, games = time.perf_counter(), 0, 0
    while time.perf_counter() - t < 4:
        turns += Game([make_bot("balanced") for _ in range(4)], seed=games).play().turns
        games += 1
    one = turns / (time.perf_counter() - t)
    t = time.perf_counter()
    df = run_games(["balanced"] * 4, 400 * (os.cpu_count() or 1), seed0=1)
    allc = df.turns.sum() / (time.perf_counter() - t) if "turns" in df else float("nan")
    add("INFO", "Python engine speed, 4 players", f"{one:,.0f} player-turns/s on one core; "
                                                  f"{allc:,.0f}/s on all threads")


def later() -> None:
    rust = shutil.which("cargo")
    add("PASS" if rust else "LATER", "Rust toolchain (Phase A, week 5)",
        "found" if rust else "installed by make setup-rust")
    gpu = shutil.which("nvidia-smi")
    if gpu:
        code, out = sh("nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader")
        add("PASS" if code == 0 else "WARN", "GPU visible in WSL (Phase D)", out)
    else:
        add("LATER", "GPU visible in WSL (Phase D)", "checked again by make setup-gpu")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="skip the full test suite and the benchmark")
    a = ap.parse_args()
    system()
    git_checks()
    python_checks(a.quick)
    if not a.quick:
        benchmark()
    later()
    w = max(len(c) for _, c, _ in rows)
    print(f"\n{'':6}{'Check':{w}}  Detail")
    for status, check, detail in rows:
        print(f"{status:6}{check:{w}}  {detail}")
    fails = sum(s == "FAIL" for s, _, _ in rows)
    print(f"\n{'All checks passed.' if not fails else f'{fails} check(s) failed.'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
