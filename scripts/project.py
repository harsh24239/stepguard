"""Dependency setup, offline verification, and a single-server local release.

Bootstrap: python3 scripts/project.py setup
Verify:   python3 scripts/project.py check
Run:      python3 scripts/project.py run --build
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(command, directory=ROOT, environment=None):
    subprocess.run([str(value) for value in command], cwd=directory, env=environment, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "check", "run"])
    parser.add_argument("--build", action="store_true", help="Build the frontend before starting the local release")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required.")
    node = shutil.which("node")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not node or not npm:
        parser.error("Install Node.js 22.12 or newer, including npm.")
    version = subprocess.check_output([node, "--version"], text=True).strip().lstrip("v").split(".")
    if tuple(map(int, version[:2])) < (22, 12):
        parser.error("Node.js 22.12 or newer is required.")
    if args.command == "setup":
        if not PYTHON.is_file():
            run([sys.executable, "-m", "venv", ROOT / ".venv"])
        if not (ROOT / ".env").exists():
            shutil.copyfile(ROOT / ".env.example", ROOT / ".env")
            (ROOT / ".env").chmod(0o600)
        run([PYTHON, "-m", "pip", "install", "-r", "backend/requirements.lock"])
        run([npm, "ci"], ROOT / "frontend")
        print("Setup complete. Existing .env values were preserved.", flush=True)
        return
    if not PYTHON.is_file() or not (ROOT / "frontend/node_modules").is_dir():
        parser.error("Run python3 scripts/project.py setup first.")
    if args.command == "check":
        environment = {**os.environ, "MOCK_MODE": "true", "MODEL_PROVIDER": "meta", "MODEL_MAX_RETRIES": "0", "DETECTION_CACHE_SECONDS": "0"}
        run([PYTHON, "-m", "pip", "check"], environment=environment)
        run([PYTHON, "-m", "unittest", "discover", "-s", "backend/tests"], environment=environment)
        run([npm, "test"], ROOT / "frontend", environment)
        run([npm, "run", "build"], ROOT / "frontend", environment)
        run([npm, "run", "check:preview"], ROOT / "frontend", environment)
        run([PYTHON, "-m", "scripts.check_release"], environment=environment)
        run([PYTHON, "-m", "scripts.package_source", "--check"], environment=environment)
        print("All offline release checks passed. Live models/devices are not verified by these checks.", flush=True)
        return
    if args.build:
        run([npm, "run", "build"], ROOT / "frontend")
    run([PYTHON, "-m", "scripts.serve", "--port", args.port])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from None
