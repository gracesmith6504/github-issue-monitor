from unittest.mock import patch, MagicMock
from app.modes.polling.poller import Poller, SKIP_LABELS


def _make_issue(number=1, title="Fix bug", assignees=None, labels=None,
                pull_request=None, body="", html_url="https://github.com/org/repo/issues/1"):
    issue = {
        "id": number,
        "number": number,
        "title": title,
        "body": body,
        "html_url": html_url,
        "labels": [{"name": l} for l in (labels or [])],
        "assignees": assignees or [],
    }
    if pull_request is not None:
        issue["pull_request"] = pull_request
    return issue


def _mock_responses(issues_json, timeline_json=None, search_json=None, comments_json=None):
    def side_effect(url, **kwargs):
        resp = MagicMock()
        resp.headers = {}

        if "/timeline" in url:
            resp.status_code = 200
            resp.json.return_value = timeline_json or []
        elif "/search/issues" in url:
            resp.status_code = 200
            resp.json.return_value = search_json or {"total_count": 0}
        elif "/comments" in url:
            resp.status_code = 200
            resp.json.return_value = comments_json or []
        elif "/issues" not in url and "/search" not in url:
            resp.status_code = 200
            resp.json.return_value = {"language": "Python"}
        else:
            resp.status_code = 200
            resp.json.return_value = issues_json
        return resp
    return side_effect


class TestPollerFiltering:
    def test_skips_pull_requests(self):
        issues = [_make_issue(pull_request={"url": "..."})]
        poller = Poller("fake-token")
        with patch("requests.get", side_effect=_mock_responses(issues)):
            result = poller.poll("org/repo", "2024-01-01T00:00:00Z", "user/alerts")
        assert len(result) == 0

    def test_skips_assigned_issues(self):
        issues = [_make_issue(assignees=[{"login": "someone"}])]
        poller = Poller("fake-token")
        with patch("requests.get", side_effect=_mock_responses(issues)):
            result = poller.poll("org/repo", "2024-01-01T00:00:00Z", "user/alerts")
        assert len(result) == 0

    def test_skips_issues_with_skip_labels(self):
        for label in ["spike", "refactor", "epic", "rfc"]:
            issues = [_make_issue(labels=[label])]
            poller = Poller("fake-token")
            with patch("requests.get", side_effect=_mock_responses(issues)):
                result = poller.poll("org/repo", "2024-01-01T00:00:00Z", "user/alerts")
            assert len(result) == 0, f"Should skip label '{label}'"

    def test_includes_valid_issue(self):
        issues = [_make_issue(number=42, title="Add feature")]
        poller = Poller("fake-token")
        with patch("requests.get", side_effect=_mock_responses(issues)):
            result = poller.poll("org/repo", "2024-01-01T00:00:00Z", "user/alerts")
        assert len(result) == 1
        assert result[0]["number"] == 42

    def test_skips_issue_with_open_pr(self):
        issues = [_make_issue()]
        timeline = [
            {
                "event": "cross-referenced",
                "source": {
                    "issue": {
                        "state": "open",
                        "pull_request": {"url": "..."},
                    }
                },
            }
        ]
        poller = Poller("fake-token")
        with patch("requests.get", side_effect=_mock_responses(issues, timeline_json=timeline)):
            result = poller.poll("org/repo", "2024-01-01T00:00:00Z", "user/alerts")
        assert len(result) == 0

    def test_skips_already_notified(self):
        issues = [_make_issue()]
        search = {"total_count": 1}
        poller = Poller("fake-token")
        with patch("requests.get", side_effect=_mock_responses(issues, search_json=search)):
            result = poller.poll("org/repo", "2024-01-01T00:00:00Z", "user/alerts")
        assert len(result) == 0

    def test_respects_limit(self):
        issues = [_make_issue(number=i) for i in range(10)]
        poller = Poller("fake-token")
        with patch("requests.get", side_effect=_mock_responses(issues)):
            result = poller.poll("org/repo", "2024-01-01T00:00:00Z", "user/alerts", limit=3)
        assert len(result) == 3


class TestReclaimed:
    def test_detects_unassigned_reclaim(self):
        issues = [_make_issue()]
        timeline = [{"event": "unassigned", "created_at": "2024-06-01T00:00:00Z"}]
        search = {"total_count": 1}
        poller = Poller("fake-token")
        with patch("requests.get", side_effect=_mock_responses(issues, timeline_json=timeline, search_json=search)):
            result = poller.poll("org/repo", "2024-01-01T00:00:00Z", "user/alerts")
        assert len(result) == 1
        assert result[0]["trigger"] == "reclaimed"
        assert "unassigned" in result[0]["reclaimed_signals"]
