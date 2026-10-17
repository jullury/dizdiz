# Semantic Release for dizdiz — Design

Date: 2026-10-17
Status: approved (design), pending spec review

## Goal

Every push to `main` automatically produces a semantic release: version bump in
`pyproject.toml`, regenerated `CHANGELOG.md`, a `vX.Y.Z` git tag, and a GitHub
Release — with loud failure on commit messages that don't follow Conventional
Commits.

## Decisions (confirmed with user)

| Decision | Choice | Rationale |
|---|---|---|
| Tool | `python-semantic-release` (PSR) v10 | Python-native, config lives in `pyproject.toml`; `semantic-release` (JS) would add a Node toolchain for no gain; `release-please`'s PR model contradicts "version updates on push to main"; `setuptools-scm` never writes a version, contradicting the requirement. |
| Trigger | GitHub Actions on `push: branches: [main]` | Repo is on GitHub (`jullury/dizdiz`); no CI exists today, this is the first workflow. |
| Release output | Version bump + `CHANGELOG.md` + tag + GitHub Release notes | No wheel artifacts, no PyPI publishing (YAGNI; can be added later). |
| Bad commit messages | Fail the workflow **and** block locally via pre-commit guard | Silent skips hide drift; semver stays honest. |
| Guard mechanism | Plain versioned git hooks (`.githooks/` + `core.hooksPath`) | Zero dependencies; `pre-commit` framework or `commitizen` would add weight for a single regex. |
| 0.x breaking changes | Bump **minor**, not major | PSR v10 defaults `major_on_zero = true` (0.x breaking → 1.0.0); we set `major_on_zero = false` explicitly to keep 0.x semantics. |

## Non-goals

- Publishing to PyPI, building wheels, or attaching artifacts (out of scope until asked).
- Enforcing commit style beyond validity (e.g. allowed scopes) — format only.
- Supporting merge-commit workflows: `Merge branch 'x'` messages are non-conventional and will fail the guard. Squash/rebase merging avoids this.

## Current state (facts this design builds on)

- `main` commits already follow Conventional Commits (`feat(app):`, `fix(app):`, `test:`, `chore(tools):`, `docs:`).
- Version exists only in `pyproject.toml` (`version = "0.1.0"`); no `__version__` in code.
- No git tags, no `CHANGELOG`, no `.github/workflows/`.
- PSR v10.7.0 is current; with no anchor tag its `allow_zero_version = false` default would make the first release `1.0.0`.

## Design

### 1. Release workflow — `.github/workflows/release.yml`

```yaml
name: Release
on:
  push:
    branches: [main]
permissions:
  contents: write          # push release commit + tag, create GitHub Release
concurrency: release       # never run two releases in parallel
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout  # release tag resolved + pinned to a commit SHA during implementation
        with:
          fetch-depth: 0  # PSR needs full history + tags
      - name: Validate commit messages
        run: <see §2 — fail the job before releasing on any non-conventional subject>
      - name: Python Semantic Release
        uses: python-semantic-release/python-semantic-release@v10
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          git_committer_name: github-actions
          git_committer_email: actions@users.noreply.github.com
```

Flow when it fires: PSR computes the next version from conventional commits
since `v<last>`, stamps `pyproject.toml`, regenerates `CHANGELOG.md`, commits
`chore(release): v{version} [skip ci]` (PSR's default message), tags `vX.Y.Z`,
pushes both, and creates the GitHub Release. PSR aborts safely if `main` moved
upstream mid-run (it re-verifies before pushing). If all commits in the range
are conventional but none warrant a release (`chore:`, `docs:`, `test:` only),
PSR makes no release and exits green — correct semver behavior; the "fail"
rule applies only to malformed messages.

Notes:
- `publish-action` is **not** used — it only uploads assets, and we have none.
- Default `GITHUB_TOKEN` pushes don't retrigger workflows (GitHub's loop
  protection), so the release commit cannot loop even without `[skip ci]`;
  the tag is kept anyway as defense in depth.

