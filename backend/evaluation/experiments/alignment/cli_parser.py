"""Argument parser for the evaluator-alignment command line interface."""

from __future__ import annotations

import argparse

from evaluation.experiments.alignment.reference.labels import LABEL_SET_VERSION


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Explicit local and live commands for CAM-41/CAM-50 evaluator alignment."
    )
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("self-test", help="run the credential-free 420-attempt matrix")

    prepare = subcommands.add_parser(
        "prepare-labels", help="publish blind labeling runs and queues"
    )
    prepare.add_argument("--live", action="store_true", help="authorize LangSmith writes")

    adjudicate = subcommands.add_parser(
        "prepare-adjudication",
        help="freeze the primary pass and route flagged cases to second-pass queues",
    )
    adjudicate.add_argument("--live", action="store_true", help="authorize LangSmith writes")

    composite = subcommands.add_parser(
        "publish-composite", help="compose verified alignment sources into one holdout prerequisite"
    )
    composite.add_argument("--live", action="store_true", help="authorize one LangSmith write")
    composite.add_argument("--authorize-1-manifest", action="store_true")
    composite.add_argument("--categorical-project", required=True)
    composite.add_argument("--score-project", action="append", required=True)
    composite.add_argument(
        "--label-set", default=LABEL_SET_VERSION, help="approved LangSmith label-set version"
    )

    calibrate = subcommands.add_parser(
        "calibrate", help="run real judges against the approved human label set"
    )
    calibrate.add_argument("--live", action="store_true", help="authorize provider calls")
    calibrate.add_argument(
        "--phase",
        choices=("alignment", "holdout"),
        default="alignment",
        help="run the five-case-per-question diagnostic or frozen holdout phase",
    )
    calibrate.add_argument(
        "--confirm-rubric-frozen",
        action="store_true",
        help="required before the untouched holdout phase",
    )
    calibrate.add_argument(
        "--label-set", default=LABEL_SET_VERSION, help="approved LangSmith label-set version"
    )
    calibrate.add_argument(
        "--authorize-420-calls",
        action="store_true",
        help="acknowledge the disclosed logical-attempt and retry request envelope",
    )
    calibrate.add_argument(
        "--score-revision-only",
        action="store_true",
        help="rerun only the two ordered-score alignment questions after the bounded revision",
    )
    calibrate.add_argument(
        "--authorize-60-calls",
        action="store_true",
        help="authorize the targeted ordered-score alignment rerun",
    )
    calibrate.add_argument(
        "--local-only",
        action="store_true",
        help="deliberately skip alignment trace publication; never completion evidence",
    )
    calibrate.add_argument(
        "--untraced-reason",
        help="required explanation for the incomplete local-only exception",
    )
    calibrate.add_argument(
        "--composite-project",
        help="read-back-verified composite alignment project required for holdout",
    )
    return result


__all__ = ["parser"]
