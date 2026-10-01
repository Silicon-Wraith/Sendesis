"""Suite scoring. A rule in code, never an LLM.

Rules from `suites/security-reviewer/README.md`:
- a finding matches a label when the file is the same and the line ranges
  overlap, with 3 lines of slack either side;
- recall = matched labels / all labels, over non-clean cases;
- false positives per clean case = findings on clean cases / clean cases;
- schema validity = outputs that validate / outputs returned;
- category agreement is reported separately and is not part of the bar.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from sendesis.suite import Label

SLACK = 3
Z95 = 1.959963984540054


@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    clean: bool
    labels: tuple[Label, ...]
    findings: list[dict[str, Any]]  # empty when the output was invalid
    valid: bool  # output validated against the role's output schema
    returned: bool  # the call returned an output at all


@dataclass(frozen=True)
class Score:
    value: float
    ci_low: float
    ci_high: float
    ci_method: str
    n: int


def _norm(path: str) -> str:
    path = path.strip().replace("\\", "/")
    for prefix in ("./", "a/", "b/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
    return path


def matches(finding: dict[str, Any], label: Label) -> bool:
    loc = finding.get("location") or {}
    start = loc.get("line_start")
    if start is None or _norm(loc.get("file", "")) != _norm(label.file):
        return False
    end = loc.get("line_end") or start
    return start <= label.line_end + SLACK and end >= label.line_start - SLACK


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def bootstrap_mean_ci(values: list[float], iters: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap for a mean. Fixed seed so a receipt can be recomputed."""
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters) - 1]


def compute_metrics(outcomes: list[CaseOutcome]) -> dict[str, Score]:
    vulnerable = [o for o in outcomes if not o.clean]
    clean = [o for o in outcomes if o.clean and o.returned]
    returned = [o for o in outcomes if o.returned]
    metrics: dict[str, Score] = {}

    n_labels = sum(len(o.labels) for o in vulnerable)
    matched_labels = []
    for o in vulnerable:
        for label in o.labels:
            hit = next((f for f in o.findings if matches(f, label)), None)
            if hit is not None:
                matched_labels.append((label, hit))
    if n_labels:
        metrics["recall"] = Score(len(matched_labels) / n_labels, *wilson(len(matched_labels), n_labels), "wilson", n_labels)

    if clean:
        fps = [float(len(o.findings)) for o in clean]
        metrics["false_positives_per_clean_case"] = Score(sum(fps) / len(fps), *bootstrap_mean_ci(fps), "bootstrap", len(fps))

    if returned:
        k = sum(o.valid for o in returned)
        metrics["schema_validity"] = Score(k / len(returned), *wilson(k, len(returned)), "wilson", len(returned))

    if matched_labels:
        agree = sum(str(f.get("category", "")).upper() == label.cwe.upper() for label, f in matched_labels)
        metrics["category_agreement"] = Score(agree / len(matched_labels), *wilson(agree, len(matched_labels)), "wilson", len(matched_labels))
    return metrics


def passes(score: Score, direction: str, threshold: float) -> bool:
    """Compare the conservative end of the interval with the threshold."""
    if direction == "higher_is_better":
        return score.ci_low >= threshold
    return score.ci_high <= threshold
