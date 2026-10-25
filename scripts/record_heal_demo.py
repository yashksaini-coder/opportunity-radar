"""Record docs/img/heal-demo.gif: the real pipeline healing a broken source.

    uv run python scripts/record_heal_demo.py          # needs `agg` on PATH

HONESTY: the Bright Data CLI is STUBBED. `subprocess.run` inside
radar.brightdata is replaced so `brightdata scraper run` returns zero rows
the first time, `brightdata scraper heal` returns "ok", and the second run
returns raw_output/mlh_run.json (output captured from a real run). The
CLI never executes and nothing touches the network. Everything else is the
real code path: radar.pipeline.main → process_source → validator → healer →
Store (temp sqlite) → Notifier (no token, so it logs instead of sending).

The GIF is built from the pipeline's own log lines, timestamped as they
happen, written as an asciicast v2 file and rendered with agg.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from radar import brightdata, pipeline  # noqa: E402

SOURCE = "mlh-hackathons"
CMD = f"python -m radar.pipeline --source {SOURCE}"  # the stub's empty first run is the "site break"
COLS, ROWS = 100, 24
OUT = ROOT / "docs" / "img" / "heal-demo.gif"
REAL_RUN_OUTPUT = (ROOT / "raw_output" / "mlh_run.json").read_text()

# stub CLI: (verb -> (seconds to pretend it took, stdout)); the first `run`
# is the broken one and is popped off after use.
STUB = {"run": [(1.2, "[]"), (1.0, REAL_RUN_OUTPUT)], "heal": [(2.5, "ok")]}

RED, GREEN, BLUE, DIM, BOLD, RESET = "\x1b[31m", "\x1b[32m", "\x1b[34m", "\x1b[2m", "\x1b[1m", "\x1b[0m"


def stub_cli(command, **_):
    """Stand-in for subprocess.run: answers like the CLI would, after a pause."""
    verb = command[command.index("scraper") + 1]
    delay, stdout = STUB[verb].pop(0) if len(STUB[verb]) > 1 else STUB[verb][0]
    time.sleep(delay)  # so the GIF breathes between phases
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


class Recorder(logging.Handler):
    """Collects (elapsed, coloured text) for every pipeline log line."""

    def __init__(self):
        super().__init__()
        self.t0 = time.monotonic()
        self.lines: list[tuple[float, str]] = []
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))

    def emit(self, record):
        text = self.format(record)
        head, *rest = text.split("\n")
        if len(rest) > 3:  # the "N new opportunities" alert lists 8 items (title + url each); keep the first
            text = "\n".join([head, *rest[:2], f"  … {len(rest) - 2} more lines"])
        colour = ""
        if record.levelno >= logging.WARNING and "Healing" in record.getMessage():
            colour = RED + BOLD
        elif record.getMessage().startswith("CLI:"):
            colour = BLUE
        elif record.name == "radar.pipeline" and ": healed (" in record.getMessage():
            colour = GREEN + BOLD
        wrapped = "\r\n".join(
            textwrap.fill(line, COLS, subsequent_indent="    ", break_on_hyphens=False)
            for line in text.split("\n")
        ).replace("\n", "\r\n")
        self.lines.append((time.monotonic() - self.t0, f"{colour}{wrapped}{RESET}\r\n"))


def run_pipeline(tmp: pathlib.Path) -> Recorder:
    os.environ.update(TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="",
                      RADAR_DB_PATH=str(tmp / "radar.db"))
    rec = Recorder()
    logging.basicConfig(level=logging.INFO, handlers=[rec])  # main()'s basicConfig is then a no-op
    brightdata.subprocess = SimpleNamespace(run=stub_cli, TimeoutExpired=subprocess.TimeoutExpired)
    brightdata._cli_base = lambda: ["brightdata"]  # log lines as with a global CLI install, not npx
    code = pipeline.main(["--source", SOURCE])
    if code != 0:
        raise SystemExit("the heal did not succeed; not overwriting the gif")
    return rec


def write_cast(rec: Recorder, path: pathlib.Path) -> None:
    events = [[0.0, "o", f"{DIM}# recorded against a stubbed Bright Data CLI; the pipeline code is real{RESET}\r\n"]]
    t = 0.6
    events.append([t, "o", f"{BLUE}{BOLD}$ {RESET}"])
    for ch in CMD:  # type the command
        t += 0.03
        events.append([t, "o", f"{BLUE}{BOLD}{ch}{RESET}"])
    t += 0.4
    events.append([t, "o", "\r\n"])
    events.extend([round(t + at, 3), "o", text] for at, text in rec.lines)
    used = 2 + sum(text.count("\r\n") for _, text in rec.lines)
    print(f"{used} rows used of {ROWS}, {events[-1][0]:.1f}s of pipeline + typing")
    if used > ROWS:
        raise SystemExit("output would scroll; shorten something")
    header = {"version": 2, "width": COLS, "height": ROWS, "env": {"TERM": "xterm-256color"}}
    with path.open("w") as fh:
        fh.write(json.dumps(header) + "\n")
        fh.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in events)


def main() -> None:
    if not shutil.which("agg"):
        raise SystemExit("agg not found on PATH (https://github.com/asciinema/agg)")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        rec = run_pipeline(tmp)
        cast = tmp / "heal-demo.cast"
        write_cast(rec, cast)
        render(cast)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")


def render(cast: pathlib.Path) -> None:
    subprocess.run([
        "agg", "--text-font-family", "JetBrainsMono Nerd Font", "--font-size", "16",
        # dashboard palette: bg, fg, then black red green yellow blue magenta cyan white
        "--theme", "fcfcfb,0c0e11,0c0e11,d03b3b,1baf7a,c28f12,2a78d6,8a4fd6,1a9bb0,e6e6e3",
        "--idle-time-limit", "3", "--fps-cap", "15", "--last-frame-duration", "3",
        str(cast), str(OUT),
    ], check=True)


if __name__ == "__main__":
    main()
