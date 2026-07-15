import logging

import requests

from app.core.verdict import VERDICT_EMOJI

logger = logging.getLogger(__name__)

GOOD_FIRST_ISSUE_LABEL = "good first issue"
GOOD_FIRST_ISSUE_COLOR = "7057ff"


def _headers(token):
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def ensure_label(repo, token, label_name=None, label_color=None):
    name = label_name or GOOD_FIRST_ISSUE_LABEL
    color = label_color or GOOD_FIRST_ISSUE_COLOR
    url = f"https://api.github.com/repos/{repo}/labels/{name}"
    resp = requests.get(url, headers=_headers(token), timeout=10)
    if resp.status_code == 404:
        requests.post(
            f"https://api.github.com/repos/{repo}/labels",
            headers=_headers(token),
            json={"name": name, "color": color},
            timeout=10,
        )
        logger.info(f"Created '{name}' label on {repo}")


def add_label(repo, issue_number, token, label_name=None):
    name = label_name or GOOD_FIRST_ISSUE_LABEL
    ensure_label(repo, token, label_name=name)

    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels"
    resp = requests.post(
        url, headers=_headers(token), json={"labels": [name]}, timeout=10,
    )

    if resp.status_code in (200, 201):
        logger.info(f"Added '{name}' to {repo}#{issue_number}")
        return True

    logger.warning(f"Failed to add label: {resp.status_code} {resp.text[:200]}")
    return False


def post_comment(repo, issue_number, analysis, token):
    verdict = analysis.get("verdict", "")
    emoji = VERDICT_EMOJI.get(verdict, "")
    summary = analysis.get("summary", "")
    fix_description = analysis.get("fix_description", "")
    skills = analysis.get("skills_needed", [])
    reason = analysis.get("verdict_reason", "")

    skills_str = ", ".join(skills) if skills else "None identified"

    body = (
        f"### {emoji} Newcomer Assessment: **{verdict}**\n\n"
        f"**Summary:** {summary}\n\n"
        f"**What to fix:** {fix_description}\n\n"
        f"**Skills needed:** {skills_str}\n\n"
        f"**Why this verdict:** {reason}\n\n"
        f"---\n"
        f"*Assessed automatically by [github-issue-monitor](https://github.com/gracesmith6504/github-issue-monitor)*"
    )

    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    resp = requests.post(
        url, headers=_headers(token), json={"body": body}, timeout=10,
    )

    if resp.status_code in (200, 201):
        logger.info(f"Posted assessment comment on {repo}#{issue_number}")
        return True

    logger.warning(f"Failed to post comment: {resp.status_code} {resp.text[:200]}")
    return False
