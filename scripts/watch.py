"""Watch your PC's games live: a board in the browser replays real games from the running job, move by
move, beside the job's progress.

    make watch                       opens http://localhost:8765 (Ctrl+C stops it)
    make watch PORT=8800             another port
    make watch HOST=0.0.0.0          if Windows can't reach the page on localhost

While a job runs, every few seconds it saves one of the games it is about to play: the players, the
seed and the rules (src/monopoly_meta/watch.py). This server replays that exact game with the same code
(src/monopoly_meta/replay.py), so the board shows a real game from the run, slowed down for people.
With no job running it plays demo games between the meta agents. It only reads the job's files.

    make play                        play against the meta agents yourself (the same page, ?play)

In play mode one seat is yours (src/monopoly_meta/human.py): the game runs here and waits for your
decisions, which the page asks you for; the other seats are the meta agents.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import socket
import subprocess
import threading
import time
from collections import deque
from dataclasses import fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from monopoly_meta import load_edition
from monopoly_meta.engine import Rules, championship_rules
from monopoly_meta.human import PlaySession
from monopoly_meta.meta import BALANCED, to_spec, tournament_rules
from monopoly_meta.policies import make_bot
from monopoly_meta.replay import RecordingGame, buy_value, win_chances
from monopoly_meta.unconventional import TACTIC_NAMES, tactics_on

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / ".sync" / "watch"
LOGS = ROOT / ".sync" / "logs"
PAGE = ROOT / "watch" / "index.html"
PIECES = ROOT / "watch" / "pieces"  # the players' pieces (scripts/cut_pieces.py)
ARTWORK = ROOT / "watch" / "board"  # the board's artwork (the classic-colour board kit; see its README)
THEME = ROOT / "dashboard" / "theme.css"

GROUP_COLOURS = {  # the dashboard's board colours (dashboard/theme.src.css)
    "brown": "#8a5a3b", "light_blue": "#8cc9e8", "pink": "#c9468f", "orange": "#ec8a2c", "red": "#d53a2c",
    "yellow": "#edcb2c", "green": "#22955a", "dark_blue": "#2c58a8", "stations": "#3b3833", "utilities": "#9a9488",
}


# ---------------------------------------------------------------------- board
def board() -> dict:
    ed = load_edition()
    squares = []
    for i in range(ed.n_squares):
        gi = ed.group_of[i]
        sq = {"i": i, "name": ed.names[i], "type": ed.types[i], "price": ed.price[i], "tax": ed.tax[i]}
        if gi >= 0:
            sq.update(group=ed.group_names[gi], colour=GROUP_COLOURS.get(ed.group_names[gi], "#777"),
                      house_cost=ed.house_cost[gi], mortgage=ed.mortgage_value(i))
            if ed.types[i] == "street":
                sq["rent"] = ed.rent[i]
        squares.append(sq)
    try:
        pieces = json.loads((PIECES / "pieces.json").read_text())
    except (OSError, ValueError):
        pieces = []
    return {"squares": squares, "ownable": ed.ownable, "go_salary": ed.go_salary, "jail": ed.jail_square,
            "jail_fine": ed.jail_fine, "start_cash": ed.start_cash, "pieces": pieces}


# ---------------------------------------------------------------------- games
def rules_label(r: Rules) -> str:
    name = "Championship rules" if r.speed_die else "Official rules"
    extras = []
    if not r.auctions:
        extras.append("no auctions")
    if r.free_parking_jackpot:
        extras.append("Free Parking jackpot")
    if r.card_draw != "deck":
        extras.append("random cards")
    return name + (f" ({', '.join(extras)})" if extras else "")


GAMES: dict[str, dict] = {}  # recent games kept for analysis: id -> lineup, rules, states, decisions
COMPUTE = threading.Lock()  # one estimate at a time, so the viewer never uses more than one thread
ODDS_BUDGET = 0.4   # CPU seconds per win-chance estimate (fewer playouts in long games)
VALUE_BUDGET = 1.0  # CPU seconds per property value
CURRENT = {"gid": None}
QUEUE: deque = deque()  # (game id, decision index) waiting for a property value
WAKE = threading.Condition()


def play(lineup: list, seed: int, rules: Rules) -> tuple[str, dict, int]:
    g = RecordingGame([make_bot(spec) for spec in lineup], seed=seed, rules=rules, keep_states=True)
    log = g.record()
    gid = f"{seed}-{time.time():.3f}"
    GAMES[gid] = {"lineup": lineup, "rules": rules, "states": g.states, "decisions": g.decisions,
                  "odds": {}, "values": {}}
    while len(GAMES) > 4:
        GAMES.pop(next(iter(GAMES)))
    with WAKE:
        CURRENT["gid"] = gid
        QUEUE.clear()  # older games' work is no longer wanted
    return gid, log, len(g.decisions)


def odds(gid: str, turn: int, n: int) -> dict:
    """Win chances after `turn` (0 = before the first turn) of a game this server replayed."""
    entry = GAMES.get(gid)
    if entry is None:
        return {"error": "unknown game"}
    turn = max(0, min(turn, len(entry["states"]) - 1))
    if turn not in entry["odds"]:
        with COMPUTE:
            if turn not in entry["odds"]:
                t0 = time.process_time()
                res = win_chances(entry["lineup"], entry["rules"], entry["states"][turn], n, budget_s=ODDS_BUDGET)
                res["cpu_seconds"] = round(time.process_time() - t0, 3)
                entry["odds"][turn] = res
    return {"turn": turn, **entry["odds"][turn]}


def value(gid: str, k: int, ahead: int = 3) -> dict:
    """The value of the property at buying decision k to the player deciding (computed in the background;
    asking also queues the next few decisions, so they are usually ready by the time the replay gets there)."""
    entry = GAMES.get(gid)
    if entry is None or not 0 <= k < len(entry["decisions"]):
        return {"error": "unknown decision"}
    if k in entry["values"]:
        return {"ready": True, "k": k, **entry["values"][k]}
    with WAKE:
        for j in range(k, min(k + 1 + ahead, len(entry["decisions"]))):
            if j not in entry["values"] and (gid, j) not in QUEUE:
                QUEUE.append((gid, j))
        WAKE.notify()
    return {"ready": False, "k": k}


def value_worker() -> None:
    while True:
        with WAKE:
            while not QUEUE:
                WAKE.wait()
            gid, k = QUEUE.popleft()
            if gid != CURRENT["gid"]:
                continue
        entry = GAMES.get(gid)
        if entry is None or k in entry["values"]:
            continue
        d = entry["decisions"][k]
        with COMPUTE:
            entry["values"][k] = buy_value(entry["lineup"], entry["rules"], d["state"], d["p"], d["sq"],
                                           budget_s=VALUE_BUDGET)


def latest_sample() -> dict | None:
    """The newest game saved by a running (or the last) job."""
    best = None
    if WATCH.exists():
        for f in WATCH.glob("*/sample.json"):
            try:
                rec = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            if best is None or rec.get("time", 0) > best.get("time", 0):
                best = rec
    return best


def player_labels(lineup, seat, context) -> list[dict]:
    out = []
    for i, spec in enumerate(lineup):
        if isinstance(spec, str):
            label, role = f"Simple bot ({spec.replace('_', ' ')})", "bot"
        elif seat is not None and i == seat:
            label, role = context.get("candidate", "Candidate"), "candidate"
        else:
            label, role = context.get("opponents", "Opponent"), "opponent"
        on = tactics_on(spec) if isinstance(spec, dict) else []
        if on:  # the v0.4 moves it is trying, e.g. "Explorer · housing lock, card counting"
            label += " · " + ", ".join(TACTIC_NAMES[k] for k in on)
        out.append({"label": label, "role": role})
    return out


def live_game(rec: dict) -> dict:
    known = {f.name for f in fields(Rules)}
    rules = Rules(**{k: v for k, v in rec["rules"].items() if k in known})
    lineup, seat = rec["lineup"], rec.get("seat")
    ctx = rec.get("context") or {}
    gid, log, decisions = play(lineup, rec["seed"], rules)
    return {"kind": "live", "id": gid, "decisions": decisions, "step": rec.get("step", ""),
            "sampled_at": rec.get("time"), "seed": rec["seed"], "about": ctx.get("about", ""),
            "rules": rules_label(rules), "scoring": rules.stalemate, "n_players": len(lineup),
            "max_rounds": rules.max_turns // len(lineup), "players": player_labels(lineup, seat, ctx), "log": log}


def demo_game() -> dict:
    """A game between meta agents (or simple bots if there are no meta agents yet)."""
    rng = random.Random()
    n = rng.choice([3, 4, 4, 5])
    mode = rng.choice(["standard", "championship"])
    seed = rng.randrange(1 << 30)
    path = ROOT / "results" / "tables" / f"meta_agents_{mode}.json"
    try:
        metas = json.loads(path.read_text())
        genome = {k: v for k, v in metas[str(n)].items() if k != "name"}
        lineup = [to_spec(genome, f"meta{i}") for i in range(n)]
        label = "Meta agent"
    except (OSError, ValueError, KeyError):
        lineup, label = ["balanced"] * n, "Simple bot"
    rules = championship_rules(n) if mode == "championship" else tournament_rules(n)
    gid, log, decisions = play(lineup, seed, rules)
    return {"kind": "demo", "id": gid, "decisions": decisions, "step": "", "sampled_at": time.time(), "seed": seed,
            "about": f"Demo: {n} {label.lower()}s play each other (no job running)", "rules": rules_label(rules),
            "scoring": rules.stalemate, "n_players": n, "max_rounds": rules.max_turns // n,
            "players": [{"label": label, "role": "opponent"}] * n, "log": log}


# ---------------------------------------------------------------------- playing them yourself
# Whose meta agents you can play against: the hardened v0.5 agents once that run has made them, and v0.3's.
OPPONENTS = {"v05": ("v0.5 meta agent", ROOT / "results" / "v05" / "tables"),
             "v03": ("v0.3 meta agent", ROOT / "results" / "tables")}
PLAY: dict = {"session": None, "id": None}


def meta_genome(kind: str, mode: str, n: int) -> dict | None:
    try:
        metas = json.loads((OPPONENTS[kind][1] / f"meta_agents_{mode}.json").read_text())
        return {k: v for k, v in metas[str(n)].items() if k != "name"}
    except (KeyError, OSError, ValueError):
        return None


def play_options() -> dict:
    """Which opponents exist for each rule set and table size."""
    return {mode: {kind: [n for n in range(2, 7) if meta_genome(kind, mode, n)] for kind in OPPONENTS}
            for mode in ("standard", "championship")}


def play_new(body: dict) -> dict:
    mode = body.get("mode") if body.get("mode") in ("standard", "championship") else "standard"
    n = min(6, max(2, int(body.get("players") or 4)))
    kind = body.get("opponents")
    genome = meta_genome(kind, mode, n) if kind in OPPONENTS else None
    if genome is None and kind != "simple":  # the newest agents there are, else the simple bot
        kind = next((k for k in OPPONENTS if meta_genome(k, mode, n)), "simple")
        genome = meta_genome(kind, mode, n) if kind in OPPONENTS else None
    label = OPPONENTS[kind][0] if genome else "Simple bot"
    bot = to_spec(genome, label) if genome else to_spec(dict(BALANCED), label)
    seat = body.get("seat")
    seat = random.randrange(n) if seat in (None, "random") else min(n - 1, max(0, int(seat)))
    seed = random.randrange(1 << 30)
    rules = championship_rules(n) if mode == "championship" else tournament_rules(n)
    lineup = [bot] * n
    if PLAY["session"] is not None:
        PLAY["session"].close()
    session = PlaySession(lineup, seat, rules, seed)
    gid = f"play-{seed}-{time.time():.3f}"
    # the coach (win chances, property values) plays your seat with the same agent in its playouts
    GAMES[gid] = {"lineup": lineup, "rules": rules, "states": session.g.states, "decisions": session.g.decisions,
                  "odds": {}, "values": {}}
    while len(GAMES) > 4:
        GAMES.pop(next(iter(GAMES)))
    with WAKE:
        CURRENT["gid"] = gid
        QUEUE.clear()
    PLAY.update(session=session, id=gid)
    players = [{"label": "You", "role": "you"} if i == seat else {"label": label, "role": "opponent"}
               for i in range(n)]
    return {"kind": "play", "id": gid, "seat": seat, "n_players": n, "mode": mode, "rules": rules_label(rules),
            "scoring": rules.stalemate, "max_rounds": rules.max_turns // n, "seed": seed, "players": players,
            "opponents": kind, "start": session.start_state, "decisions": 0}


def play_poll(gid: str, since: int) -> dict:
    s = PLAY["session"]
    if s is None or PLAY["id"] != gid:
        return {"error": "This game has ended: start a new one."}
    return s.poll(max(0, since), wait=1.0)


def play_answer(body: dict) -> dict:
    s = PLAY["session"]
    if s is None or PLAY["id"] != body.get("id"):
        return {"ok": False, "error": "This game has ended: start a new one."}
    return {"ok": s.answer(int(body.get("qid", -1)), body.get("value"))}


# ---------------------------------------------------------------------- job status
class Progress:
    """Reads a job's progress.log incrementally: games finished, games in flight, recent speed."""

    def __init__(self):
        self.path, self.offset = None, 0
        self.done = 0
        self.inflight = 0
        self.inflight_since = 0.0
        self.recent = []  # (finish time, games, seconds)
        self.step_games = {}
        self.step = ""

    def update(self, path: Path) -> None:
        if path != self.path:
            self.__init__()
            self.path = path
        try:
            with path.open() as f:
                f.seek(self.offset)
                chunk = f.read()
                self.offset = f.tell()
        except OSError:
            return
        for line in chunk.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            t, kind, n = float(parts[0]), parts[1], int(parts[2])
            if kind == "start":
                self.inflight, self.inflight_since = n, t
                self.step = parts[3] if len(parts) > 3 else ""
            elif kind == "done":
                secs = float(parts[3]) if len(parts) > 3 else 0.0
                self.done += n
                self.step_games[self.step] = self.step_games.get(self.step, 0) + n
                self.inflight = 0
                self.recent.append((t, n, secs))
        cutoff = time.time() - 600
        self.recent = [r for r in self.recent if r[0] >= cutoff][-200:]

    def rate(self) -> float:
        secs = sum(r[2] for r in self.recent)
        return sum(r[1] for r in self.recent) / secs if secs > 0 else 0.0


