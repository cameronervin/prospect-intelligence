#!/usr/bin/env sh

set -eu
. "$(dirname -- "$0")/common.sh"

root=$(repo_root)
require_command rg
require_command python3

scan_parent=$(mktemp -d "${TMPDIR:-/tmp}/langchain-takehome-secret-scan.XXXXXX")
scan_root="$scan_parent/snapshot"
cleanup() {
  rm -rf -- "$scan_parent"
}
trap cleanup EXIT HUP INT TERM

python3 "$root/scripts/copy-reviewable-snapshot.py" "$root" "$scan_root"

if command -v gitleaks >/dev/null 2>&1; then
  gitleaks dir --redact --no-banner "$scan_root"
fi

patterns='-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9]{32,}|lsv2_[A-Za-z0-9_-]{24,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{20,}'

if rg -l -I -S --hidden -e "$patterns" "$scan_root"; then
  echo "error: likely credential material found" >&2
  exit 1
fi

echo "secret scan passed"
