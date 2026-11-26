"""Start the dashboard with the documented command, wait until it is healthy, then stop it.

Usage (from the repository root)::

    python dashboard/check_launch.py --root ARTIFACT_ROOT [--port 8599] [--timeout 90]

Exit code 0 when the server answered its health check and served the app page, 1 otherwise.
Used by CI and ``make dashboard-check``; it reads the artifact root and writes nothing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent / "app.py"


def command(root: str, port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP),
        "--server.headless",
        "true",
        "--server.address",
        "localhost",
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
        "--",
        "--root",
        root,
    ]


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:  # localhost only
        return str(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True)
    parser.add_argument("--port", type=int, default=8599)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args(argv)
    proc = subprocess.Popen(  # fixed command, no shell
        command(args.root, args.port),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://localhost:{args.port}"
    ok = False
    try:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline and proc.poll() is None:
            try:
                ok = _get(f"{base}/_stcore/health").strip() == "ok" and "<title>" in _get(base)
            except OSError:
                ok = False
            if ok:
                break
            time.sleep(1)
    finally:
        proc.terminate()
        try:
            output, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate()
    print(f"dashboard at {base}: {'healthy' if ok else 'NOT healthy'}")
    if not ok:
        print(output[-2000:])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
