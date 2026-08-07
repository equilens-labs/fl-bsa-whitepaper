PDF=dist/whitepaper.pdf
CANDIDATE_PDF=dist/fl-bsa-v5.0.1-characterization-candidate.pdf
COMPANION=dist/fl-bsa-v5.0.1-companion-evidence.zip
IDENTITY=includes/publication_identity.tex
CANDIDATE_PROFILE=profiles/publication_profile.candidate.tex
LOCAL_PROFILE=includes/publication_profile.local.tex
COMPATIBILITY_INTAKE=dist/stable-v5-intake-compatibility.zip
PUBLICATION_MANIFEST=dist/publication-manifest.json
UTILITY_SUMMARY_SHA256=2b05a4a2b7ce2d798b9156ed5f837efe890ee87e4f5e914497724802636e4595
GOLD_EVIDENCE_MANIFEST_SHA256=353cd77907a5b5b0f64534ce6e5b00defeb872f5a8585aec43006ec24f96e073
GOLD_INDEX_SHA256=9ffb2c04a95f428f068d471732c7d9ed1e27a16d553749c2ec828907fbe9166c
GOLD_SUMMARY_SHA256=15bee5d51c6816e4bd8bffdde3bcb657e5a25932f9742f17496c7a53884858ce
EXPECTED_TABLE_HEADER_CELLS=26
EXPECTED_FIGURE_TAGS=7
VERAPDF_IMAGE=ghcr.io/verapdf/cli@sha256:595d7791a9321975cde6b7f5393beed98d76167ea6c39af191704462a4fa8b9d
VERAPDF_REPORT=dist/verapdf-ua1-preflight.xml
SOURCE_DATE_EPOCH ?= $(shell git log -1 --format=%ct HEAD)
export SOURCE_DATE_EPOCH
export FORCE_SOURCE_DATE = 1
export TZ = UTC

.PHONY: all test macros plots characterization assets companion identity pdf candidate ua-preflight arxiv publication-candidate publication-candidate-repeatability clean

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
	python3 scripts/verify_companion_bundle.py \
		--expected-utility-sha256 $(UTILITY_SUMMARY_SHA256) \
		--expected-gold-manifest-sha256 $(GOLD_EVIDENCE_MANIFEST_SHA256) \
		--expected-gold-index-sha256 $(GOLD_INDEX_SHA256) \
		--expected-gold-summary-sha256 $(GOLD_SUMMARY_SHA256) \
		$(COMPANION)

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
	python3 scripts/verify_companion_bundle.py \
		--expected-utility-sha256 $(UTILITY_SUMMARY_SHA256) \
		--expected-gold-manifest-sha256 $(GOLD_EVIDENCE_MANIFEST_SHA256) \
		--expected-gold-index-sha256 $(GOLD_INDEX_SHA256) \
		--expected-gold-summary-sha256 $(GOLD_SUMMARY_SHA256) \
		$(COMPANION)
	python3 scripts/gen_publication_identity.py --require-clean --repo-root . --companion $(COMPANION) --output $(IDENTITY)
	latexmk -C main.tex
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
	test "$$(pdftotext main.pdf - | grep -F -c 'DEMO / EVALUATION ONLY')" -eq 1
	python3 scripts/check_pdf_tag_structure.py --expected-header-cells $(EXPECTED_TABLE_HEADER_CELLS) --expected-figures $(EXPECTED_FIGURE_TAGS) main.pdf
	mkdir -p dist
	cp main.pdf $(PDF)
	cp main.pdf $(CANDIDATE_PDF)

# The PDF intentionally makes no formal PDF/UA claim until human assistive-
# technology review. Forced-profile preflight must therefore fail only on the
# absent PDF/UA identification metadata, and on no substantive UA-1 rule.
ua-preflight:
	@mkdir -p dist; \
	status=0; \
	docker run --rm -v "$(CURDIR):/data:ro" $(VERAPDF_IMAGE) \
		-f ua1 /data/main.pdf > $(VERAPDF_REPORT) || status=$$?; \
	if [ "$$status" -ne 1 ]; then \
		echo "expected veraPDF's non-conformance exit 1 for the undeclared candidate; got $$status" >&2; \
		exit 1; \
	fi; \
	python3 scripts/verify_verapdf_ua_preflight.py $(VERAPDF_REPORT)

arxiv: identity
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
	bibtex main || true
	bash scripts/arxiv_pack.sh

# Build the complete local handoff set sequentially so the publication manifest
# cannot describe stale ignored artifacts from an earlier whitepaper commit.
publication-candidate:
	$(MAKE) candidate
	$(MAKE) ua-preflight
	$(MAKE) arxiv
	python3 -S scripts/intake_anchor.py export --anchor baselines/stable-v5-characterization.json --repo-root . --output $(COMPATIBILITY_INTAKE)
	python3 scripts/build_publication_manifest.py --whitepaper-commit "$$(git rev-parse HEAD)" --publication-status candidate_not_published --companion $(COMPANION) --arxiv dist/whitepaper_arxiv_source.zip --compatibility-intake $(COMPATIBILITY_INTAKE) --output $(PUBLICATION_MANIFEST)

# Rebuild the complete handoff set twice and compare every delivered artifact.
# This is intentionally explicit rather than inferred from component-level tests.
publication-candidate-repeatability:
	@set -eu; \
	$(MAKE) publication-candidate; \
	reference_dir="$$(mktemp -d)"; \
	trap 'rm -rf "$$reference_dir"' 0; \
	for artifact in \
		$(CANDIDATE_PDF) \
		$(COMPANION) \
		dist/whitepaper_arxiv_source.zip \
		$(COMPATIBILITY_INTAKE) \
		$(PUBLICATION_MANIFEST); do \
		mkdir -p "$$reference_dir/$$(dirname "$$artifact")"; \
		cp "$$artifact" "$$reference_dir/$$artifact"; \
	done; \
	$(MAKE) publication-candidate; \
	for artifact in \
		$(CANDIDATE_PDF) \
		$(COMPANION) \
		dist/whitepaper_arxiv_source.zip \
		$(COMPATIBILITY_INTAKE) \
		$(PUBLICATION_MANIFEST); do \
		cmp "$$reference_dir/$$artifact" "$$artifact"; \
	done; \
	echo "Complete publication handoff is byte-reproducible across two builds."

clean:
	latexmk -C
	rm -f $(IDENTITY) $(PDF) $(CANDIDATE_PDF) $(COMPANION)
