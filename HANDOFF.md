# Monopoly Meta: handoff prompt for a fresh chat (v3, on my own PC)

Paste everything below the line into a new chat on my PC, with this repo unzipped in the working folder.

---

You're picking up **Monopoly Meta**, a portfolio project I (Oliver, MSc Applied Data Science and Statistics, Exeter) am building for data science, data engineering, AI and strategy consulting roles. It's been built in a cloud sandbox over several sessions; the code and every result so far are in this folder. Read `HANDOFF.md`, `README.md`, `RULES.md` and `ROADMAP.md` first, then run the test suite.

## The goal: "find the META" in classic UK Monopoly, 2–6 players

The questions the project must answer, for any game state, under official rules and official championship rules:
1. Which properties and sets are best, in a fresh game and mid-game.
2. What any trade is worth to each player right now: the seller's win-chance change and net-worth change at every price, the deal zone, and who to sell to.
3. What to bid at auction for any property in any state, versus a fresh game.
4. When and where to build, mortgage or hold cash.
5. "The true value of a property in this moment", split into rent, set completion, blocking and liquidity.
6. What strong play looks like at each table size, tested against **meta agents found by self-play**, not just simple bots.

Deliverables: an interactive web app/dashboard, a consulting-style deck, notebooks and a written report. I want this as thorough and in-depth as possible; new infrastructure is fine.

## My hardware

Ryzen 7 9800X3D (8 cores / 16 threads, 96 MB L3) and an RTX 4070 Ti (12 GB), on Windows. Plan to use WSL2 (Ubuntu 24.04), `rustup`, `uv`, and PyTorch's CUDA build. The CPU runs simulation; the GPU trains networks. The rules engine itself won't benefit from the GPU (branching logic).

## What exists (v0.3, Python, 98 tests)

