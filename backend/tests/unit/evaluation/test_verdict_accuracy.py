"""Fit-verdict evaluator behavior."""

from evaluation.evaluators.verdict_accuracy import evaluate_verdict_accuracy
from tests.unit.evaluation.support import artifacts, outputs


def test_verdict_accuracy_is_strict_and_fails_closed() -> None:
    snapshot = outputs(artifacts())
    assert evaluate_verdict_accuracy(snapshot, {"expected_verdict": "fit"}).score == 1.0
    assert evaluate_verdict_accuracy(snapshot, {"expected_verdict": "no_fit"}).score == 0.0
    assert evaluate_verdict_accuracy({}, {"expected_verdict": "fit"}).score == 0.0
