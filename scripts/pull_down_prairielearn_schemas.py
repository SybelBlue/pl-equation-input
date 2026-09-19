#!/usr/bin/env python3
"""Update the local PrairieLearn schemas from the upstream repository."""

from __future__ import annotations

import argparse
import filecmp
import shutil
import subprocess
import tempfile
from pathlib import Path

UPSTREAM = "https://github.com/PrairieLearn/PrairieLearn.git"
SCHEMA_PATH = Path("apps/prairielearn/src/schemas/schemas")
DESTINATION = Path(__file__).resolve().parents[1] / ".prairielearn" / "schemas"


def directories_equal(left: Path, right: Path) -> bool:
    if not right.is_dir():
        return False
    left_files = {path.relative_to(left) for path in left.rglob("*") if path.is_file()}
    right_files = {
        path.relative_to(right) for path in right.rglob("*") if path.is_file()
    }
    return left_files == right_files and all(
        filecmp.cmp(left / path, right / path, shallow=False) for path in left_files
    )


def update_schemas(ref: str | None, write: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="prairielearn-schemas-") as temp_dir:
        checkout = Path(temp_dir) / "PrairieLearn"
        command = [
            "git",
            "clone",
            "--depth=1",
            "--filter=blob:none",
            "--sparse",
            "--quiet",
        ]
        if ref:
            command.extend(("--branch", ref))
        command.extend((UPSTREAM, str(checkout)))
        subprocess.run(command, check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(checkout),
                "sparse-checkout",
                "set",
                str(SCHEMA_PATH),
            ],
            check=True,
        )

        source = checkout / SCHEMA_PATH
        if directories_equal(source, DESTINATION):
            return
        if not write:
            raise RuntimeError(
                "PrairieLearn schemas are out of date; rerun with --write to update them"
            )

        staged = DESTINATION.with_name(f"{DESTINATION.name}.new")
        backup = DESTINATION.with_name(f"{DESTINATION.name}.old")
        shutil.rmtree(staged, ignore_errors=True)
        shutil.copytree(source, staged)
        shutil.rmtree(backup, ignore_errors=True)
        if DESTINATION.exists():
            DESTINATION.rename(backup)
        try:
            staged.rename(DESTINATION)
        except BaseException:
            if backup.exists():
                backup.rename(DESTINATION)
            raise
        shutil.rmtree(backup, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update .prairielearn/schemas from PrairieLearn/PrairieLearn."
    )
    parser.add_argument(
        "--ref",
        help="Upstream branch or tag (defaults to the repository's default branch).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write upstream changes instead of only checking for them.",
    )
    args = parser.parse_args()
    update_schemas(args.ref, args.write)


if __name__ == "__main__":
    main()
