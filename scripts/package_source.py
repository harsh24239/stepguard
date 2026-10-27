"""Build a local source bundle, excluding credentials, media, sessions, and dependencies."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {"backend", "frontend", "docs", "eval", "scripts"}
ROOT_FILES = {"README.md", "STEPGUARD_COMPLETE_PROMPT.md", ".gitignore", ".env.example", "private_assets/.gitkeep", "sessions/.gitkeep"}
EXCLUDED = {".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache"}
SUFFIXES = {".py", ".ts", ".tsx", ".css", ".html", ".json", ".md", ".txt", ".lock", ".mjs"}
# This is a basic accidental-key check, not a substitute for participant review.
KEY = re.compile(r"AIza[0-9A-Za-z_-]{30,}|\bsk-[0-9A-Za-z_-]{20,}|\bgh[pousr]_[0-9A-Za-z]{20,}")


def source_files():
    files = [ROOT / name for name in ROOT_FILES]
    for name in sorted(DIRECTORIES):
        for directory, children, names in os.walk(ROOT / name, followlinks=False):
            children[:] = sorted(child for child in children if child not in EXCLUDED and not (Path(directory) / child).is_symlink())
            for filename in sorted(names):
                path = Path(directory) / filename
                if path.suffix in SUFFIXES and not filename.startswith(".env"):
                    files.append(path)
    for path in sorted(files):
        if path.is_symlink():
            raise ValueError(f"Refusing source symlink: {path.relative_to(ROOT)}")
        content = path.read_text()
        if KEY.search(content):
            raise ValueError(f"Possible credential in {path.relative_to(ROOT)}; review locally. No credential is printed.")
        if path.name == ".env.example":
            for line in content.splitlines():
                if re.match(r"\s*\w*(?:API_KEY|TOKEN|SECRET)\s*=", line) and line.split("=", 1)[1].strip().strip("\"'"):
                    raise ValueError("Keep credential values blank in .env.example.")
        yield path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "private_assets" / "stepguard-source.zip")
    parser.add_argument("--check", action="store_true", help="Validate selected source without creating a bundle")
    args = parser.parse_args()
    files = list(source_files())
    if args.check:
        print(f"Checked {len(files)} source files. Credentials, private assets, sessions, dependencies, and builds are excluded.")
        return
    output = args.output.resolve()
    if output.suffix != ".zip":
        parser.error("Use a .zip output path.")
    if output.exists():
        parser.error("Output already exists. Choose a new filename or remove the old bundle explicitly.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, Path("stepguard") / path.relative_to(ROOT))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n")
    print(f"Bundled {len(files)} source files: {output}\nSHA256: {digest}")


if __name__ == "__main__":
    main()
