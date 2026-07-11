import requests
import logging

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, token):
        self.token = token
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

    def _is_already_notified(self, number, repo_name, notify_repo):
        search_term = f"[{repo_name} #{number}]"
        url = "https://api.github.com/search/issues"
        params = {
            "q": f'repo:{notify_repo} "{search_term}" in:title is:open',
            "per_page": 1,
        }
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            if resp.status_code == 200 and resp.json().get("total_count", 0) > 0:
                return True
        except requests.RequestException as e:
            logger.warning(f"Dedup check failed: {e}")
        return False

    def poll(self, repo, since, notify_repo, limit=5):
        url = f"https://api.github.com/repos/{repo}/issues"
        params = {
            "state": "open",
            "since": since,
            "sort": "updated",
            "direction": "asc",
            "per_page": 100,
        }
        repo_name = repo.split("/")[-1]
        new_issues = []

        while url and len(new_issues) < limit:
            try:
                resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            except requests.RequestException as e:
                logger.error(f"[{repo}] Request failed: {e}")
                break

            if resp.status_code != 200:
                logger.warning(f"[{repo}] Got status {resp.status_code}: {resp.text[:200]}")
                break

            for issue in resp.json():
                if len(new_issues) >= limit:
                    break
                if "pull_request" in issue:
                    continue
                if issue.get("assignees"):
                    continue

                number = issue.get("number")
                already_notified = self._is_already_notified(number, repo_name, notify_repo)

                issue_dict = {
                    "id": issue.get("id"),
                    "number": number,
                    "title": issue.get("title"),
                    "body": issue.get("body", ""),
                    "url": issue.get("html_url"),
                    "labels": [l.get("name") for l in issue.get("labels", [])],
                    "repo": repo,
                    "repo_name": repo_name,
                }
                if already_notified:
                    issue_dict["trigger"] = "unassigned"

                new_issues.append(issue_dict)

            # Follow pagination
            next_url = None
            for part in resp.headers.get("Link", "").split(","):
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip().strip("<>")
                    break
            url = next_url
            params = {}

        if new_issues:
            logger.info(f"[{repo}] Found {len(new_issues)} new/reclaimed unassigned issue(s)")
        else:
            logger.debug(f"[{repo}] No new or reclaimed unassigned issues")

        return new_issues