### 2. Commit message checker — `tools/check-commit-msg.sh`

One regex, two call sites, zero dependencies (bash + grep).

- Input: a file path (git commit-msg hook passes `"$1"`) or `-` for stdin (CI
  pipes `git log` subjects through it).
- Rule: first line must match
  `^(feat|fix|perf|refactor|docs|test|build|ci|chore|revert)(\([a-zA-Z0-9._/-]+\))?!?: .+`
  (optional scope, optional `!` for breaking, non-empty description).
- On failure: print every offending line to stderr and exit 1.

CI validation step:

```bash
before="${{ github.event.before }}"
# all-zeros = branch creation or force push; that range is meaningless, so be broad
if [ "$before" = "0000000000000000000000000000000000000000" ]; then
  git log -50 --format=%s HEAD | tools/check-commit-msg.sh -
else
  git log --format=%s "$before..${{ github.sha }}" | tools/check-commit-msg.sh -
fi
```

### 3. Local guard — `.githooks/commit-msg`

Thin wrapper: resolve repo root via `git rev-parse --show-toplevel`, delegate
to `tools/check-commit-msg.sh "$1"`. Enabled per clone with the one-time:

```bash
git config core.hooksPath .githooks
```

### 4. PSR configuration — `pyproject.toml`

```toml
[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
major_on_zero = false        # 0.x breaking changes bump minor, not to 1.0.0

[tool.semantic_release.publish]
upload_to_vcs_release = true  # create the GitHub Release with the notes
```

The changelog target defaults to `CHANGELOG.md` in PSR v10; if the pinned
version's default differs, set it explicitly during implementation.

PSR is installed **only in CI** (the action bundles it) — never a project
dependency, never required locally.

### 5. Bootstrap

- Create annotated tag `v0.1.0` on whatever `main` HEAD is **at implementation
  time** (it will have moved past the SHA in this doc) and push it, so the first
  CI run has a "last release" anchor instead of jumping to `1.0.0`.
  Touches remote state → executed only with explicit user go-ahead.
- Pre-check repo settings: **verified 2026-10-17** via `gh api
  repos/jullury/dizdiz/branches/main/protection` → `404 Branch not protected`.
  No protection rules, so the `GITHUB_TOKEN` push (commit + tag + release) is
  not blocked and no signed-commit requirement exists. If protection is added
  later, the bot push would start failing and this design must be revisited
  (e.g. a PAT or GitHub App token, or a PR-based model).

### 6. Documentation

- `AGENTS.md`: the claim "There is **no** linter, formatter, type checker, or
  CI here. `pytest` … is the only automated check" becomes false — update it to
  describe the release workflow, the commit-msg rule, and the hook setup command.
- `README.md`: short "Releases" section (how versioning works, how to enable the
  hook).

## Files touched

| File | Change |
|---|---|
| `.github/workflows/release.yml` | new |
| `tools/check-commit-msg.sh` | new |
| `.githooks/commit-msg` | new |
| `pyproject.toml` | append `[tool.semantic_release]` tables |
| `AGENTS.md` | correct the "no CI" statement, document hook |
| `README.md` | releases section |
| `CHANGELOG.md` | generated on first release (not hand-written) |
| git tag `v0.1.0` | bootstrap, remote state, needs user go-ahead |

No app code changes; `tests/` and `pytest` are unaffected.

## Verification

1. `tools/check-commit-msg.sh` exercised against positive/negative samples
   (`feat(app): x`, `fix!: y`, `Merge branch 'main'`, `fixed stuff`) via direct
   invocation and via the hook path on a real commit.
2. Config validity + computed next version checked locally with a throwaway
   install: `semantic-release -vv noop version --print` must parse the config
   and print the expected next version without side effects.
3. `pytest` still green.
4. After merge: seed the `v0.1.0` tag, then watch the first real workflow run.

## Open items

- ~~Confirm `main` branch protection status via `gh`~~ — verified: `main` is
  unprotected (see §5).
- Pin exact action commit SHAs at implementation time.
