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

# Fail closed: a path argument that cannot be read is an input error, not a pass.
if [ "$#" -gt 0 ] && [ "$1" != "-" ] && [ ! -r "$1" ]; then
  printf 'invalid commit message: cannot read %s\n' "$1" >&2
  exit 1
fi

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
