"""Put the final meta agents into a results folder prepared for the deep run (after scripts/deep_prepare.py).

    MM_RESULTS=results/final python scripts/final_agents.py

The final agents are the ones v0.5 kept (results/v05/tables/meta_agents_<mode>.json): the hardened agent where
it was less exploitable than v0.3's, v0.3's elsewhere. This writes them where every study reads them:
  meta_agents_<mode>.json      the agents the studies play
  meta_<mode>/<n>p.json        the agent and its strongest known challenger, for 05b's revalidation
The strongest known challenger is the strongest exploit any search found against that agent: v0.5's recheck for
a hardened agent, v0.4's searches for a v0.3 agent. v0.5 also measured v0.4's exploits against both agents; one of
those replaces the searches' challenger only when it is clearly stronger (its whole 95% interval above the
challenger's ratio), so a difference within the noise doesn't swap one challenger for another. Safe to run again.
"""
import importlib
import json
import os

import pandas as pd

from meta_common import MODES, ROOT, TAB, ckpt_dir

V04 = ROOT / os.environ.get("MM_V04", "results/v04/tables")
V05 = ROOT / os.environ.get("MM_V05", "results/v05/tables")


def strongest(candidates: list[tuple[float, dict, str]]) -> tuple[float, dict, str]:
    return max(candidates, key=lambda c: c[0])


def searched_v05(rec: dict) -> list[tuple[float, dict, str]]:
    rc = rec["recheck"]
    best = rc["finalists"][0]
    return [(rc["tactics_arm"]["ratio"], rc["tactics_arm"]["challenger"], "v0.5 recheck: challenger search"),
            (best["ratio"], best["genome"], "v0.5 recheck: MAP-Elites")]


def searched_v03(mode: str, n: int) -> list[tuple[float, dict, str]]:
    d = json.loads((V04 / "unconventional" / f"{mode}_{n}p.json").read_text())
    best = max(d["finalists"], key=lambda r: r["ratio"])
    arm = d["tactics_arm"]
    ctrl = pd.read_csv(V04 / f"exploitability_{mode}.csv")
    ctrl = ctrl[ctrl.n_players == n].iloc[-1]
    return [(best["ratio"], best["genome"], "v0.4: MAP-Elites"),
            (arm["tactics_vs_meta"], json.loads(arm["challenger"]), "v0.4: challenger search, new moves"),
            (ctrl["challenger_vs_meta"], json.loads(ctrl["challenger"]), "v0.4: challenger search")]


def known(rows: list[dict], exploits: dict) -> list[tuple[float, dict, str, float]]:
    """v0.4's exploits as v0.5's checks measured them against this agent: (ratio, genome, source, 95% low)."""
    return [(r["ratio"], exploits[r["name"]], f"v0.5 checks: {r['name']}", r["ci_low"])
            for r in rows if r["name"] in exploits]


def pick(searched: list[tuple[float, dict, str]], measured: list[tuple[float, dict, str, float]]):
    """The searches' strongest challenger, unless an exploit measured against the agent is clearly stronger."""
    best = strongest(searched)
    clear = [m[:3] for m in measured if m[3] > best[0]]
    return strongest(clear) if clear else best


def main() -> None:
    v04_inputs = importlib.import_module("14_harden").v04_inputs  # names and genomes of v0.4's exploits
    for mode in MODES:
        kept = json.loads((V05 / f"meta_agents_{mode}.json").read_text())
        agents = {}
        for n, genome in sorted(kept.items(), key=lambda kv: int(kv[0])):
            rec = json.loads((V05 / "hardened" / f"{mode}_{n}p.json").read_text())
            version = (rec.get("chosen") or {}).get("agent")
            if version is None:
                raise SystemExit(f"results/v05 has no choice for {mode} {n}p yet: run scripts/14_harden.py --summary")
            exploits = v04_inputs(mode, int(n))["exploits"]
            if version == "v0.5":
                ratio, challenger, source = pick(searched_v05(rec), known(rec["known_after"], exploits))
            else:
                ratio, challenger, source = pick(searched_v03(mode, int(n)), known(rec["known_before"], exploits))
            path = ckpt_dir(mode) / f"{n}p.json"
            ck = json.loads(path.read_text()) if path.exists() else {"n_players": int(n), "mode": mode}
            changed = ck.get("challenger") not in (None, challenger)
            ck.update(meta=genome, challenger=challenger, refined=True, final={
                "version": version, "challenger_source": source, "challenger_ratio": ratio})
            path.write_text(json.dumps(ck, indent=2))
            agents[n] = genome
            print(f"{mode} {n}p: the {version} agent; strongest known challenger {ratio:.3f}x ({source})"
                  + ("; a different challenger from before: revalidate this size" if changed else ""))
        (TAB / f"meta_agents_{mode}.json").write_text(json.dumps(agents, indent=2))


if __name__ == "__main__":
    main()
