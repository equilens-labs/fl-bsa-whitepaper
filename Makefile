
PDF=dist/whitepaper.pdf

all: pdf

macros:
	python3 scripts/gen_tex_macros_from_metrics.py --metrics intake/metrics_long.csv --sap config/sap.yaml --outdir includes || true
	python3 scripts/gen_tex_preamble_from_manifest.py --manifest intake/manifest.json --sap config/sap.yaml --out includes/provenance_macros.tex || true
	python3 scripts/gen_tex_hyperparams_from_yaml.py --config intake/model_hyperparams.yaml --outdir includes || true

plots:
	python3 scripts/gen_plots_from_intake.py --selection intake/selection_rates.csv --metrics intake/metrics_long.csv --outdir figures || true

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
