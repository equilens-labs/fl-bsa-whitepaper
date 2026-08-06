PDF=dist/whitepaper.pdf
CANDIDATE_PDF=dist/fl-bsa-v5.0.1-characterization-candidate.pdf
COMPANION=dist/fl-bsa-v5.0.1-companion-evidence.zip
IDENTITY=includes/publication_identity.tex
CANDIDATE_PROFILE=profiles/publication_profile.candidate.tex
LOCAL_PROFILE=includes/publication_profile.local.tex
COMPATIBILITY_INTAKE=dist/stable-v5-intake-compatibility.zip
PUBLICATION_MANIFEST=dist/publication-manifest.json
SOURCE_DATE_EPOCH ?= $(shell git log -1 --format=%ct HEAD)
export SOURCE_DATE_EPOCH
export FORCE_SOURCE_DATE = 1
export TZ = UTC

.PHONY: all test macros plots characterization assets companion identity pdf candidate arxiv publication-candidate clean

all: pdf

test:
	python3 -m unittest discover -s tests

macros:
	python3 scripts/gen_tex_macros_from_metrics.py --strict --metrics intake/metrics_long.csv --sap config/sap.yaml --outdir includes
	python3 scripts/gen_tex_preamble_from_manifest.py --strict --manifest intake/manifest.json --sap config/sap.yaml --out includes/provenance_macros.tex
	python3 scripts/gen_tex_hyperparams_from_yaml.py --strict --config intake/model_hyperparams.yaml --outdir includes

plots:
	python3 scripts/gen_plots_from_intake.py --selection intake/selection_rates.csv --metrics intake/metrics_long.csv --outdir figures --require-all

characterization:
	python3 scripts/gen_characterization_assets.py --repo-root .

assets: macros plots characterization

companion: assets
	python3 scripts/build_companion_bundle.py --repo-root . --output $(COMPANION)
	python3 scripts/verify_companion_bundle.py $(COMPANION)

identity: companion
	python3 scripts/gen_publication_identity.py --repo-root . --companion $(COMPANION) --output $(IDENTITY)

pdf: identity
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
	mkdir -p dist
	cp main.pdf $(PDF)
	cp main.pdf $(CANDIDATE_PDF)

# A final candidate must be built after all tracked generation outputs have been
# reviewed and committed. Generated dist/ and self-identity files are ignored.
candidate: test assets
	test -z "$$(git status --porcelain --untracked-files=all)"
	cp $(CANDIDATE_PROFILE) $(LOCAL_PROFILE)
	python3 scripts/build_companion_bundle.py --repo-root . --output $(COMPANION)
	python3 scripts/verify_companion_bundle.py $(COMPANION)
	python3 scripts/gen_publication_identity.py --require-clean --repo-root . --companion $(COMPANION) --output $(IDENTITY)
	latexmk -C main.tex
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
	test "$$(pdftotext main.pdf - | grep -F -c 'DEMO / EVALUATION ONLY')" -eq 1
	mkdir -p dist
	cp main.pdf $(PDF)
	cp main.pdf $(CANDIDATE_PDF)

arxiv: identity
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
	bibtex main || true
	bash scripts/arxiv_pack.sh

# Build the complete local handoff set sequentially so the publication manifest
# cannot describe stale ignored artifacts from an earlier whitepaper commit.
publication-candidate:
	$(MAKE) candidate
	$(MAKE) arxiv
	python3 -S scripts/intake_anchor.py export --anchor baselines/stable-v5-characterization.json --repo-root . --output $(COMPATIBILITY_INTAKE)
	python3 scripts/build_publication_manifest.py --whitepaper-commit "$$(git rev-parse HEAD)" --publication-status candidate_not_published --companion $(COMPANION) --arxiv dist/whitepaper_arxiv_source.zip --compatibility-intake $(COMPATIBILITY_INTAKE) --output $(PUBLICATION_MANIFEST)

clean:
	latexmk -C
	rm -f $(IDENTITY) $(PDF) $(CANDIDATE_PDF) $(COMPANION)
