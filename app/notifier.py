import time
import requests
import logging
import jwt

logger = logging.getLogger(__name__)

VERDICT_TO_LABEL = {
    "JUMP ON IT": "jump-on-it",
    "GO FOR IT": "go-for-it",
    "STRETCH": "stretch",
    "LONG SHOT": "long-shot",
    "NOT YET": "not-yet",
}

VERDICT_EMOJI = {
    "JUMP ON IT": "🟢",
    "GO FOR IT": "🔵",
    "STRETCH": "🟡",
    "LONG SHOT": "🟠",
    "NOT YET": "🔴",
}


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


def _already_notified(issue, notify_repo, headers):
    if issue.get("trigger") == "unassigned":
        search_term = f"[RECLAIMED] [{issue['repo_name']} #{issue['number']}]"
    else:
        search_term = f"[{issue['repo_name']} #{issue['number']}]"
    url = "https://api.github.com/search/issues"
    params = {
        "q": f'repo:{notify_repo} "{search_term}" in:title is:open',
        "per_page": 1,
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200 and resp.json().get("total_count", 0) > 0:
            logger.info(f"[{issue['repo']} #{issue['number']}] Already notified, skipping")
            return True
    except requests.RequestException as e:
        logger.warning(f"Dedup check failed: {e}")

    return False


def _post_notification(issue, analysis, notify_repo, token):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }

    if _already_notified(issue, notify_repo, headers):
        return False

    verdict = analysis.get("verdict", "STRETCH")
    label = VERDICT_TO_LABEL.get(verdict, "stretch")
    emoji = VERDICT_EMOJI.get(verdict, "🟡")
    reclaimed = issue.get("trigger") == "unassigned"

    prefix = "🔄 " if reclaimed else ""
    if reclaimed:
        title = f"[RECLAIMED] [{issue['repo_name']} #{issue['number']}] {verdict}: {issue['title']}"
    else:
        title = f"[{issue['repo_name']} #{issue['number']}] {verdict}: {issue['title']}"
    if len(title) > 256:
        title = title[:253] + "..."

    reclaimed_note = (
        "\n> Previously claimed and abandoned — check the comments for context or partial work.\n"
        if reclaimed else ""
    )

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
