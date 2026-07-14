import requests
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

SKIP_LABELS = {
    "spike", "refactor", "architecture", "design", "rfc",
    "breaking-change", "epic",
    "state:pr-opened",
    "state:in-progress",
}

RECLAIMED_LABELS = {"state:in-progress", "state:pr-opened"}


class Poller:
    def __init__(self, token):
        self.token = token
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

    def _is_already_notified(self, number, repo, notify_repo):
        repo_name = repo.split("/")[-1]
        search_term = f"[{repo_name} #{number}]"
        url = "https://api.github.com/search/issues"
        params = {
            "q": f'repo:{notify_repo} "{search_term}" in:title',
            "per_page": 1,
        }
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            if resp.status_code == 200 and resp.json().get("total_count", 0) > 0:
                return True
        except requests.RequestException as e:
            logger.warning(f"Dedup check failed: {e}")
        return False

    def _fetch_recent_comments(self, repo, number, limit=10):
        url = f"https://api.github.com/repos/{repo}/issues/{number}/comments"
        params = {"per_page": limit, "direction": "desc"}
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            if resp.status_code != 200:
                return []
            return [
                {"user": c.get("user", {}).get("login", "unknown"),
                 "body": (c.get("body") or "")[:500],
                 "created_at": c.get("created_at", "")}
                for c in resp.json()
            ]
        except requests.RequestException:
            return []

    def _scan_timeline(self, repo, number, since):
        result = {"has_open_pr": False, "has_linked_commit": False, "has_fork_activity": False, "abandoned_signals": []}
        url = f"https://api.github.com/repos/{repo}/issues/{number}/timeline"
        headers = {**self.headers, "Accept": "application/vnd.github.mockingbird-preview+json"}
        while url:
            try:
                resp = requests.get(url, headers=headers, params={"per_page": 100}, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"[{repo} #{number}] Timeline API returned {resp.status_code}")
                    return result
                for event in resp.json():
                    event_type = event.get("event")

                    if event_type == "cross-referenced":
                        src_issue = event.get("source", {}).get("issue", {})
                        pr = src_issue.get("pull_request")
                        if pr:
                            if src_issue.get("state") == "open":
                                result["has_open_pr"] = True
                            elif src_issue.get("state") == "closed" and not pr.get("merged_at"):
                                if src_issue.get("updated_at", "") >= since:
                                    result["abandoned_signals"].append("closed-pr")
                        else:
                            src_repo = event.get("source", {}).get("issue", {}).get("repository", {}).get("full_name", "")
                            if src_repo and src_repo != repo and src_repo.split("/")[-1] == repo.split("/")[-1]:
                                created = event.get("created_at", "")
                                cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                                if created >= cutoff:
                                    result["has_fork_activity"] = True

                    elif event_type == "committed":
                        result["has_linked_commit"] = True

                    elif event_type == "unassigned":
                        if event.get("created_at", "") >= since:
                            result["abandoned_signals"].append("unassigned")

                    elif event_type == "unlabeled":
                        label_name = event.get("label", {}).get("name", "")
                        if label_name in RECLAIMED_LABELS and event.get("created_at", "") >= since:
                            result["abandoned_signals"].append(f"removed-label:{label_name}")

                url = None
                for part in resp.headers.get("Link", "").split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")
                        break
            except requests.RequestException as e:
                logger.warning(f"[{repo} #{number}] Timeline check failed: {e}")
                return result
        return result

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
        repo_language = None
        try:
            repo_resp = requests.get(f"https://api.github.com/repos/{repo}", headers=self.headers, timeout=10)
            if repo_resp.status_code == 200:
                repo_language = repo_resp.json().get("language")
        except requests.RequestException:
            pass
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
                label_names = {l.get("name", "").lower() for l in issue.get("labels", [])}
                matched_skip = label_names & SKIP_LABELS
                if matched_skip:
                    logger.info(f"[{repo} #{number}] Skipping — has label: {', '.join(matched_skip)}")
                    continue

                timeline = self._scan_timeline(repo, number, since)

                if timeline["has_open_pr"]:
                    logger.info(f"[{repo} #{number}] Skipping — has linked open PR")
                    continue

                if timeline["has_fork_activity"]:
                    logger.info(f"[{repo} #{number}] Skipping — referenced from a fork (likely in progress)")
                    continue

                if timeline["has_linked_commit"]:
                    logger.info(f"[{repo} #{number}] Skipping — has linked commit")
                    continue

                already_notified = self._is_already_notified(number, repo, notify_repo)
                if already_notified:
                    if timeline["abandoned_signals"]:
                        logger.info(f"[{repo} #{number}] Reclaimed — signals: {', '.join(timeline['abandoned_signals'])}")
                    else:
                        logger.debug(f"[{repo} #{number}] Already notified, skipping")
                        continue

                comments = self._fetch_recent_comments(repo, number)

                issue_dict = {
                    "id": issue.get("id"),
                    "number": number,
                    "title": issue.get("title"),
                    "body": issue.get("body", ""),
                    "url": issue.get("html_url"),
                    "labels": [l.get("name") for l in issue.get("labels", [])],
                    "repo": repo,
                    "repo_name": repo_name,
                    "repo_language": repo_language,
                    "comments": comments,
                }
                if already_notified:
                    issue_dict["trigger"] = "reclaimed"
                    issue_dict["reclaimed_signals"] = timeline["abandoned_signals"]

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
            if len(new_issues) >= limit:
                logger.warning(f"[{repo}] Hit per-run cap of {limit} — additional issues may be deferred to next run")
        else:
            logger.debug(f"[{repo}] No new or reclaimed unassigned issues")

        return new_issues
