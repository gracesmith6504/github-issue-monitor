from unittest.mock import MagicMock
from app.core.assessment import assess_issue
from app.core.hints import GOOD_FIRST_ISSUE_LABELS, APPROACHABLE_LABELS


def _make_issue(labels=None, trigger=None, reclaimed_signals=None):
    issue = {
        "repo": "org/repo",
        "number": 1,
        "title": "Fix typo",
        "body": "There's a typo in README.md",
        "url": "https://github.com/org/repo/issues/1",
        "labels": labels or [],
        "comments": [],
    }
    if trigger:
        issue["trigger"] = trigger
    if reclaimed_signals:
        issue["reclaimed_signals"] = reclaimed_signals
    return issue


def _mock_llm_response(verdict="GO FOR IT", claimed=False):
    scores = {
        "JUMP ON IT": (5, 5, 5),
        "GO FOR IT": (4, 4, 4),
        "STRETCH": (3, 3, 3),
        "LONG SHOT": (2, 2, 2),
        "NOT YET": (1, 1, 1),
    }
    sp, sc, fm = scores.get(verdict, (3, 3, 3))
    return {
        "summary": "Fix a typo.",
        "fix_description": "Edit README.md.",
        "skills_needed": ["Markdown"],
        "starting_point": sp,
        "starting_point_reason": "Clear location.",
        "scope": sc,
        "scope_reason": "Small change.",
        "familiarity": fm,
        "familiarity_reason": "No codebase knowledge needed.",
        "claimed": claimed,
    }


def _make_mock_client(response=None):
    client = MagicMock()
    client.assess.return_value = response
    return client


class TestAnalyzeIssue:
    def test_returns_analysis_for_valid_issue(self):
        issue = _make_issue()
        client = _make_mock_client(_mock_llm_response("JUMP ON IT"))
        result = assess_issue(issue, client, "gpt-4o")
        assert result["verdict"] == "JUMP ON IT"

    def test_good_first_issue_label_passes_hint(self):
        issue = _make_issue(labels=["good first issue"])
        client = _make_mock_client(_mock_llm_response())
        assess_issue(issue, client, "gpt-4o")
        user_prompt = client.assess.call_args[0][1]
        assert "good first issue" in user_prompt

    def test_approachable_label_passes_hint(self):
        issue = _make_issue(labels=["documentation"])
        client = _make_mock_client(_mock_llm_response())
        assess_issue(issue, client, "gpt-4o")
        user_prompt = client.assess.call_args[0][1]
        assert "documentation" in user_prompt

    def test_reclaimed_issue_passes_hint(self):
        issue = _make_issue(trigger="reclaimed", reclaimed_signals=["unassigned"])
        client = _make_mock_client(_mock_llm_response())
        assess_issue(issue, client, "gpt-4o")
        user_prompt = client.assess.call_args[0][1]
        assert "removed" in user_prompt or "assigned" in user_prompt.lower()

    def test_returns_none_on_llm_failure(self):
        issue = _make_issue()
        client = _make_mock_client(None)
        result = assess_issue(issue, client, "gpt-4o")
        assert result is None


class TestRetry:
    def test_retries_on_transient_failure(self):
        issue = _make_issue()
        client = _make_mock_client()
        client.assess.side_effect = [
            None,
            _mock_llm_response("STRETCH"),
        ]
        result = assess_issue(issue, client, "gpt-4o")
        assert result is None

    def test_does_not_retry_json_parse_error(self):
        issue = _make_issue()
        client = _make_mock_client(None)
        result = assess_issue(issue, client, "gpt-4o")
        assert result is None
        assert client.assess.call_count == 1
