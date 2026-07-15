import logging

logger = logging.getLogger(__name__)

GOOD_FIRST_ISSUE_LABELS = {
    "good first issue",
    "good-first-issue",
    "beginner",
    "beginner-friendly",
    "starter",
    "easy",
    "newcomer",
    "first-timers-only",
}

APPROACHABLE_LABELS = {
    "documentation",
    "docs",
    "typo",
    "test",
    "tests",
    "help wanted",
    "help-wanted",
}


def build_hint(issue: dict) -> str | None:
    reclaimed = issue.get("trigger") == "reclaimed"
    labels = [label.lower() for label in issue.get("labels", [])]

    hint = None
    if reclaimed:
        signals = issue.get("reclaimed_signals", [])
        parts = []
        if any(s == "closed-pr" for s in signals):
            parts.append("A linked pull request was closed without being merged — there may be partial work or review feedback from the abandoned PR.")
        if any(s == "unassigned" for s in signals):
            parts.append("A contributor was previously assigned but removed.")
        if any(s.startswith("removed-label:") for s in signals):
            parts.append("Work-in-progress markers were removed, suggesting work was started but not completed.")
        if not parts:
            parts.append("This issue was previously claimed and abandoned.")
        parts.append("Check the comments for useful context.")
        hint = " ".join(parts)

    if any(label in GOOD_FIRST_ISSUE_LABELS for label in labels):
        logger.info(f"[{issue['repo']} #{issue['number']}] Has good-first-issue label")
        gfi = "This issue is explicitly labeled 'good first issue' by the maintainers — they consider it approachable for newcomers."
        hint = f"{hint} {gfi}" if hint else gfi
    elif not reclaimed:
        matched = [label for label in labels if label in APPROACHABLE_LABELS]
        if matched:
            hint = f"This issue is labeled '{matched[0]}' — consider whether it gives a newcomer a clear starting point."

    return hint
