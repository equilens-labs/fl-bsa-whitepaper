#!/usr/bin/env bash
set -euo pipefail
OUTDIR="dist/arxiv"
rm -rf "$OUTDIR"
mkdir -p "$OUTDIR"

# Copy core sources (tolerate optional files)
cp -v main.tex "$OUTDIR"/
if [ -f .latexmkrc ]; then cp -v .latexmkrc "$OUTDIR"/; fi

for dir in sections includes figures bib; do
  if [ -d "$dir" ]; then
    cp -vr "$dir" "$OUTDIR"/
  fi
done

# Keep .bbl if present; arXiv can also run bibtex, but include for safety
if [ -f main.bbl ]; then cp -v main.bbl "$OUTDIR"/; fi

# Zip
mkdir -p dist
cd dist
zip -r whitepaper_arxiv_source.zip arxiv
echo "Wrote dist/whitepaper_arxiv_source.zip"
