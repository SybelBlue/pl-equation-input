from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "update_prairielearn_pin.py"
SPEC = importlib.util.spec_from_file_location("update_prairielearn_pin", SCRIPT)
assert SPEC and SPEC.loader
pin = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pin
SPEC.loader.exec_module(pin)


def test_directories_equal_detects_content_and_file_set_drift(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "same.txt").write_text("same")
    (right / "same.txt").write_text("same")
    assert pin.directories_equal(left, right)

    (right / "same.txt").write_text("different")
    assert not pin.directories_equal(left, right)
    (right / "same.txt").write_text("same")
    (right / "extra.txt").write_text("extra")
    assert not pin.directories_equal(left, right)


def test_build_snapshot_copies_complete_element_and_license(tmp_path):
    checkout = tmp_path / "checkout"
    source = checkout / pin.DEFAULT_SOURCE_PATH
    source.mkdir(parents=True)
    (source / "pl-symbolic-input.py").write_text("controller")
    (checkout / "LICENSE").write_text("license")
    destination = tmp_path / "snapshot"

    pin.build_snapshot(checkout, source, destination)

    assert (destination / "pl-symbolic-input.py").read_text() == "controller"
    assert (destination / "UPSTREAM_LICENSE").read_text() == "license"


def test_replace_pyproject_commit_updates_only_declared_revision(tmp_path, monkeypatch):
    old = "1" * 40
    new = "2" * 40
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.uv.sources.prairielearn]\n"
        'git = "https://example.invalid/PrairieLearn.git"\n'
        f'rev = "{old}" # keep this comment\n'
        'subdirectory = "apps/prairielearn/python"\n'
    )
    monkeypatch.setattr(pin, "PYPROJECT", pyproject)

    pin.replace_pyproject_commit(new)

    assert f'rev = "{new}"' in pyproject.read_text()
    assert "# keep this comment" in pyproject.read_text()
    assert old not in pyproject.read_text()


def test_clone_source_propagates_invalid_ref_failure(tmp_path, monkeypatch):
    calls = 0

    def fake_run(*args, cwd=None):
        nonlocal calls
        calls += 1
        if args[:3] == ("git", "fetch", "--depth=1"):
            raise subprocess.CalledProcessError(128, args)
        return ""

    monkeypatch.setattr(pin, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        pin.clone_source("https://example.invalid/repo.git", "missing", tmp_path)
    assert calls == 3


def test_main_defaults_update_to_master(monkeypatch):
    requested_refs = []
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    monkeypatch.setattr(pin, "update", requested_refs.append)

    pin.main()

    assert requested_refs == ["master"]