PROGRESS = Progress()


def pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def tail(path: Path, n: int = 6) -> list[str]:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    lines = [x.rstrip() for x in lines if x.strip() and not x.startswith("===")]
    return lines[-n:]


def status() -> dict:
    out = {"host": socket.gethostname(), "now": time.time(), "job": None}
    try:
        cur = json.loads((WATCH / "current.json").read_text())
    except (OSError, ValueError):
        return out
    running = cur.get("state") == "running" and pid_alive(cur.get("pid"))
    PROGRESS.update(WATCH / cur["job"] / "progress.log")
    step = cur.get("step")
    out["job"] = {
        "name": cur["job"], "state": "running" if running else ("stopped" if cur.get("state") == "running"
                                                                else cur.get("state")),
        "step": step, "steps": cur.get("steps", []), "started": cur.get("started"), "commit": cur.get("commit"),
        "host": cur.get("host"), "games": PROGRESS.done, "inflight": PROGRESS.inflight if running else 0,
        "inflight_since": PROGRESS.inflight_since, "rate": PROGRESS.rate(),
        "log": tail(LOGS / f"{cur['job']}-{step}.log") if step else [],
    }
    return out


# ---------------------------------------------------------------------- server
def fonts_css() -> str:
    try:
        css = THEME.read_text()
    except OSError:
        return ""
    return "\n".join(re.findall(r"@font-face\s*{[^}]*}", css))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def send(self, body, ctype="application/json", code=200, cache=False):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype if ctype.startswith("image/") else ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path in ("/", "/index.html"):
                self.send(PAGE.read_bytes(), "text/html")
            elif url.path == "/fonts.css":
                self.send(fonts_css(), "text/css")
            elif url.path.startswith("/pieces/") and re.fullmatch(r"[a-z-]+\.png", url.path[8:]) \
                    and (PIECES / url.path[8:]).exists():
                self.send((PIECES / url.path[8:]).read_bytes(), "image/png", cache=True)
            elif url.path.startswith("/board/") and re.fullmatch(r"[a-z-]+\.svg", url.path[7:]) \
                    and (ARTWORK / url.path[7:]).exists():
                self.send((ARTWORK / url.path[7:]).read_bytes(), "image/svg+xml", cache=True)
            elif url.path == "/api/board":
                self.send(board())
            elif url.path == "/api/status":
                self.send(status())
            elif url.path == "/api/game":
                since = float(parse_qs(url.query).get("since", ["0"])[0] or 0)
                rec = latest_sample()
                fresh = rec is not None and rec.get("time", 0) > since and time.time() - rec["time"] < 3600
                self.send(live_game(rec) if fresh else demo_game())
            elif url.path == "/api/odds":
                q = parse_qs(url.query)
                n = max(8, min(400, int(q.get("n", ["64"])[0])))
                self.send(odds(q.get("id", [""])[0], int(q.get("turn", ["0"])[0]), n))
            elif url.path == "/api/play/options":
                self.send(play_options())
            elif url.path == "/api/play/poll":
                q = parse_qs(url.query)
                self.send(play_poll(q.get("id", [""])[0], int(q.get("since", ["0"])[0] or 0)))
            elif url.path == "/api/value":
                q = parse_qs(url.query)
                self.send(value(q.get("id", [""])[0], int(q.get("k", ["0"])[0])))
            else:
                self.send({"error": "not found"}, code=404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # report, keep serving
            self.send({"error": f"{type(exc).__name__}: {exc}"}, code=500)


class PlayHandler(Handler):
    """The viewer's server, plus the two things play mode sends: a new game and your answers."""

    def do_POST(self):
        url = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(n, 1 << 20)) or b"{}") if n else {}
            if url.path == "/api/play/new":
                self.send(play_new(body if isinstance(body, dict) else {}))
            elif url.path == "/api/play/answer":
                self.send(play_answer(body if isinstance(body, dict) else {}))
            else:
                self.send({"error": "not found"}, code=404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # report, keep serving
            self.send({"error": f"{type(exc).__name__}: {exc}"}, code=500)


def open_browser(url: str) -> None:
    try:
        if "microsoft" in Path("/proc/version").read_text().lower():  # WSL: use the Windows browser
            subprocess.Popen(["explorer.exe", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    except OSError:
        pass
    import webbrowser
    webbrowser.open(url)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--play", action="store_true", help="open the page in play mode: you against the meta agents")
    a = ap.parse_args()
    try:
        os.nice(19)  # lowest priority: a running job always comes first
    except OSError:
        pass
    server = None
    for port in range(a.port, a.port + 20):
        try:
            server = ThreadingHTTPServer((a.host, port), PlayHandler)
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit(f"No free port from {a.port} to {a.port + 19}")
    threading.Thread(target=value_worker, daemon=True).start()
    url = f"http://localhost:{server.server_address[1]}" + ("/?play" if a.play else "")
    print(f"{'Playing' if a.play else 'Watching'} on {url}  (Ctrl+C to stop). If no browser window opens, paste "
          "that address into one.",
          flush=True)
    if not a.no_browser:
        open_browser(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
