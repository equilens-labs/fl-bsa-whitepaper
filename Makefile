
PDF=dist/whitepaper.pdf
SOURCE_DATE_EPOCH ?= $(shell git log -1 --format=%ct HEAD)
export SOURCE_DATE_EPOCH
export FORCE_SOURCE_DATE = 1
export TZ = UTC

all: pdf

test:
	python3 -m unittest discover -s tests

macros:
	python3 scripts/gen_tex_macros_from_metrics.py --strict --metrics intake/metrics_long.csv --sap config/sap.yaml --outdir includes
	python3 scripts/gen_tex_preamble_from_manifest.py --strict --manifest intake/manifest.json --sap config/sap.yaml --out includes/provenance_macros.tex
	python3 scripts/gen_tex_hyperparams_from_yaml.py --strict --config intake/model_hyperparams.yaml --outdir includes

plots:
	python3 scripts/gen_plots_from_intake.py --selection intake/selection_rates.csv --metrics intake/metrics_long.csv --outdir figures --require-all

pdf: macros plots
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
	mkdir -p dist && cp main.pdf $(PDF)

clean:
	latexmk -C
	rm -f includes/table_*.tex includes/metrics_macros.tex $(PDF)

arxiv: macros
	# Build to generate .bbl for arXiv; then package sources
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
	bibtex main || true
	bash scripts/arxiv_pack.sh
