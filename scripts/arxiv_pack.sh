#!/usr/bin/env bash
set -euo pipefail

source_date_epoch="${SOURCE_DATE_EPOCH:-}"
if [ -z "$source_date_epoch" ]; then
  source_date_epoch="$(git log -1 --format=%ct HEAD)"
fi
if [[ ! "$source_date_epoch" =~ ^[0-9]+$ ]]; then
  echo "SOURCE_DATE_EPOCH must be a positive integer; got ${source_date_epoch@Q}." >&2
  exit 1
fi

python3 scripts/package_arxiv_source.py \
  --repo-root . \
  --output dist/whitepaper_arxiv_source.zip \
  --source-date-epoch "$source_date_epoch"
