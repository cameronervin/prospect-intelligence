"""Experiment package boundaries and CLI compatibility."""

import importlib.util
import subprocess
import sys


def test_experiment_modules_live_under_hosted_and_offline_packages() -> None:
    nested_modules = (
        "evaluation.experiments.offline.runner",
        "evaluation.experiments.offline.report",
        "evaluation.experiments.offline.results",
        "evaluation.experiments.hosted.runner",
        "evaluation.experiments.hosted.dataset",
        "evaluation.experiments.hosted.delivery",
        "evaluation.experiments.hosted.persistence",
        "evaluation.experiments.hosted.report",
        "evaluation.experiments.hosted.results",
        "evaluation.experiments.hosted.runtime",
        "evaluation.experiments.hosted.plan",
    )
    removed_flat_modules = (
        "evaluation.experiments.offline_report",
        "evaluation.experiments.offline_results",
        "evaluation.experiments.hosted_dataset",
        "evaluation.experiments.hosted_delivery",
        "evaluation.experiments.hosted_persistence",
        "evaluation.experiments.hosted_report",
        "evaluation.experiments.hosted_results",
        "evaluation.experiments.hosted_runtime",
        "evaluation.experiments.plan",
    )

    assert all(importlib.util.find_spec(name) is not None for name in nested_modules)
    assert all(importlib.util.find_spec(name) is None for name in removed_flat_modules)


def test_importing_offline_package_does_not_import_hosted_package() -> None:
    result = subprocess.run(
        (
            sys.executable,
            "-c",
            "import sys; import evaluation.experiments.offline; "
            "assert 'evaluation.experiments.hosted' not in sys.modules; "
            "assert 'evaluation.targets.prospect_live' not in sys.modules",
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
