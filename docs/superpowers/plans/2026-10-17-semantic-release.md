# Semantic Release for dizdiz — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every push to `main` automatically bumps `pyproject.toml`'s version from Conventional Commit messages, regenerates `CHANGELOG.md`, tags `vX.Y.Z`, and creates a GitHub Release — with non-conventional commit messages rejected locally by a git hook and in CI.

**Architecture:** `python-semantic-release` (PSR) v10 runs as a GitHub Actions job on `push: main`, preceded by a validation step that rejects malformed commit subjects. The same shell validator backs a versioned git hook (`.githooks/commit-msg`) activated per clone via `core.hooksPath`, so bad messages are caught before they exist. PSR rewrites `pyproject.toml` + `CHANGELOG.md`, commits `chore(release): vX.Y.Z [skip ci]`, tags, and creates the GitHub Release.

**Tech Stack:** GitHub Actions, Python Semantic Release v10 (CI-only, never a project dependency), bash + grep, pytest 9 (already the repo's only automated check).

**Spec:** `docs/superpowers/specs/2026-10-17-semantic-release-design.md`

## Global Constraints

- Linux-only project; bash for scripts (no Python for the validator — it must work without a venv).
- Python 3.11+; `pytest` is the repo's **only** automated check. Do **not** introduce linters/formatters/type checkers.
- PSR is installed **in CI only** (bundled by the action). Never add it to `[project] dependencies` or dev extras.
- Conventional Commit type allowlist, verbatim: `feat fix perf refactor docs test build ci chore revert`.
- Validator regex, verbatim: `^(feat|fix|perf|refactor|docs|test|build|ci|chore|revert)(\([a-zA-Z0-9._/-]+\))?!?: .+`
- PSR config, verbatim: `version_toml = ["pyproject.toml:project.version"]`, `major_on_zero = false`, `[tool.semantic_release.publish] upload_to_vcs_release = true`.
- Version source of truth is `pyproject.toml` only (no `__version__` anywhere in `dizdiz/`).
- Actions pinned: `actions/checkout@v7` (latest `v7.0.1`, sha `3d3c42e5aac5ba805825da76410c181273ba90b1`), `python-semantic-release/python-semantic-release@v10` (latest `v10.7.0`).
- `docs/` is in `.gitignore`; new files under `docs/` must be added with `git add -f` (existing precedent).
- Verified 2026-10-17: `main` is **unprotected** (`gh api repos/jullury/dizdiz/branches/main/protection` → 404), so the bot's push of the release commit + tag will succeed with the default `GITHUB_TOKEN`.

---

### Task 1: Commit message validator + tests

**Files:**
- Create: `tools/check-commit-msg.sh`
- Test: `tests/test_commit_msg_check.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `tools/check-commit-msg.sh <file>|-` — validates every non-empty input line as a Conventional Commit subject; exits `0` when all valid, `1` otherwise (invalid lines printed to stderr). Called by `.githooks/commit-msg` (Task 2) and the workflow's validation step (Task 4).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_commit_msg_check.py`:

```python
"""Tests for tools/check-commit-msg.sh (the Conventional Commits guard)."""
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "check-commit-msg.sh"

VALID_SUBJECTS = [
    "feat(app): add score overlay",
    "fix(hook): ignore key repeat events",
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_commit_msg_check.py -v`
Expected: failures — `bash` exits `127` because `tools/check-commit-msg.sh` does not exist.

- [ ] **Step 3: Write the validator**

Create `tools/check-commit-msg.sh`:

```bash
#!/usr/bin/env bash
# Validate commit message subjects against Conventional Commits.
#
# Usage:
#   tools/check-commit-msg.sh <file>   # validates the first line of <file>
#   tools/check-commit-msg.sh -        # reads subjects from stdin, one per line
#
# Exits 0 when every subject is valid, 1 otherwise.
set -euo pipefail

readonly TYPES='feat|fix|perf|refactor|docs|test|build|ci|chore|revert'
readonly PATTERN="^(${TYPES})(\([a-zA-Z0-9._/-]+\))?!?: .+"

subjects() {
  if [ "$#" -gt 0 ] && [ "$1" != "-" ]; then
    head -n 1 "$1"
  else
    cat
  fi
}

status=0
while IFS= read -r line || [ -n "$line" ]; do
  [ -z "$line" ] && continue
  if ! printf '%s' "$line" | grep -Eq "$PATTERN"; then
    printf 'invalid commit message: %s\n' "$line" >&2
    status=1
  fi
done < <(subjects "$@")

if [ "$status" -ne 0 ]; then
  cat >&2 <<'EOF'

Commit subjects must follow Conventional Commits, e.g.
  feat(app): add score overlay
  fix(hook): ignore key repeat events
  chore(deps)!: drop Python 3.10   (! marks a breaking change)

Allowed types: feat fix perf refactor docs test build ci chore revert
Merge commits are not conventional - merge with squash or rebase instead
(or use `git commit --no-verify` when a merge message is unavoidable).
EOF
  exit 1
fi
```

- [ ] **Step 4: Make it executable and verify the mode is recorded**

```bash
chmod +x tools/check-commit-msg.sh
git add tools/check-commit-msg.sh
git ls-files -s tools/check-commit-msg.sh   # expect mode 100755
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `python3 -m pytest tests/test_commit_msg_check.py -v`
Expected: PASS (all cases; 6 parametrized invalid + 5 others).

- [ ] **Step 6: Run the whole suite (no regressions)**

Run: `python3 -m pytest`
Expected: PASS — the pre-existing 19 tests plus the new ones.

- [ ] **Step 7: Commit**

```bash
git add tools/check-commit-msg.sh tests/test_commit_msg_check.py
git commit -m "feat(release): add conventional commit message validator"
```

---

### Task 2: Local git hook + activation

**Files:**
- Create: `.githooks/commit-msg`
- Modify: `AGENTS.md` (add hook setup; the "no CI" correction belongs to Task 4)

**Interfaces:**
- Consumes: `tools/check-commit-msg.sh <file>` from Task 1.
- Produces: an activated local hook on this clone (`core.hooksPath=.githooks`) that rejects non-conventional subjects before a commit is created.

- [ ] **Step 1: Write the hook**

Create `.githooks/commit-msg`:

```bash
#!/usr/bin/env bash
# Git commit-msg hook: reject subjects that are not Conventional Commits.
# Enable per clone with: git config core.hooksPath .githooks
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
exec "$root/tools/check-commit-msg.sh" "$1"
```

- [ ] **Step 2: Verify the hook by direct invocation**

```bash
chmod +x .githooks/commit-msg
printf 'fixed stuff\n' > /home/jullury/tmp/opencode/msg.txt
.githooks/commit-msg /home/jullury/tmp/opencode/msg.txt   # expect exit 1 + "invalid commit message"
printf 'feat(app): ok\n' > /home/jullury/tmp/opencode/msg.txt
.githooks/commit-msg /home/jullury/tmp/opencode/msg.txt   # expect exit 0, no output
```

- [ ] **Step 3: Activate the hook on this clone**

```bash
git config core.hooksPath .githooks
git config --get core.hooksPath   # expect: .githooks
```

- [ ] **Step 4: Verify a real commit is rejected, then that a good one is accepted**

```bash
printf 'x\n' > .hook-test.tmp
git add .hook-test.tmp
git commit -m "fixed stuff"          # expect: REJECTED, exit 1, files listed as invalid commit message
git restore --staged .hook-test.tmp && rm -f .hook-test.tmp
git status --short                   # expect: clean except AGENTS.md once edited
```

- [ ] **Step 5: Document the hook in `AGENTS.md`**

In `AGENTS.md`, in the "Commands" section, after the `pytest` line, add:

```markdown
- Enable the commit-message guard (once per clone): `git config core.hooksPath .githooks`
```

- [ ] **Step 6: Commit (this commit passes through the newly active hook)**

```bash
git add .githooks/commit-msg AGENTS.md
git commit -m "chore(release): add local conventional commit guard"
```

Expected: commit succeeds — proving the hook accepts valid messages end-to-end.

---

### Task 3: PSR configuration in `pyproject.toml`

**Files:**
- Modify: `pyproject.toml` (append two tables at the end of the file)

**Interfaces:**
- Consumes: nothing (standalone config).
- Produces: the `[tool.semantic_release]` configuration read by the action in Task 4; stamps `pyproject.toml:project.version`.

- [ ] **Step 1: Append the configuration**

Append to the end of `pyproject.toml`:

```toml

[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
major_on_zero = false

[tool.semantic_release.publish]
upload_to_vcs_release = true
```

- [ ] **Step 2: Validate the config with a throwaway PSR install (no side effects)**

```bash
python3 -m venv /home/jullury/tmp/opencode/psr-verify
/home/jullury/tmp/opencode/psr-verify/bin/pip install --quiet python-semantic-release==10.7.0
cd /home/jullury/Projects/Jullury/dizdiz
/home/jullury/tmp/opencode/psr-verify/bin/semantic-release -vv --noop version --print
```

Expected: exit `0` and a single version line. This repo currently has **no tags**, and PSR v10's `allow_zero_version = false` default means that line is `1.0.0` — which is exactly why Task 5 seeds `v0.1.0` before the workflow can ever run. A non-zero exit means the config or the install is wrong: stop and fix before continuing.

Verify noop left nothing behind: `git status --porcelain` → expect empty.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat(release): configure python-semantic-release"
```

---

### Task 4: Release workflow + docs

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `AGENTS.md` (correct the "no CI" claim, describe the release flow)
- Modify: `README.md` (add a "Releases" section)

**Interfaces:**
- Consumes: `tools/check-commit-msg.sh` (Task 1), `[tool.semantic_release]` config (Task 3).
- Produces: the automated release path on `push: main`.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    branches: [main]

permissions:
  contents: write

concurrency: release

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v7
        with:
          fetch-depth: 0

      - name: Validate commit messages
        run: |
          before="${{ github.event.before }}"
          # all-zeros = new branch or force push; that range is meaningless, so be broad
          if [ "$before" = "0000000000000000000000000000000000000000" ]; then
            git log -50 --format=%s HEAD | bash tools/check-commit-msg.sh -
          else
            git log --format=%s "$before..${{ github.sha }}" | bash tools/check-commit-msg.sh -
          fi

      - name: Python Semantic Release
        uses: python-semantic-release/python-semantic-release@v10
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          git_committer_name: github-actions
          git_committer_email: actions@users.noreply.github.com
          verbosity: 2
```

Design notes for the implementer, so nobody "improves" these away:
- No `publish-action` step: it only uploads release assets, and this design ships none.
- The validation step runs **before** PSR by design — a malformed message must fail the run before any version is stamped.
- A push made with the default `GITHUB_TOKEN` does not retrigger workflows (GitHub's loop protection), and PSR's default commit message carries `[skip ci]` anyway.
- If all commits in the range are conventional but none warrant a release (only `chore:`, `docs:`, `test:`), PSR creates no release and the job exits green — correct semver behavior, not a bug.

- [ ] **Step 2: Validate the YAML parses**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml')); print('yaml ok')"
```

Expected: `yaml ok`.

- [ ] **Step 3: Simulate the validation step locally, both outcomes**

```bash
# pass: a real range from this repo (adjust the range to any two existing commits)
git log --format=%s 5f4b028..03375e5 | bash tools/check-commit-msg.sh -   # expect exit 0
# fail: a malformed subject
printf 'fixed stuff\n' | bash tools/check-commit-msg.sh -                  # expect exit 1
```

- [ ] **Step 4: Correct `AGENTS.md`**

The "Verification reality" section currently claims there is no CI. Replace:

```markdown
There is **no** linter, formatter, type checker, or CI here. `pytest` (currently 19
tests) is the only automated check and must pass. Do not invent `ruff`/`mypy`/`make`
steps from generic habits.
```

with:

```markdown
There is **no** linter, formatter, or type checker here. `pytest` is the only local
automated check and must pass. The only CI is `.github/workflows/release.yml`, and it
does not run tests — on every push to `main` it validates commit subjects, then runs
`python-semantic-release` to bump `pyproject.toml`, regenerate `CHANGELOG.md`, tag
`vX.Y.Z`, and create a GitHub Release. Commit subjects must be Conventional Commits
(hook: `git config core.hooksPath .githooks`); non-conforming messages fail both the
hook and the workflow.
```

- [ ] **Step 5: Add a Releases section to `README.md`**

```markdown
## Releases

Versioning is automated from Conventional Commit messages
(`feat` → minor, `fix`/`perf` → patch, `!`/`BREAKING CHANGE` → minor while the
major version is `0`). Every push to `main` runs
`.github/workflows/release.yml`, which bumps `pyproject.toml`, regenerates
`CHANGELOG.md`, tags `vX.Y.Z`, and publishes a GitHub Release.

Enable the local commit-message guard once per clone:

```bash
git config core.hooksPath .githooks
```
```

- [ ] **Step 6: Verify script modes and commit**

```bash
git ls-files -s tools/check-commit-msg.sh .githooks/commit-msg   # expect 100755 for both
git add .github/workflows/release.yml AGENTS.md README.md
git commit -m "feat(release): automate releases on push to main"
```

---

### Task 5: Activate on `main` (remote state — requires explicit user go-ahead)

**Files:** none (repository state only).

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: tag `v0.1.0` on the pre-tooling `main` HEAD; the first automated release (`v0.2.0`) from the conventional squash-merge commit.

Ordering matters: the `v0.1.0` anchor **must** exist before the workflow ever runs, otherwise the first run has no previous version and `allow_zero_version = false` makes it release `1.0.0`.

- [ ] **Step 1: Confirm with the user before touching the remote**

Ask explicitly. This task creates a tag and merges to `main` on GitHub. Do not proceed on an assumed "yes".

- [ ] **Step 2: Seed the `v0.1.0` anchor on `main` HEAD**

```bash
git fetch origin
git tag -a v0.1.0 origin/main -m "dizdiz 0.1.0"
git push origin v0.1.0
git ls-remote --tags origin v0.1.0   # expect the tag present
```

A tag push does not match `push: branches: [main]`, so it does not trigger the workflow — and the workflow file is not on `main` yet anyway.

- [ ] **Step 3: Push the branch and merge to `main` with a conventional squash title**

Merge so that the only commit after the anchor is a `feat:` subject — that both proves the release path end-to-end and honestly describes the change:

```bash
git push -u origin HEAD
gh pr create --title "feat(release): automate semantic versioning, changelog, and commit guards" --body "Implements docs/superpowers/specs/2026-10-17-semantic-release-design.md"
```

Squash-merge with that exact title (a `feat:` subject → minor bump → `0.2.0`). Merging with a bare "Merge pull request …" message would fail the validator — that failure is intended behavior, not a bug; fix the merge title.

- [ ] **Step 4: Watch the first run**

```bash
gh run list --workflow=release.yml --limit 3
gh run watch "$(gh run list --workflow=release.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Expected: the "Validate commit messages" step passes, then PSR releases `0.2.0`.

- [ ] **Step 5: Verify the release artifacts**

```bash
git fetch --tags origin
git tag -l 'v0.*'                                  # expect v0.1.0 and v0.2.0
gh release view v0.2.0                             # expect a release with generated notes
git show origin/main:pyproject.toml | grep '^version'   # expect version = "0.2.0"
git show origin/main:CHANGELOG.md | head -30       # expect a generated changelog
```

- [ ] **Step 6: Pull the bot's release commit locally**

```bash
git checkout main && git pull --ff-only
git log --oneline -3    # expect chore(release): 0.2.0 and the squash-merged feature commit
```

---

## Self-Review

**Spec coverage:** workflow (§1 → Task 4); checker + two call sites (§2 → Tasks 1, 4); local hook + activation (§3 → Task 2); PSR config incl. `major_on_zero = false` (§4 → Task 3); bootstrap anchor tag + unprotected-branch check (§5 → Task 5, protection verified up front); AGENTS.md + README (§6 → Tasks 2, 4); bootstrap tag, verification plan, open items (§Verification → Tasks 3, 4, 5).

**Placeholder scan:** no TBD/TODO; every file's full content is inline; every expected result is stated.

**Type/name consistency:** `tools/check-commit-msg.sh` invoked identically (file arg in the hook, `-` with piped subjects in CI) across Tasks 1, 2, 4; `version_toml` target matches the `version` key in Task 3 and the verification in Task 5; action refs match the pinned versions in Global Constraints.

**Known deviation from the spec:** none.
