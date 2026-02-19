#!/usr/bin/env python3
"""
Walk the current directory; when a kustomize file is found in a directory,
run `kustomize build` in that directory via subprocess.
"""

import os
import subprocess
import sys

# Standard kustomize file names
KUSTOMIZE_FILES = ("kustomization.yaml", "kustomize.yaml", "Kustomization")


def has_kustomize_file(dirpath: str) -> bool:
    """Return True if dirpath contains a kustomize file."""
    try:
        entries = os.listdir(dirpath)
    except OSError:
        return False
    return any(name in entries for name in KUSTOMIZE_FILES)


def main() -> None:
    start_dir = os.getcwd()
    found_any = False

    for dirpath, dirnames, _filenames in os.walk(start_dir, topdown=True):
        # Skip hidden dirs (e.g. .git) to avoid unnecessary work
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if has_kustomize_file(dirpath):
            found_any = True
            rel = os.path.relpath(dirpath, start_dir)
            print(f"\n--- kustomize build: {rel or '.'} ---")
            try:
                result = subprocess.run(
                    ["kustomize", "build", "."],
                    cwd=dirpath,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print(result.stdout)
                else:
                    print(result.stderr, file=sys.stderr)
                    sys.exit(result.returncode)
            except FileNotFoundError:
                print("Error: 'kustomize' not found in PATH", file=sys.stderr)
                sys.exit(1)

    if not found_any:
        print("No kustomize directories found.")


if __name__ == "__main__":
    main()
