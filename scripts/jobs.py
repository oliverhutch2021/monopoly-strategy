"""Run the heavy jobs on the PC: resumable, low priority, and self-reporting.

    python scripts/jobs.py sync          # fast-forward main to the code Claude left in .sync/claude.bundle
    python scripts/jobs.py run v03       # run (or resume) a job; `make v03` calls this
    python scripts/jobs.py status        # which steps of which jobs are done

A job is a list of steps. Each finished step is recorded in .sync/state/<job>.json, so running the
same command again skips it. A job refuses to resume on different code (another commit), because
its checkpoints would mix two versions; pass --force to restart it on the new code.

When every step has finished, the job
  1. writes a stamp to results/runs/<job>.json (commit, machine, Python, timings),
  2. commits everything under results/ on main,
  3. writes .sync/from-pc.bundle (your new commits) and .sync/DONE-<job>.txt for Claude to read.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / ".sync"
STATE = SYNC / "state"
LOGS = SYNC / "logs"
WATCH = SYNC / "watch"  # what the live viewer reads (scripts/watch.py)
PY = sys.executable

# A step is (name, argv) or (name, argv, env): env adds variables for that step, e.g. a results folder and a
# sample-size multiplier (scripts/run_config.py). Steps run in order; finished ones are skipped on a rerun.
V04 = {"MM_RESULTS": "results/v04", "MM_SCALE": "10"}
V05 = {"MM_RESULTS": "results/v05", "MM_SCALE": "10"}

JOBS: dict[str, list[tuple]] = {
    # Finish v0.3 on the untouched engine (see RUNNING.md, step 2). Order matters: the
    # championship trade curve and diagnosis need the 6-player championship agent first.
    "v03": [
        ("harden-championship-6p", ["scripts/05b_refine_meta.py", "--mode", "championship", "6"]),
        ("trade-curve-championship", ["scripts/06_meta_trade_curve.py", "--mode", "championship"]),
        ("championship-basics", ["scripts/07_championship_basics.py"]),
        ("revalidate-standard-2-5p", ["scripts/05b_refine_meta.py", "--mode", "standard", "--revalidate",
                                      "2", "3", "4", "5"]),
        ("meta-vs-simple-championship", ["scripts/09_meta_vs_simple.py", "--mode", "championship"]),
        ("property-trades-meta", ["scripts/10_property_trades.py", "--bots", "meta"]),
        ("dashboard-data", ["scripts/08_dashboard_data.py"]),
        ("figures", ["scripts/make_figures.py"]),
    ],
    # v0.4, run 1: how far a much bigger search can beat the meta agents using only the moves they already have.
    # This is the control arm for the unconventional-strategy search (new moves on), which uses the same
    # protocol, budget and evaluation games. Written to results/v04; v0.3's results stay as they are.
    "exploit": [
        ("prepare", ["scripts/deep_prepare.py"], V04),
        ("exploitability-standard", ["scripts/12_exploitability.py", "--mode", "standard"], V04),
        ("exploitability-championship", ["scripts/12_exploitability.py", "--mode", "championship"], V04),
    ],
    # v0.4, run 2: unconventional strategies. For each table size (4 players first, so a stopped run still has
    # the most-played sizes) and both rule sets: the control arm above, then scripts/13_unconventional.py (the
    # same search with the new moves allowed, a MAP-Elites search, and checks of what they found).
    "v04": [("prepare", ["scripts/deep_prepare.py"], V04)]
    + [step for n in ("4", "3", "5", "2", "6") for mode in ("standard", "championship") for step in (
        (f"{n}p-{mode}-control", ["scripts/12_exploitability.py", "--mode", mode, n], V04),
        (f"{n}p-{mode}-new-moves", ["scripts/13_unconventional.py", "--mode", mode, n], V04))]
    + [("summary", ["scripts/13_unconventional.py", "--summary"], V04)],
    # v0.5: harden the meta agents against the new moves (scripts/14_harden.py), then repeat v0.4's two searches
    # against the new agents. Hardening runs for every table size first (4 players first), so a stopped run still
    # has the new agents; the rechecks follow. Reads v0.4's results from results/v04, writes results/v05.
    "v05": [(f"{n}p-{mode}-harden", ["scripts/14_harden.py", "--mode", mode, n], V05)
            for n in ("4", "3", "5", "2", "6") for mode in ("standard", "championship")]
    + [(f"{n}p-{mode}-recheck", ["scripts/14_harden.py", "--mode", mode, "--recheck", n], V05)
       for n in ("4", "3", "5", "2", "6") for mode in ("standard", "championship")]
    + [("summary", ["scripts/14_harden.py", "--summary"], V05)],
    # On hold: every v0.3 study at 10x the samples. Most of these are measured with the meta agent at the table,
    # so they wait until the unconventional-strategy search has settled which agent that is (and will likely
    # run on the Rust engine, in minutes). Steps already done by "exploit" are skipped.
    "deep": [
        ("prepare", ["scripts/deep_prepare.py"], V04),
        ("tournaments", ["scripts/03_tournament.py"], V04),
        ("championship-basics", ["scripts/07_championship_basics.py"], V04),
        ("validate-standard", ["scripts/05b_refine_meta.py", "--mode", "standard", "--revalidate"], V04),
        ("validate-championship", ["scripts/05b_refine_meta.py", "--mode", "championship", "--revalidate"], V04),
        ("exploitability-standard", ["scripts/12_exploitability.py", "--mode", "standard"], V04),
        ("exploitability-championship", ["scripts/12_exploitability.py", "--mode", "championship"], V04),
        ("meta-vs-simple-standard", ["scripts/09_meta_vs_simple.py", "--mode", "standard"], V04),
        ("meta-vs-simple-championship", ["scripts/09_meta_vs_simple.py", "--mode", "championship"], V04),
        ("vine-street-simple", ["scripts/04_trade_curve.py"], V04),
        ("vine-street-meta-standard", ["scripts/06_meta_trade_curve.py", "--mode", "standard"], V04),
        ("vine-street-meta-championship", ["scripts/06_meta_trade_curve.py", "--mode", "championship"], V04),
        ("property-trades-simple", ["scripts/10_property_trades.py", "--bots", "simple"], V04),
        ("property-trades-meta", ["scripts/10_property_trades.py", "--bots", "meta"], V04),
        ("property-trades-championship", ["scripts/10_property_trades.py", "--bots", "championship"],
         {**V04, "MM_SCALE": "5"}),
        ("dashboard-data", ["scripts/08_dashboard_data.py"], V04),
        ("figures", ["scripts/make_figures.py"], V04),
    ],
    # A two-minute end-to-end check of this runner (sync, steps, stamp, commit, bundle, DONE note).
    "smoke": [
        ("regression-digests", ["tests/golden.py"]),
        ("doctor", ["scripts/doctor.py", "--quick"]),
    ],
}


def git(*args: str, check: bool = True, capture: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, check=False, text=True,
                       stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{(r.stderr or '').strip()}")
    return (r.stdout or "").strip()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dirty_tracked(exclude_results: bool) -> list[str]:
    """Tracked files with real (not line-ending-only) changes."""
    out = git("diff", "--name-only", "--ignore-cr-at-eol", "HEAD")
    files = [f for f in out.splitlines() if f]
    if exclude_results:
        files = [f for f in files if not f.startswith("results/")]
    return files


def require_main() -> None:
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != "main":
        raise SystemExit(f"You're on branch '{branch}'. Run `git switch main` first.")


def is_ancestor(a: str, b: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=ROOT).returncode == 0


def fetch_bundle() -> bool:
    """Fetch Claude's bundle into refs/remotes/claude/main. True if it holds code main doesn't have yet."""
    bundle = SYNC / "claude.bundle"
    if not bundle.exists():
        return False
    git("bundle", "verify", "--quiet", str(bundle))
    git("fetch", "--quiet", str(bundle), "+main:refs/remotes/claude/main")
    return not is_ancestor("refs/remotes/claude/main", "HEAD")


def sync() -> None:
    if not (SYNC / "claude.bundle").exists():
        raise SystemExit("No .sync/claude.bundle yet: nothing to sync.")
    require_main()
    if not fetch_bundle():
        print("Already up to date with Claude's latest code.")
        return
    changed = dirty_tracked(exclude_results=False)
    if changed:
        raise SystemExit("These tracked files have uncommitted changes, so the update was not applied:\n  "
                         + "\n  ".join(changed[:20])
                         + "\nIf a job was interrupted, finish it first (rerun its make command). "
                           "Otherwise commit or stash the changes and run `make sync` again.")
    base = "refs/remotes/claude/main"
    if is_ancestor("HEAD", base):
        git("merge", "--ff-only", "--quiet", base)
        print(f"Updated to {git('log', '-1', '--format=%h %s')}")
        return
    # main has commits Claude hasn't seen yet. If they only add results, replay them on top of the new code.
    local = [f for f in git("diff", "--name-only", f"{base}...HEAD").splitlines() if f]
    if local and all(f.startswith("results/") for f in local):
        r = subprocess.run(["git", "rebase", "--quiet", base], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            subprocess.run(["git", "rebase", "--abort"], cwd=ROOT, capture_output=True)
            raise SystemExit("Your results commits clash with Claude's newer code, so nothing was changed. "
                             "Tell Claude; .sync/from-pc.bundle carries your results.")
        git("bundle", "create", "--quiet", str(SYNC / "from-pc.bundle"), f"{base}..main")
        print(f"Updated to Claude's latest code and replayed your results on top: "
              f"{git('log', '-1', '--format=%h %s')}")
        return
    raise SystemExit("Your main has commits Claude hasn't seen that change more than results/, so it can't "
                     "update automatically. Tell Claude; .sync/from-pc.bundle carries them.")


def load_state(job: str) -> dict | None:
    p = STATE / f"{job}.json"
    return json.loads(p.read_text()) if p.exists() else None


def save_state(job: str, st: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = STATE / f"{job}.json.tmp"
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(STATE / f"{job}.json")


def machine() -> dict:
    mem = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem = round(int(line.split()[1]) / 1024 ** 2, 1)
    except OSError:
        pass
    return {"host": socket.gethostname(), "platform": platform.platform(), "cpu_threads": os.cpu_count(),
            "ram_gb": mem, "python": platform.python_version()}


def run(job: str, force: bool, watch: bool = True) -> None:
    if job not in JOBS:
        raise SystemExit(f"Unknown job '{job}'. Jobs: {', '.join(JOBS)}")
    require_main()
    if load_state(job):  # resuming: finish on the job's own code, even if newer code is waiting
        if fetch_bundle():
            print("Note: newer code from Claude is waiting. Finishing this job on its original code first; "
                  "run `make sync` afterwards.")
    elif (SYNC / "claude.bundle").exists():
        sync()
    changed = dirty_tracked(exclude_results=True)
    if changed:
        raise SystemExit("Uncommitted changes outside results/ (" + ", ".join(changed[:5]) + "). "
                         "Commit or stash them first, so the results record the exact code that made them.")
    head = git("rev-parse", "HEAD")
    st = load_state(job)
    if st and st.get("commit") != head and not force:
        raise SystemExit(f"Job '{job}' was started on commit {st['commit'][:9]} but the code is now {head[:9]}. "
                         f"Rerun with FORCE=1 (make {job} FORCE=1) to restart it on the new code.")
    if not st or st.get("commit") != head:
        st = {"job": job, "commit": head, "started": now(), "steps": {}}
        save_state(job, st)
    try:
        os.nice(10)  # keep the PC responsive: jobs yield to anything interactive
    except OSError:
        pass
    LOGS.mkdir(parents=True, exist_ok=True)
    steps = [(*step, {})[:3] for step in JOBS[job]]
    for i, (name, argv, env) in enumerate(steps, 1):
        if st["steps"].get(name, {}).get("done"):
            print(f"[{i}/{len(steps)}] {name}: already done, skipping")
            continue
        extra = " ".join(f"{k}={v}" for k, v in env.items())
        print(f"[{i}/{len(steps)}] {name}: {extra + ' ' if extra else ''}python {shlex.join(argv)}", flush=True)
        t0 = time.time()
        log = LOGS / f"{job}-{name}.log"
        watch_note(job, st, steps, "running", step=name)
        # MM_WATCH_DIR / MM_STEP let `make watch` follow the step (src/monopoly_meta/watch.py)
        live = {"MM_WATCH_DIR": str(WATCH / job), "MM_STEP": f"{job}/{name}"} if watch else {}
        with log.open("a") as fh:
            fh.write(f"\n=== {now()} {extra} {shlex.join([PY, *argv])}\n")
            fh.flush()
            proc = subprocess.Popen([PY, "-u", *argv], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1, env={**os.environ, **live, **env})
            assert proc.stdout is not None
            for line in proc.stdout:
                sys.stdout.write("    " + line)
                fh.write(line)
            code = proc.wait()
        secs = round(time.time() - t0)
        if code != 0:
            st["steps"][name] = {"done": False, "seconds": secs, "exit_code": code}
            save_state(job, st)
            watch_note(job, st, steps, "failed", step=name)
            raise SystemExit(f"Step '{name}' failed (exit code {code}); the log is .sync/logs/{log.name}. "
                             f"Rerun `make {job}` to resume from this step once it's fixed.")
        st["steps"][name] = {"done": True, "seconds": secs, "finished": now()}
        save_state(job, st)
        print(f"    done in {secs // 60} min {secs % 60} s", flush=True)
    watch_note(job, st, steps, "finished")
    finish(job, st)


def watch_note(job: str, st: dict, steps: list, state: str, step: str | None = None) -> None:
    """Tell the live viewer (`make watch`) which job and step are running. Never fails the job."""
    try:
        WATCH.mkdir(parents=True, exist_ok=True)
        note = {"job": job, "state": state, "step": step, "time": time.time(), "host": socket.gethostname(),
                "pid": os.getpid(), "started": st["started"], "commit": st["commit"][:9],
                "steps": [{"name": s[0], "done": bool(st["steps"].get(s[0], {}).get("done")),
                           "seconds": st["steps"].get(s[0], {}).get("seconds")} for s in steps]}
        tmp = WATCH / ".current.tmp"
        tmp.write_text(json.dumps(note))
        os.replace(tmp, WATCH / "current.json")
    except OSError:
        pass


def finish(job: str, st: dict) -> None:
    stamp = {"job": job, "commit": st["commit"], "started": st["started"], "finished": now(),
             "machine": machine(), "steps": {k: v["seconds"] for k, v in st["steps"].items()},
             "commands": {s[0]: " ".join(f"{k}={v}" for k, v in (s[2] if len(s) > 2 else {}).items())
                          + (" " if len(s) > 2 else "") + "python " + shlex.join(s[1]) for s in JOBS[job]}}
    runs = ROOT / "results" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{job}.json").write_text(json.dumps(stamp, indent=1) + "\n")
    git("add", "--all", "results")
    if git("diff", "--cached", "--name-only"):
        git("commit", "--quiet", "-m", f"results({job}): {stamp['machine']['host']}, "
                                       f"{stamp['machine']['cpu_threads']} threads, code {st['commit'][:9]}")
    base = "refs/remotes/claude/main"
    has_base = subprocess.run(["git", "rev-parse", "--verify", "--quiet", base], cwd=ROOT,
                              stdout=subprocess.DEVNULL).returncode == 0
    rng = f"{base}..main" if has_base and git("rev-list", "--count", f"{base}..main") != "0" else "main"
    git("bundle", "create", str(SYNC / "from-pc.bundle"), rng)
    total = sum(stamp["steps"].values())
    lines = [f"Job {job} finished {stamp['finished']} on {stamp['machine']['host']} "
             f"({stamp['machine']['cpu_threads']} threads, Python {stamp['machine']['python']}).",
             f"Code: {st['commit']}", f"Results commit: {git('rev-parse', 'HEAD')}",
             f"Total time: {total // 3600} h {total % 3600 // 60} min", "", "Steps (seconds):"]
    lines += [f"  {k}: {v}" for k, v in stamp["steps"].items()]
    (SYNC / f"DONE-{job}.txt").write_text("\n".join(lines) + "\n")
    (STATE / f"{job}.json").unlink(missing_ok=True)
    print("\n".join(["", *lines, "", "All done. Tell Claude in the chat; the results are in .sync/ for it to read."]))


def status() -> None:
    for job, steps in JOBS.items():
        st = load_state(job)
        done = (SYNC / f"DONE-{job}.txt").exists()
        if st:
            n = sum(1 for step in steps if st["steps"].get(step[0], {}).get("done"))
            print(f"{job}: running or interrupted, {n}/{len(steps)} steps done (code {st['commit'][:9]})")
        else:
            print(f"{job}: {'finished' if done else 'not started'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync")
    r = sub.add_parser("run")
    r.add_argument("job")
    r.add_argument("--force", action="store_true")
    r.add_argument("--no-watch", action="store_true", help="don't leave games for the live viewer (make watch)")
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "sync":
        sync()
    elif a.cmd == "run":
        run(a.job, a.force, watch=not a.no_watch)
    else:
        status()


if __name__ == "__main__":
    main()
