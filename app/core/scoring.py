DEFAULT_THRESHOLDS = {
    "JUMP ON IT": 13,
    "GO FOR IT": 10,
    "STRETCH": 7,
    "LONG SHOT": 5,
}

AXIS_LABELS = {
    "starting_point": "Starting Point",
    "scope": "Scope",
    "familiarity": "Familiarity",
}


def clamp_score(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 3
    return max(1, min(5, n))


def compute_verdict(starting_point: int, scope: int, familiarity: int,
                    thresholds: dict | None = None) -> tuple[str, int]:
    t = thresholds or DEFAULT_THRESHOLDS
    total = starting_point + scope + familiarity
    for verdict in ("JUMP ON IT", "GO FOR IT", "STRETCH", "LONG SHOT"):
        if total >= t[verdict]:
            return verdict, total
    return "NOT YET", total


def build_verdict_reason(analysis: dict) -> str:
    parts = []
    for axis in ("starting_point", "scope", "familiarity"):
        reason = analysis.get(f"{axis}_reason", "")
        score = analysis.get(axis, 0)
        if reason:
            parts.append(f"{AXIS_LABELS[axis]} ({score}/5): {reason}")
    return "; ".join(parts)


import re

_SCORE_RE = re.compile(r"SP=(\d)\s+Scope=(\d)\s+Fam=(\d)")


def parse_example_scores(scores_str: str) -> tuple[int, int, int] | None:
    m = _SCORE_RE.search(scores_str)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def lookup_example(issue_number: int, profile) -> dict | None:
    if not profile or not profile.examples:
        return None
    for ex in profile.examples:
        if ex.get("number") == issue_number:
            scores_str = ex.get("scores", "")
            parsed = parse_example_scores(scores_str)
            if parsed:
                sp, sc, fm = parsed
                return {
                    "starting_point": sp,
                    "scope": sc,
                    "familiarity": fm,
                    "starting_point_reason": f"Calibration example (#{issue_number})",
                    "scope_reason": f"Calibration example (#{issue_number})",
                    "familiarity_reason": f"Calibration example (#{issue_number})",
                    "reason": ex.get("reason", ""),
                }
    return None


def format_scores(analysis: dict, prefix: str = "") -> str:
    lines = []
    for axis in ("starting_point", "scope", "familiarity"):
        score = analysis.get(axis, 0)
        reason = analysis.get(f"{axis}_reason", "")
        label = AXIS_LABELS[axis]
        sep = f" — {reason}" if reason else ""
        lines.append(f"{prefix}{label}: {score}/5{sep}")
    return "\n".join(lines)
