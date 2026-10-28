#!/usr/bin/env bash
# One-time setup on the PC, run inside Ubuntu (WSL2) from the repo folder:
#     cd /mnt/h/monopoly-strategy && bash bootstrap.sh
# Safe to run again: every step checks before it changes anything.
set -euo pipefail
cd "$(dirname "$0")"
say() { printf '\n== %s\n' "$*"; }

say "Git settings for a Windows-drive checkout used from Linux"
git config core.autocrlf false
git config core.fileMode false
if [ -z "$(git config user.email || true)" ]; then
  name=$(git log -1 --format=%an); email=$(git log -1 --format=%ae)
  git config user.name "$name"; git config user.email "$email"
  echo "Result commits will be made as: $name <$email> (this repo only)"
fi

say "Line endings"
n_crlf=$(git ls-files --eol | grep -c 'w/crlf' || true)
if [ "$n_crlf" -gt 0 ]; then
  if git diff --quiet --ignore-cr-at-eol HEAD; then
    echo "Switching $n_crlf files to LF line endings (one-time; no content changes)..."
    git rm -r --cached --quiet . && git reset --quiet --hard
    echo "Now $(git ls-files --eol | grep -c 'w/crlf' || true) files with CRLF."
  else
    echo "You have uncommitted changes, so line endings were left alone. Commit or stash them, then rerun." >&2
  fi
else
  echo "Already LF."
fi

say "System packages (make, compilers, curl)"
missing=()
for c in make gcc curl; do command -v "$c" >/dev/null || missing+=("$c"); done
if [ ${#missing[@]} -gt 0 ]; then
  echo "Installing: build-essential curl (needs your Ubuntu password)"
  sudo apt-get update -qq && sudo apt-get install -y -qq build-essential curl
else
  echo "Present."
fi

say "uv (Python package manager)"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

say "Python environment"
make --no-print-directory setup

say "Checks"
make --no-print-directory doctor || true

cat <<'EOF'

Setup finished. Next (step 2 in RUNNING.md):
    make v03
It takes about an hour; Ctrl+C stops it and running `make v03` again resumes it.
EOF
