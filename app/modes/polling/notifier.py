import time
import requests
import logging
import jwt

from app.core.verdict import VERDICT_TO_LABEL, VERDICT_EMOJI

logger = logging.getLogger(__name__)


def _get_app_token(app_id, private_key, installation_id):
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + (10 * 60),
        "iss": app_id,
    }
    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")

    headers = {
        "Authorization": f"Bearer {encoded_jwt}",
        "Accept": "application/vnd.github+json",
    }
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    resp = requests.post(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()["token"]


def _post_notification(issue, analysis, notify_repo, token):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }

    verdict = analysis.get("verdict", "STRETCH")
    label = VERDICT_TO_LABEL.get(verdict, "stretch")
    emoji = VERDICT_EMOJI.get(verdict, "🟡")
    reclaimed = issue.get("trigger") == "reclaimed"

    prefix = "🔄 " if reclaimed else ""
    if reclaimed:
        title = f"[RECLAIMED] [{issue['repo']} #{issue['number']}] {emoji} {verdict}: {issue['title']}"
    else:
        title = f"[{issue['repo']} #{issue['number']}] {emoji} {verdict}: {issue['title']}"
    if len(title) > 256:
        title = title[:253] + "..."

    reclaimed_note = ""
    if reclaimed:
        signals = issue.get("reclaimed_signals", [])
        details = []
        if any(s == "closed-pr" for s in signals):
            details.append("A linked PR was closed without being merged.")
        if any(s == "unassigned" for s in signals):
            details.append("A contributor was assigned then removed.")
        if any(s.startswith("removed-label:") for s in signals):
            details.append("Work-in-progress markers were removed.")
        note = " ".join(details) if details else "Previously claimed and abandoned."
        reclaimed_note = f"\n> {note} Check the comments for context or partial work.\n"

    skills = ', '.join(analysis.get('skills_needed', ['unknown']))

    safe_url = issue['url'].replace('https://github.com/', 'https://redirect.github.com/')
    body = f"""{prefix}{emoji} **{verdict}** — [{issue['repo']} #{issue['number']}]({safe_url})

**Skills:** {skills}
{reclaimed_note}
---

{analysis.get('summary', 'No summary available.')}

**What to fix:** {analysis.get('fix_description', 'No fix description available.')}

**Why this verdict:** {analysis.get('verdict_reason', 'No reason provided.')}

---
*[github-issue-monitor](https://github.com/{notify_repo})*"""

    url = f"https://api.github.com/repos/{notify_repo}/issues"
    payload = {"title": title, "body": body, "labels": [label]}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 201:
            logger.info(f"Notification created: {resp.json().get('html_url')}")
            return True
        else:
            logger.error(f"Failed to create notification: {resp.status_code} {resp.text[:200]}")
            return False
    except requests.RequestException as e:
        logger.error(f"Failed to create notification: {e}")
        return False


def notify(issue, analysis, notify_repo, app_id, private_key, installation_id):
    token = _get_app_token(app_id, private_key, installation_id)
    return _post_notification(issue, analysis, notify_repo, token)


def notify_simple(issue, analysis, notify_repo, token):
    return _post_notification(issue, analysis, notify_repo, token)
