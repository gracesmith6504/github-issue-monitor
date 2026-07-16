from unittest.mock import patch, MagicMock
from app.modes.polling.notifier import _post_notification, VERDICT_EMOJI, VERDICT_TO_LABEL


def _make_issue(number=1, title="Fix bug", repo="org/repo", trigger=None, reclaimed_signals=None):
    issue = {
        "number": number,
        "title": title,
        "repo": repo,
        "repo_name": repo.split("/")[-1],
        "url": f"https://github.com/{repo}/issues/{number}",
    }
    if trigger:
        issue["trigger"] = trigger
    if reclaimed_signals:
        issue["reclaimed_signals"] = reclaimed_signals
    return issue


def _make_analysis(verdict="GO FOR IT"):
    return {
        "summary": "Fix a bug.",
        "fix_description": "Edit the file.",
        "skills_needed": ["Python"],
        "verdict": verdict,
        "verdict_reason": "Clear fix.",
    }


class TestNotificationFormatting:
    def test_title_contains_repo_and_number(self):
        issue = _make_issue(number=42, repo="NVIDIA/OpenShell")
        analysis = _make_analysis()

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=201, json=lambda: {"html_url": "..."})
            _post_notification(issue, analysis, "user/alerts", "fake-token")
            payload = mock_post.call_args[1]["json"]
            assert "[NVIDIA/OpenShell #42]" in payload["title"]

    def test_title_truncation_at_256(self):
        issue = _make_issue(title="A" * 300)
        analysis = _make_analysis()

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=201, json=lambda: {"html_url": "..."})
            _post_notification(issue, analysis, "user/alerts", "fake-token")
            payload = mock_post.call_args[1]["json"]
            assert len(payload["title"]) <= 256
            assert payload["title"].endswith("...")

    def test_reclaimed_prefix_in_title(self):
        issue = _make_issue(trigger="reclaimed", reclaimed_signals=["unassigned"])
        analysis = _make_analysis()

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=201, json=lambda: {"html_url": "..."})
            _post_notification(issue, analysis, "user/alerts", "fake-token")
            payload = mock_post.call_args[1]["json"]
            assert "[RECLAIMED]" in payload["title"]

    def test_safe_url_rewriting(self):
        issue = _make_issue()
        analysis = _make_analysis()

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=201, json=lambda: {"html_url": "..."})
            _post_notification(issue, analysis, "user/alerts", "fake-token")
            payload = mock_post.call_args[1]["json"]
            assert "redirect.github.com" in payload["body"]
            assert "https://github.com/org/repo" not in payload["body"]

    def test_verdict_label_applied(self):
        for verdict, expected_label in VERDICT_TO_LABEL.items():
            issue = _make_issue()
            analysis = _make_analysis(verdict=verdict)

            with patch("requests.post") as mock_post:
                mock_post.return_value = MagicMock(status_code=201, json=lambda: {"html_url": "..."})
                _post_notification(issue, analysis, "user/alerts", "fake-token")
                payload = mock_post.call_args[1]["json"]
                assert expected_label in payload["labels"]

    def test_verdict_emoji_in_body(self):
        issue = _make_issue()
        analysis = _make_analysis(verdict="JUMP ON IT")

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=201, json=lambda: {"html_url": "..."})
            _post_notification(issue, analysis, "user/alerts", "fake-token")
            payload = mock_post.call_args[1]["json"]
            assert VERDICT_EMOJI["JUMP ON IT"] in payload["body"]
