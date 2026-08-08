"""Shared policy for machine-local paths in public whitepaper artifacts."""

FORBIDDEN_PUBLIC_PATH_MARKERS = (
    b"/mnt/ci-work/",
    b"/home/ci/",
    b"/home/runner/",
    b"/app/",
)