- `src/monopoly_meta/`: rules engine (`engine.py`: classic UK 1972 set, fixed-order card decks, auctions as second price + £1, even building, 32 houses / 12 hotels, mortgages with 10% interest, bankruptcy, restartable `GameState`, per-player dice streams for common random numbers, frozen squares, trading API, **championship mode** with the Speed Die via `championship_rules(n)`); `markov.py` (exact 123-state chain, validated against 10M turns); `roi.py`; `policies.py` (`HeuristicBot`, ~23 parameters, presets); `tournament.py`; `rollout.py` (paired trade price curves, `deal_summary`); `meta.py` (evolutionary self-play, best-response hardening, paired bootstrap ratios).
- `scripts/01`–`10`: Markov, ROI, tournaments, Vine Street trade curves, meta agents (`05`), hardening + paired validation (`05b`), meta trade curves (`06`), championship basics (`07`), dashboard export (`08`), **meta vs simple diagnosis** (`09`), **every-property trade curves** (`10`, uses `scenarios.set_completion`). `make_figures.py`. `meta_common.py` holds modes, ablations and aggregation.
- `results/tables/` (CSVs and checkpoints: `meta_standard/`, `meta_championship/`, `property_trades/simple/`), `results/dashboard/` (dashboard CSVs), `results/figures/`.
- `dashboard/index.html`: the page of a Claude Dashboard artifact (https://claude.ai/artifact/15s13gsGe5boN199AhpFFz). It reads datasets uploaded as CSV assets; `dashboard/build_store_docs.py` builds its store documents; `scripts/dashboard_preview.js` renders it locally with a mock runtime (Playwright) at phone and desktop widths.
- The v2 plan doc: https://claude.ai/artifact/CQge9jTFu6FNG9Tk8QH3rf (phases A–G below).

## Key decisions and findings so far

- **Scoring of stalled games matters.** Self-play games stop at 150 rounds. Richest-wins taught stalling (77% of 5p games stalled); shared draws taught a trade embargo; **a stalled game counts as a loss for everyone** (official-rules meta) fixed it. Championship mode uses finishing points (28; 25/14; 22/12/6; 19/10/5/3; 5–6 survivors extrapolated).
- Trafalgar Square is the most-landed property (3.48 per 100 turns). Orange pays back fastest; the third house is the best buy except for brown.
- Pounds undervalue set completion: the buyer's true maximum is 24–41% above the net-worth maximum.
- Every-property deal zones (simple bots, 4p): orange £570–600 → ~£1,175; light blue ~£510 → ~£925; brown has no deal (seller needs ~£485, buyer gains nothing above ~£85); utilities worth ~£70–100. At 2 players every trade is zero-sum. At 6 players the seller rarely wins either way, so its break-even is unreliable.
- **Why the 4p official meta agent loses to simple bots (0.88×):** it offers 2.56× face value for a set piece, tuned to meta opponents. Copying the simple bot's 2× offer makes it level (0.97×); at 5–6p the same change lifts it to 1.33–1.36×. Non-transitivity is a headline finding.
- Self-play cycles at 6p (official) and 3p (championship); hardening keeps the least-exploitable agent.

## Unfinished v0.3 runs (finish these first; they're fast on 16 threads)

1. `python scripts/05b_refine_meta.py --mode championship 6` (2–5 players are hardened and validated; 6 players starts hardening from its first-pass agent).
2. `python scripts/06_meta_trade_curve.py --mode championship` and `python scripts/07_championship_basics.py`.
3. `python scripts/05b_refine_meta.py --mode standard --revalidate` (2–5p validation is still the old unpaired version).
4. `python scripts/09_meta_vs_simple.py --mode championship` and `python scripts/10_property_trades.py --bots meta`.
5. `python scripts/08_dashboard_data.py`, `python scripts/make_figures.py`, then rewrite README/RULES/ROADMAP with the final numbers (README still describes the old draw-scoring meta) and tag v0.3.

Gotchas: never `pkill -f`/`pgrep -f` a pattern that appears in your own command line (it kills your shell; use `pgrep -f "05b_refine_met[a]"`); the engine's regression hash must stay unchanged by refactors; keep evaluation paired (common random numbers); `[hidden]` needs `display:none !important` in the dashboard CSS.

## Your first job: write plan v3 for running everything on this PC, then execute it

Start from the v2 phases and adapt them to local execution (you can run commands directly here, so the "who runs what" split disappears):

- **A. Fast engine:** Rust crate `monopoly-core` with PyO3 bindings and Rayon; both rule sets and the bots in Rust; Python engine switched to the same SplitMix64 generator and kept as the reference. Gate: identical per-turn state logs on 100,000 games, every v0 table reproduced, ≥100× per-core speed. Also a WebAssembly build for the web app.
- **B. Every analysis at scale:** 100,000+ games per cell; every property × 2–6 players × early/mid/late positions × opponent types; auctions, building, jail, cards, more rule sets.
- **C. Position data:** 50–200M positions (Parquet + DuckDB), shocks for coverage, game-level splits, a frozen valuation benchmark from rollouts.
- **D. Value models:** LightGBM + SHAP baseline; a permutation-equivariant transformer value net on the 4070 Ti; calibration; median £ error target under £25 on the benchmark; ONNX export.
- **E. Instant valuations:** price of cash, trades and counter-offers, auction limits, build decisions, property value decomposition, with rollout fallback.
- **F. Stronger agents:** value-greedy, search, negotiating trader, expert iteration, a PPO baseline, and a league with a Nash mixture (PSRO).
- **G. Showcase:** static web app (WASM engine + ONNX model in the browser), dashboard updates, report, notebooks, the "Monopoly as capital allocation" deck, README and CV bullets.

Engineering: one repo (`engine/`, `python/`, `pipelines/`, `web/`, `notebooks/`, `docs/`), `uv`/`ruff`/`mypy`/`pytest`, `cargo test`/`clippy`/`proptest`, GitHub Actions, configs + seeds + commit stamped on every result, MLflow for training, checkpointed resumable jobs.

Before writing code, show me plan v3 and ask me the open decisions: Rust vs Numba, public or private GitHub repo, and anything about my setup you need. Then set up the environment with a `make doctor` check, finish the v0.3 runs, and start Phase A.
