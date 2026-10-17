"""Tests for tools/check-commit-msg.sh (the Conventional Commits guard)."""
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "check-commit-msg.sh"

VALID_SUBJECTS = [
    "feat(app): add score overlay",
    "fix(hook): ignore key repeat events",
    "fix(a/b-c.d): scoped subject",
    "fix!: drop Python 3.10 support",
    "chore(tools): regenerate sounds",
    "docs: describe the release flow",
    "revert: feat(app): add score overlay",
]

INVALID_SUBJECTS = [
    "fixed stuff",
    "feat add score overlay",
    "feat(app):",
    "Merge branch 'main'",
    " feat(app): leading whitespace",
    "Update README.md",
]


def run_stdin(text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        input=text,
        text=True,
        capture_output=True,
    )


def test_valid_subjects_pass():
    result = run_stdin("\n".join(VALID_SUBJECTS) + "\n")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("subject", INVALID_SUBJECTS)
def test_invalid_subject_fails(subject):
    result = run_stdin(subject + "\n")
    assert result.returncode == 1
    assert "invalid commit message" in result.stderr


def test_empty_input_passes():
    assert run_stdin("").returncode == 0


def test_dash_argument_reads_stdin():
    result = subprocess.run(
        ["bash", str(SCRIPT), "-"],
        input="feat(app): ok\nfix(a/b-c.d): scoped\n",
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_missing_file_argument_fails(tmp_path):
    result = subprocess.run(
        ["bash", str(SCRIPT), str(tmp_path / "does-not-exist")],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    assert result.stderr.strip()


def test_blank_lines_are_ignored():
    assert run_stdin("feat(app): ok\n\n\n").returncode == 0


def test_file_argument_validates_only_first_line(tmp_path):
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat(app): ok\n\nThis body line is not a subject.\n")
    result = subprocess.run(
        ["bash", str(SCRIPT), str(msg)], text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr


def test_file_argument_rejects_bad_subject(tmp_path):
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("fixed stuff\n")
    result = subprocess.run(
        ["bash", str(SCRIPT), str(msg)], text=True, capture_output=True
    )
    assert result.returncode == 1
