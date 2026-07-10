import requests
import logging
from collections import Counter

logger = logging.getLogger(__name__)


def build_profile(token):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }

    username = _get_username(headers)
    if not username:
        return None

    languages = _get_languages(username, headers)
    activity = _get_recent_activity(username, headers)

    profile = f"""## Auto-detected profile for {username}

### Languages (from public repos, ranked by usage)
{', '.join(f'{lang} ({count} repos)' for lang, count in languages) if languages else 'No public repos found'}

### Recent activity (last 30 events)
{activity if activity else 'No recent public activity found'}
"""

    logger.info(f"Built profile for {username}: {len(languages)} languages, recent activity detected")
    return profile


def _get_username(headers):
    try:
        resp = requests.get("https://api.github.com/user", headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("login")
    except requests.RequestException as e:
        logger.warning(f"Failed to get username: {e}")
    return None


def _get_languages(username, headers):
    try:
        resp = requests.get(
            f"https://api.github.com/users/{username}/repos",
            headers=headers,
            params={"sort": "updated", "per_page": 30, "type": "all"},
            timeout=10,
        )
        if resp.status_code != 200:
            return []

        lang_counter = Counter()
        for repo in resp.json():
            lang = repo.get("language")
            if lang:
                lang_counter[lang] += 1

        return lang_counter.most_common(10)
    except requests.RequestException as e:
        logger.warning(f"Failed to get repos: {e}")
        return []


def _get_recent_activity(username, headers):
    try:
        resp = requests.get(
            f"https://api.github.com/users/{username}/events",
            headers=headers,
            params={"per_page": 30},
            timeout=10,
        )
        if resp.status_code != 200:
            return ""

        events = resp.json()
        pr_repos = set()
        push_repos = set()
        issue_repos = set()
        review_repos = set()

        for event in events:
            repo_name = event.get("repo", {}).get("name", "")
            event_type = event.get("type", "")

            if event_type == "PullRequestEvent":
                pr_repos.add(repo_name)
            elif event_type == "PushEvent":
                push_repos.add(repo_name)
            elif event_type in ("IssuesEvent", "IssueCommentEvent"):
                issue_repos.add(repo_name)
            elif event_type == "PullRequestReviewEvent":
                review_repos.add(repo_name)

        lines = []
        if pr_repos:
            lines.append(f"- Opened PRs in: {', '.join(sorted(pr_repos))}")
        if push_repos:
            lines.append(f"- Pushed code to: {', '.join(sorted(push_repos))}")
        if issue_repos:
            lines.append(f"- Engaged with issues in: {', '.join(sorted(issue_repos))}")
        if review_repos:
            lines.append(f"- Reviewed PRs in: {', '.join(sorted(review_repos))}")

        return '\n'.join(lines) if lines else "No recent public activity"

    except requests.RequestException as e:
        logger.warning(f"Failed to get activity: {e}")
        return ""
