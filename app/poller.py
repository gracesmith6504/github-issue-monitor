import requests
import logging

logger = logging.getLogger(__name__)

SKIP_LABELS = {
    "spike", "refactor", "architecture", "design", "rfc",
    "breaking-change", "epic",
    "state:pr-opened",
}


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

    def _was_recently_unassigned(self, repo, number, since):
        url = f"https://api.github.com/repos/{repo}/issues/{number}/timeline"
        headers = {**self.headers, "Accept": "application/vnd.github.mockingbird-preview+json"}
        while url:
            try:
                resp = requests.get(url, headers=headers, params={"per_page": 100}, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"[{repo} #{number}] Timeline check for unassign failed: {resp.status_code}")
                    return False
                for event in resp.json():
                    if event.get("event") == "unassigned":
                        created = event.get("created_at", "")
                        if created >= since:
                            return True
                url = None
                for part in resp.headers.get("Link", "").split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")
                        break
            except requests.RequestException as e:
                logger.warning(f"[{repo} #{number}] Timeline check for unassign failed: {e}")
                return False
        return False

    def _has_linked_open_pr(self, repo, number):
        url = f"https://api.github.com/repos/{repo}/issues/{number}/timeline"
        headers = {**self.headers, "Accept": "application/vnd.github.mockingbird-preview+json"}
        while url:
            try:
                resp = requests.get(url, headers=headers, params={"per_page": 100}, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"[{repo} #{number}] Timeline API returned {resp.status_code} — skipping PR check")
                    return False
                for event in resp.json():
                    if event.get("event") == "cross-referenced":
                        source = event.get("source", {})
                        src_issue = source.get("issue", {})
                        if src_issue.get("pull_request") and src_issue.get("state") == "open":
                            return True
                url = None
                for part in resp.headers.get("Link", "").split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")
                        break
            except requests.RequestException as e:
                logger.warning(f"[{repo} #{number}] Timeline check failed: {e}")
                return False
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
                label_names = {l.get("name", "").lower() for l in issue.get("labels", [])}
                matched_skip = label_names & SKIP_LABELS
                if matched_skip:
                    logger.info(f"[{repo} #{number}] Skipping — has label: {', '.join(matched_skip)}")
                    continue

                if self._has_linked_open_pr(repo, number):
                    logger.info(f"[{repo} #{number}] Skipping — has linked open PR")
                    continue

                already_notified = self._is_already_notified(number, repo_name, notify_repo)
                if already_notified:
                    if self._was_recently_unassigned(repo, number, since):
                        logger.info(f"[{repo} #{number}] Reclaimed — was assigned then unassigned")
                    else:
                        logger.debug(f"[{repo} #{number}] Already notified, skipping")
                        continue

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
            if len(new_issues) >= limit:
                logger.warning(f"[{repo}] Hit per-run cap of {limit} — additional issues may be deferred to next run")
        else:
            logger.debug(f"[{repo}] No new or reclaimed unassigned issues")

        return new_issues
