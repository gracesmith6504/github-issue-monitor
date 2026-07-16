from unittest.mock import patch, MagicMock
import json
from app.analyzer import analyze_issue
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
    analysis = {
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
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = json.dumps(analysis)
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_client.return_value.chat.completions.create.return_value.choices = [mock_choice]
    return mock_client


class TestAnalyzeIssue:
    def test_returns_analysis_for_valid_issue(self):
        issue = _make_issue()
        with patch("app.core.llm.OpenAI", _mock_llm_response("JUMP ON IT")):
            result = analyze_issue(issue, "fake-token", "gpt-4o")
        assert result["verdict"] == "JUMP ON IT"

    def test_good_first_issue_label_passes_hint(self):
        issue = _make_issue(labels=["good first issue"])
        with patch("app.core.llm.OpenAI", _mock_llm_response()) as mock_openai:
            analyze_issue(issue, "fake-token", "gpt-4o")
            call_args = mock_openai.return_value.chat.completions.create.call_args
            user_msg = call_args[1]["messages"][1]["content"]
            assert "good first issue" in user_msg

    def test_approachable_label_passes_hint(self):
        issue = _make_issue(labels=["documentation"])
        with patch("app.core.llm.OpenAI", _mock_llm_response()) as mock_openai:
            analyze_issue(issue, "fake-token", "gpt-4o")
            call_args = mock_openai.return_value.chat.completions.create.call_args
            user_msg = call_args[1]["messages"][1]["content"]
            assert "documentation" in user_msg

    def test_reclaimed_issue_passes_hint(self):
        issue = _make_issue(trigger="reclaimed", reclaimed_signals=["unassigned"])
        with patch("app.core.llm.OpenAI", _mock_llm_response()) as mock_openai:
            analyze_issue(issue, "fake-token", "gpt-4o")
            call_args = mock_openai.return_value.chat.completions.create.call_args
            user_msg = call_args[1]["messages"][1]["content"]
            assert "removed" in user_msg or "assigned" in user_msg.lower()

    def test_returns_none_on_llm_failure(self):
        issue = _make_issue()
        mock_client = MagicMock()
        mock_client.return_value.chat.completions.create.side_effect = Exception("API down")
        with patch("app.core.llm.OpenAI", mock_client), patch("time.sleep"):
            result = analyze_issue(issue, "fake-token", "gpt-4o")
        assert result is None


class TestRetry:
    def test_retries_on_transient_failure(self):
        issue = _make_issue()
        mock_client = MagicMock()
        good_response = MagicMock()
        good_response.choices = [MagicMock()]
        good_response.choices[0].message.content = json.dumps({
            "summary": "s", "fix_description": "f", "skills_needed": [],
            "starting_point": 3, "starting_point_reason": "r",
            "scope": 3, "scope_reason": "r",
            "familiarity": 3, "familiarity_reason": "r",
            "claimed": False,
        })
        mock_client.return_value.chat.completions.create.side_effect = [
            Exception("timeout"),
            good_response,
        ]
        with patch("app.core.llm.OpenAI", mock_client), patch("time.sleep"):
            result = analyze_issue(issue, "fake-token", "gpt-4o")
        assert result is not None
        assert result["verdict"] == "STRETCH"

    def test_does_not_retry_json_parse_error(self):
        issue = _make_issue()
        mock_client = MagicMock()
        bad_response = MagicMock()
        bad_response.choices = [MagicMock()]
        bad_response.choices[0].message.content = "not json at all"
        mock_client.return_value.chat.completions.create.return_value = bad_response
        with patch("app.core.llm.OpenAI", mock_client):
            result = analyze_issue(issue, "fake-token", "gpt-4o")
        assert result is None
        assert mock_client.return_value.chat.completions.create.call_count == 1
