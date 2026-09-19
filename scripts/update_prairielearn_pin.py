#!/usr/bin/env python3
"""Update or verify the vendored PrairieLearn pl-symbolic-input snapshot."""

from __future__ import annotations

import argparse
import filecmp
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ELEMENT = ROOT / "elements" / "pl-equation-input"
MANIFEST = ELEMENT / "prairielearn-source.json"
VENDOR = ELEMENT / "vendor" / "prairielearn" / "pl-symbolic-input"
PYPROJECT = ROOT / "pyproject.toml"
UV_LOCK = ROOT / "uv.lock"
DEFAULT_REPOSITORY = "https://github.com/PrairieLearn/PrairieLearn.git"
DEFAULT_SOURCE_PATH = Path("apps/prairielearn/elements/pl-symbolic-input")
DEFAULT_UPDATE_REF = "master"


def run(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return completed.stdout.strip()


def load_manifest() -> dict[str, str]:
    return json.loads(MANIFEST.read_text())


def clone_source(repository: str, ref: str, destination: Path) -> tuple[Path, str]:
    run(
        "git",
        "clone",
        "--filter=blob:none",
        "--sparse",
        "--no-checkout",
        "--quiet",
        repository,
        str(destination),
    )
    run("git", "sparse-checkout", "set", str(DEFAULT_SOURCE_PATH), cwd=destination)
    run("git", "fetch", "--depth=1", "origin", ref, cwd=destination)
    run("git", "checkout", "--detach", "--quiet", "FETCH_HEAD", cwd=destination)
    commit = run("git", "rev-parse", "HEAD", cwd=destination)
    return destination / DEFAULT_SOURCE_PATH, commit


def build_snapshot(checkout: Path, source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)
    shutil.copy2(checkout / "LICENSE", destination / "UPSTREAM_LICENSE")


def directories_equal(left: Path, right: Path) -> bool:
    if not left.is_dir() or not right.is_dir():
        return False

    def source_files(root: Path) -> set[Path]:
        return {
            path.relative_to(root)
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        }

    left_files = source_files(left)
    right_files = source_files(right)
    return left_files == right_files and all(
        filecmp.cmp(left / path, right / path, shallow=False) for path in left_files
    )


def pinned_pyproject_commit() -> str | None:
    match = re.search(
        r'\[tool\.uv\.sources\.prairielearn\][\s\S]*?^rev = "([0-9a-f]{40})"(?:\s+#.*)?$',
        PYPROJECT.read_text(),
        re.MULTILINE,
    )
    return match.group(1) if match else None


def locked_commit() -> str | None:
    match = re.search(
        r'name = "prairielearn"\nversion = .*?\nsource = \{ git = ".*?#([0-9a-f]{40})" \}',
        UV_LOCK.read_text(),
    )
    return match.group(1) if match else None


def replace_pyproject_commit(commit: str) -> None:
    text = PYPROJECT.read_text()
    updated, count = re.subn(
        r'(\[tool\.uv\.sources\.prairielearn\][\s\S]*?^rev = ")[0-9a-f]{40}("(?:\s+#.*)?$)',
        rf"\g<1>{commit}\g<2>",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise RuntimeError(
            "Could not locate the PrairieLearn source revision in pyproject.toml"
        )
    PYPROJECT.write_text(updated)


def verify(ref: str | None = None) -> None:
    manifest = load_manifest()
    commit = manifest["commit"]
    if ref is not None and ref != commit:
        raise RuntimeError(f"Manifest pins {commit}, not requested ref {ref}.")
    if pinned_pyproject_commit() != commit:
        raise RuntimeError(
            "pyproject.toml PrairieLearn revision does not match provenance."
        )
    if locked_commit() != commit:
        raise RuntimeError("uv.lock PrairieLearn revision does not match provenance.")
    with tempfile.TemporaryDirectory(prefix="prairielearn-pin-check-") as temp:
        checkout = Path(temp) / "PrairieLearn"
        source, resolved = clone_source(manifest["repository"], commit, checkout)
        if resolved != commit:
            raise RuntimeError(f"Pinned ref resolved to unexpected commit {resolved}.")
        expected = Path(temp) / "snapshot"
        build_snapshot(checkout, source, expected)
        if not directories_equal(expected, VENDOR):
            raise RuntimeError(
                "Vendored pl-symbolic-input differs from its pinned upstream snapshot."
            )


def update(ref: str) -> None:
    manifest = load_manifest()
    with tempfile.TemporaryDirectory(prefix="prairielearn-pin-update-") as temp:
        temp_path = Path(temp)
        checkout = temp_path / "PrairieLearn"
        source, commit = clone_source(manifest["repository"], ref, checkout)
        snapshot = temp_path / "pl-symbolic-input"
        build_snapshot(checkout, source, snapshot)

        staged = VENDOR.with_name(f"{VENDOR.name}.new")
        backup = VENDOR.with_name(f"{VENDOR.name}.old")
        shutil.rmtree(staged, ignore_errors=True)
        shutil.copytree(snapshot, staged)
        shutil.rmtree(backup, ignore_errors=True)
        VENDOR.rename(backup)
        try:
            staged.rename(VENDOR)
        except BaseException:
            backup.rename(VENDOR)
            raise
        shutil.rmtree(backup)

        manifest["commit"] = commit
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
        replace_pyproject_commit(commit)
        run("uv", "lock", "--upgrade-package", "prairielearn", cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="Upstream branch, tag, or commit to vendor.")
    parser.add_argument(
        "--check", action="store_true", help="Verify the current pin without writing."
    )
    args = parser.parse_args()
    if args.check:
        verify(args.ref)
    else:
        update(args.ref or DEFAULT_UPDATE_REF)


if __name__ == "__main__":
    main()
