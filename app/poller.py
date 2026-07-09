import requests
import logging

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, token):
        self.token = token
        self.etags = {}
        self.seen_issue_ids = set()
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

    def poll(self, repo):
        url = f"https://api.github.com/repos/{repo}/events"
        headers = dict(self.headers)

        if repo in self.etags:
            headers["If-None-Match"] = self.etags[repo]

        try:
            resp = requests.get(url, headers=headers, timeout=10)
        except requests.RequestException as e:
            logger.error(f"[{repo}] Request failed: {e}")
            return []

        if resp.status_code == 304:
            logger.debug(f"[{repo}] No changes (304)")
            return []

        if resp.status_code != 200:
            logger.warning(f"[{repo}] Got status {resp.status_code}: {resp.text[:200]}")
            return []

        if "ETag" in resp.headers:
            self.etags[repo] = resp.headers["ETag"]

        events = resp.json()
        new_issues = []

        for event in events:
            if event.get("type") != "IssuesEvent":
                continue

            payload = event.get("payload", {})
            if payload.get("action") != "opened":
                continue

            issue = payload.get("issue", {})
            issue_id = issue.get("id")

            if issue_id in self.seen_issue_ids:
                continue

            if issue.get("assignees"):
                continue

            self.seen_issue_ids.add(issue_id)
            repo_name = repo.split("/")[-1]

            new_issues.append({
                "id": issue_id,
                "number": issue.get("number"),
                "title": issue.get("title"),
                "body": issue.get("body", ""),
                "url": issue.get("html_url"),
                "labels": [l.get("name") for l in issue.get("labels", [])],
                "repo": repo,
                "repo_name": repo_name,
            })

        if new_issues:
            logger.info(f"[{repo}] Found {len(new_issues)} new unassigned issue(s)")
        else:
            logger.debug(f"[{repo}] No new unassigned issues")

        return new_issues
