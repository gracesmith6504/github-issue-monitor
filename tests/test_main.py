from unittest.mock import patch, MagicMock
from app.modes.polling.main import run_once


def _make_config(**overrides):
    config = {
        "watch_repos": ["org/repo"],
        "last_checked": "2024-01-01T00:00:00Z",
        "notify_repo": "user/alerts",
        "notify_token": "fake-token",
        "monitor_token": "fake-token",
        "llm_token": "fake-token",
        "llm_model": "gpt-4o",
        "min_verdict": "STRETCH",
        "max_issues_per_repo": 5,
        "analysis_delay": 0,
    }
    config.update(overrides)
    return config


class TestVerdictThreshold:
    def test_skips_below_threshold(self):
        config = _make_config(min_verdict="GO FOR IT")
        issues = [{"repo": "org/repo", "number": 1, "title": "Test"}]
        analysis = {"verdict": "STRETCH", "claimed": False}

        poller = MagicMock()
        poller.poll.return_value = issues
        llm_client = MagicMock()

        with patch("app.modes.polling.main.assess_issue", return_value=analysis), \
             patch("app.modes.polling.main.notifier") as mock_notifier:
            run_once(config, poller, llm_client)
            mock_notifier.notify_simple.assert_not_called()

    def test_includes_at_threshold(self):
        config = _make_config(min_verdict="STRETCH")
        issues = [{"repo": "org/repo", "number": 1, "title": "Test"}]
        analysis = {"verdict": "STRETCH", "claimed": False}

        poller = MagicMock()
        poller.poll.return_value = issues
        llm_client = MagicMock()

        with patch("app.modes.polling.main.assess_issue", return_value=analysis), \
             patch("app.modes.polling.main.notifier") as mock_notifier:
            run_once(config, poller, llm_client)
            mock_notifier.notify_simple.assert_called_once()

    def test_includes_above_threshold(self):
        config = _make_config(min_verdict="STRETCH")
        issues = [{"repo": "org/repo", "number": 1, "title": "Test"}]
        analysis = {"verdict": "JUMP ON IT", "claimed": False}

        poller = MagicMock()
        poller.poll.return_value = issues
        llm_client = MagicMock()

        with patch("app.modes.polling.main.assess_issue", return_value=analysis), \
             patch("app.modes.polling.main.notifier") as mock_notifier:
            run_once(config, poller, llm_client)
            mock_notifier.notify_simple.assert_called_once()

    def test_skips_claimed_issues(self):
        config = _make_config()
        issues = [{"repo": "org/repo", "number": 1, "title": "Test"}]
        analysis = {"verdict": "JUMP ON IT", "claimed": True}

        poller = MagicMock()
        poller.poll.return_value = issues
        llm_client = MagicMock()

        with patch("app.modes.polling.main.assess_issue", return_value=analysis), \
             patch("app.modes.polling.main.notifier") as mock_notifier:
            run_once(config, poller, llm_client)
            mock_notifier.notify_simple.assert_not_called()

    def test_skips_failed_analysis(self):
        config = _make_config()
        issues = [{"repo": "org/repo", "number": 1, "title": "Test"}]

        poller = MagicMock()
        poller.poll.return_value = issues
        llm_client = MagicMock()

        with patch("app.modes.polling.main.assess_issue", return_value=None), \
             patch("app.modes.polling.main.notifier") as mock_notifier:
            run_once(config, poller, llm_client)
            mock_notifier.notify_simple.assert_not_called()

    def test_passes_limit_to_poller(self):
        config = _make_config(max_issues_per_repo=15)
        poller = MagicMock()
        poller.poll.return_value = []
        llm_client = MagicMock()

        run_once(config, poller, llm_client)
        poller.poll.assert_called_once_with(
            "org/repo", "2024-01-01T00:00:00Z", "user/alerts", limit=15
        )

    def test_uses_analysis_delay(self):
        config = _make_config(analysis_delay=2)
        issues = [
            {"repo": "org/repo", "number": 1, "title": "A"},
            {"repo": "org/repo", "number": 2, "title": "B"},
        ]
        analysis = {"verdict": "JUMP ON IT", "claimed": False}
        poller = MagicMock()
        poller.poll.return_value = issues
        llm_client = MagicMock()

        with patch("app.modes.polling.main.assess_issue", return_value=analysis), \
             patch("app.modes.polling.main.notifier"), \
             patch("app.modes.polling.main.time") as mock_time:
            run_once(config, poller, llm_client)
            mock_time.sleep.assert_called_once_with(2)
