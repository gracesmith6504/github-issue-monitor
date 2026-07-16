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


def format_scores(analysis: dict, prefix: str = "") -> str:
    lines = []
    for axis in ("starting_point", "scope", "familiarity"):
        score = analysis.get(axis, 0)
        reason = analysis.get(f"{axis}_reason", "")
        label = AXIS_LABELS[axis]
        sep = f" — {reason}" if reason else ""
        lines.append(f"{prefix}{label}: {score}/5{sep}")
    return "\n".join(lines)
