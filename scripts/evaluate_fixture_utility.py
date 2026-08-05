#!/usr/bin/env python3
"""Reproduce the v5.0.1 synthetic-fixture TSTR utility characterization.

The script is intentionally external to the product repository.  It imports the
generator from an exact-tag checkout, keeps protected attributes out of the
downstream classifier, and evaluates ten generated training sets against one
held-out split of the original synthetic fixture.  It does not make a customer,
privacy, legal, or production-utility claim.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from statistics import mean, stdev
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


EXPECTED_PRODUCT_COMMIT = "cc32b3a8d13cb75419b0dec1d4b9bdf5a3eb90c2"
EXPECTED_PRODUCT_TAG = "v5.0.1"
EXPECTED_FIXTURE_SHA256 = (
    "b04f721d789226723066b3d6ae70e4ab2a3fa17c825ef1d0e04d7d779571982b"
)
TRAIN_TEST_SEED = 50101
GENERATOR_FIT_SEED = 42
GENERATION_SEEDS = (7, 11, 23, 42, 101, 1337, 2025, 4096, 8191, 314159)
TARGET = "loan_approved"
PROTECTED = ("gender", "race")
FEATURES = ("age", "income", "credit_score", "loan_amount", "debt_to_income")


class UtilityError(ValueError):
    """Raised when an input cannot support the bounded utility study."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(product_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(product_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise UtilityError(completed.stderr.strip() or "unable to resolve product Git identity")
    return completed.stdout.strip()


def _read_fixture(path: Path) -> tuple[pd.DataFrame, str, str]:
    compressed = path.read_bytes()
    try:
        raw = gzip.decompress(compressed)
    except OSError as exc:
        raise UtilityError(f"fixture is not a valid gzip stream: {exc}") from exc
    raw_sha = _sha256(raw)
    if raw_sha != EXPECTED_FIXTURE_SHA256:
        raise UtilityError(
            f"fixture SHA-256 {raw_sha} does not match {EXPECTED_FIXTURE_SHA256}"
        )
    frame = pd.read_csv(path)
    required = {*FEATURES, *PROTECTED, TARGET}
    if set(frame.columns) != required:
        raise UtilityError(
            f"fixture columns {sorted(frame.columns)} do not match {sorted(required)}"
        )
    if frame.empty or frame[TARGET].nunique() != 2:
        raise UtilityError("fixture must contain rows and both outcome classes")
    return frame, raw_sha, _sha256(compressed)


def _stratified_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(TRAIN_TEST_SEED)
    train_indices: list[int] = []
    test_indices: list[int] = []
    for _, group in frame.groupby(TARGET, sort=True):
        indices = group.index.to_numpy(copy=True)
        rng.shuffle(indices)
        test_count = int(round(len(indices) * 0.30))
        test_indices.extend(int(index) for index in indices[:test_count])
        train_indices.extend(int(index) for index in indices[test_count:])
    train = frame.loc[sorted(train_indices)].reset_index(drop=True)
    test = frame.loc[sorted(test_indices)].reset_index(drop=True)
    if len(train) + len(test) != len(frame):
        raise UtilityError("train/test split lost rows")
    return train, test


def _classifier() -> Pipeline:
    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    return Pipeline(
        steps=[
            (
                "features",
                ColumnTransformer(
                    [("numeric", numeric, list(FEATURES))],
                    remainder="drop",
                    verbose_feature_names_out=False,
                ),
            ),
            (
                "classifier",
                LogisticRegression(
                    random_state=TRAIN_TEST_SEED,
                    solver="lbfgs",
                    max_iter=2_000,
                ),
            ),
        ]
    )


def _evaluate(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, float]:
    model = _classifier()
    model.fit(train.loc[:, list(FEATURES)], train[TARGET].astype(int))
    probabilities = model.predict_proba(test.loc[:, list(FEATURES)])[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    labels = test[TARGET].astype(int).to_numpy()
    return {
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "average_precision": float(average_precision_score(labels, probabilities)),
        "accuracy_at_0_5": float(accuracy_score(labels, predictions)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "positive_rate_train": float(train[TARGET].astype(int).mean()),
    }


def _bands(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "min": min(values),
        "mean": mean(values),
        "max": max(values),
        "stdev": stdev(values),
    }


def build_summary(product_root: Path, fixture_path: Path) -> dict[str, Any]:
    product_root = product_root.resolve()
    head = _git(product_root, "rev-parse", "HEAD")
    tag = _git(product_root, "describe", "--exact-match", "--tags", "HEAD")
    if head != EXPECTED_PRODUCT_COMMIT or tag != EXPECTED_PRODUCT_TAG:
        raise UtilityError(
            f"product checkout is {tag}@{head}; expected "
            f"{EXPECTED_PRODUCT_TAG}@{EXPECTED_PRODUCT_COMMIT}"
        )

    frame, fixture_sha, compressed_sha = _read_fixture(fixture_path)
    train, test = _stratified_split(frame)
    baseline = _evaluate(train, test)

    sys.path.insert(0, str(product_root))
    from flbsa.synthetic.generators.bundle import (  # pylint: disable=import-outside-toplevel
        FIRST_PARTY_EVIDENCE_NATIVE_BACKEND_ID,
    )
    from flbsa.synthetic.generators.factory import (  # pylint: disable=import-outside-toplevel
        create_dual_branch_generator,
    )

    generator = create_dual_branch_generator(
        FIRST_PARTY_EVIDENCE_NATIVE_BACKEND_ID,
        random_state=GENERATOR_FIT_SEED,
    )
    generator.train_dual_branch(
        train,
        categorical_columns=[*PROTECTED, TARGET],
        amplification_params={"seed": GENERATOR_FIT_SEED},
        intrinsic_params={"seed": GENERATOR_FIT_SEED + 1},
        protected_attributes=list(PROTECTED),
        outcome_column=TARGET,
        verbose=False,
    )

    seed_results: list[dict[str, Any]] = []
    for seed in GENERATION_SEEDS:
        generated = generator.generate_amplification(len(train), seed=seed)
        missing = {*FEATURES, TARGET}.difference(generated.columns)
        if missing:
            raise UtilityError(f"generated data is missing columns: {sorted(missing)}")
        metrics = _evaluate(generated, test)
        seed_results.append(
            {
                "seed": seed,
                "generated_rows": len(generated),
                "generated_sha256": _sha256(
                    generated.to_csv(index=False).encode("utf-8")
                ),
                "metrics": metrics,
                "roc_auc_retention": metrics["roc_auc"] / baseline["roc_auc"],
            }
        )

    metric_names = (
        "roc_auc",
        "average_precision",
        "accuracy_at_0_5",
        "brier_score",
        "log_loss",
        "positive_rate_train",
    )
    bands = {
        metric: _bands([row["metrics"][metric] for row in seed_results])
        for metric in metric_names
    }
    bands["roc_auc_retention"] = _bands(
        [row["roc_auc_retention"] for row in seed_results]
    )

    return {
        "schema_version": "flbsa.whitepaper_fixture_utility.v1",
        "claim_scope": "synthetic_fixture_tstr_characterization_only",
        "product": {
            "repo": "equilens-labs/fl-bsa",
            "tag": tag,
            "commit": head,
            "generator": "first_party_evidence_native",
            "branch": "amplification",
        },
        "source": {
            "fixture": "evidence/v5.0.1/utility/balanced_fixture.csv.gz",
            "fixture_sha256_uncompressed": fixture_sha,
            "fixture_sha256_gzip": compressed_sha,
            "rows": len(frame),
            "synthetic_fixture_only": True,
        },
        "study": {
            "design": "train-on-synthetic-test-on-held-out-original",
            "train_test_seed": TRAIN_TEST_SEED,
            "generator_fit_seed": GENERATOR_FIT_SEED,
            "generation_seeds": list(GENERATION_SEEDS),
            "train_rows": len(train),
            "test_rows": len(test),
            "generated_rows_per_seed": len(train),
            "target": TARGET,
            "features": list(FEATURES),
            "excluded_protected_attributes": list(PROTECTED),
            "classifier": "median-impute + standardize + logistic-regression",
            "decision_threshold": 0.5,
        },
        "real_train_baseline": baseline,
        "synthetic_train_results": seed_results,
        "synthetic_train_bands": bands,
        "limitations": [
            "The source is a generated fixture, not borrower or customer data.",
            "All generated samples share one fitted generator and one held-out split.",
            "Generation-seed variation does not include fixture-generator, model-fit, or deployment variation.",
            "The intrinsic branch is excluded because its post-label policy changes the utility estimand.",
            "The results do not establish production predictive utility, privacy, fairness, or legal compliance.",
        ],
        "runtime": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-root", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = build_summary(args.product_root, args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output), "seeds": len(GENERATION_SEEDS)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
