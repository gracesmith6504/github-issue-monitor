import json
import os
from unittest.mock import patch, MagicMock

import yaml

from app.core.profiles import RepoProfile
from app.modes.action.main import build_issue_dict, fetch_issue_from_api, main
from app.modes.action.labeler import ensure_label, add_label, post_comment, GOOD_FIRST_ISSUE_LABEL


def _sample_event(body="Fix the typo in README", labels=None, language="Python"):
    return {
        "action": "opened",
        "issue": {
            "number": 42,
            "title": "Fix typo in README",
            "body": body,
            "html_url": "https://github.com/org/repo/issues/42",
            "labels": [{"name": l} for l in (labels or [])],
        },
        "repository": {
            "full_name": "org/repo",
            "language": language,
        },
    }


def _write_event(tmp_path, event=None):
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event or _sample_event()))
    return str(path)


class TestBuildIssueDict:
    def test_extracts_all_fields(self):
        event = _sample_event(labels=["bug", "help wanted"])
        result = build_issue_dict(event)
        assert result["repo"] == "org/repo"
        assert result["number"] == 42
        assert result["title"] == "Fix typo in README"
        assert result["body"] == "Fix the typo in README"
        assert result["url"] == "https://github.com/org/repo/issues/42"
        assert result["labels"] == ["bug", "help wanted"]
        assert result["comments"] == []
        assert result["repo_language"] == "Python"

    def test_null_body_defaults_to_empty(self):
        event = _sample_event(body=None)
        result = build_issue_dict(event)
        assert result["body"] == ""

    def test_no_labels(self):
        event = _sample_event()
        event["issue"]["labels"] = []
        result = build_issue_dict(event)
        assert result["labels"] == []

    def test_no_language(self):
        event = _sample_event(language=None)
        result = build_issue_dict(event)
        assert result["repo_language"] is None


class TestLabeler:
    def test_ensure_label_creates_when_missing(self):
        mock_get = MagicMock(status_code=404)
        mock_post = MagicMock(status_code=201)
        with patch("app.modes.action.labeler.requests") as mock_requests:
            mock_requests.get.return_value = mock_get
            mock_requests.post.return_value = mock_post
            ensure_label("org/repo", "fake-token")
            mock_requests.post.assert_called_once()
            call_json = mock_requests.post.call_args[1]["json"]
            assert call_json["name"] == GOOD_FIRST_ISSUE_LABEL

    def test_ensure_label_skips_when_exists(self):
        mock_get = MagicMock(status_code=200)
        with patch("app.modes.action.labeler.requests") as mock_requests:
            mock_requests.get.return_value = mock_get
            ensure_label("org/repo", "fake-token")
            mock_requests.post.assert_not_called()

    def test_add_label_uses_good_first_issue(self):
        with patch("app.modes.action.labeler.ensure_label"), \
             patch("app.modes.action.labeler.requests") as mock_requests:
            mock_requests.post.return_value = MagicMock(status_code=200)
            add_label("org/repo", 42, "fake-token")
            call_json = mock_requests.post.call_args[1]["json"]
            assert call_json["labels"] == ["good first issue"]

    def test_post_comment_includes_verdict(self):
        analysis = {
            "verdict": "GO FOR IT",
            "total_score": 12,
            "summary": "Simple fix",
            "fix_description": "Edit the README",
            "skills_needed": ["Markdown"],
            "starting_point": 4,
            "starting_point_reason": "File specified",
            "scope": 4,
            "scope_reason": "Small change",
            "familiarity": 4,
            "familiarity_reason": "Isolated code",
        }
        with patch("app.modes.action.labeler.requests") as mock_requests:
            mock_requests.post.return_value = MagicMock(status_code=201)
            post_comment("org/repo", 42, analysis, "fake-token")
            call_json = mock_requests.post.call_args[1]["json"]
            assert "GO FOR IT" in call_json["body"]
            assert "12/15" in call_json["body"]
            assert "Edit the README" in call_json["body"]
            assert "Markdown" in call_json["body"]
            assert "newcomer-assess" in call_json["body"]
            assert "Starting Point: 4/5" in call_json["body"]


class TestActionMain:
    def test_labels_and_comments_on_success(self, tmp_path):
        event_path = _write_event(tmp_path)
        analysis = {"verdict": "GO FOR IT", "summary": "Simple fix", "claimed": False}

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "INPUT_MIN_VERDICT": "STRETCH",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }
        (tmp_path / "output.txt").write_text("")

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue", return_value=analysis), \
             patch("app.modes.action.main.add_label", return_value=True) as mock_label, \
             patch("app.modes.action.main.post_comment") as mock_comment:
            main()
            mock_label.assert_called_once_with("org/repo", 42, "fake-gh-token")
            mock_comment.assert_called_once_with("org/repo", 42, analysis, "fake-gh-token")

    def test_skips_below_threshold(self, tmp_path):
        event_path = _write_event(tmp_path)
        analysis = {"verdict": "LONG SHOT", "summary": "Hard issue", "claimed": False}

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "INPUT_MIN_VERDICT": "STRETCH",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }
        (tmp_path / "output.txt").write_text("")

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue", return_value=analysis), \
             patch("app.modes.action.main.add_label") as mock_label, \
             patch("app.modes.action.main.post_comment") as mock_comment:
            main()
            mock_label.assert_not_called()
            mock_comment.assert_not_called()

    def test_handles_assessment_failure(self, tmp_path):
        event_path = _write_event(tmp_path)

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }
        (tmp_path / "output.txt").write_text("")

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue", return_value=None), \
             patch("app.modes.action.main.add_label") as mock_label:
            main()
            mock_label.assert_not_called()

    def test_writes_outputs(self, tmp_path):
        event_path = _write_event(tmp_path)
        output_path = tmp_path / "output.txt"
        output_path.write_text("")
        analysis = {"verdict": "STRETCH", "summary": "Moderate task", "claimed": False}

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "INPUT_MIN_VERDICT": "STRETCH",
            "GITHUB_OUTPUT": str(output_path),
        }

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue", return_value=analysis), \
             patch("app.modes.action.main.add_label", return_value=True), \
             patch("app.modes.action.main.post_comment"):
            main()

        outputs = output_path.read_text()
        assert "verdict=STRETCH" in outputs
        assert "summary=Moderate task" in outputs
        assert "label=good first issue" in outputs


class TestProfileAwareLabeling:
    def _make_profile_dir(self, tmp_path, auto_label=True):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir(exist_ok=True)
        profile_data = {
            "repos": ["org/repo"],
            "label_map": {"JUMP ON IT": "good first issue", "GO FOR IT": "good first issue"},
            "auto_label": auto_label,
        }
        (profiles_dir / "test.yaml").write_text(yaml.dump(profile_data))
        return profiles_dir

    def test_uses_profile_label_map(self, tmp_path):
        event_path = _write_event(tmp_path)
        profiles_dir = self._make_profile_dir(tmp_path)
        analysis = {"verdict": "GO FOR IT", "summary": "Easy fix", "claimed": False}

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "INPUT_REPO_PROFILE": "test",
            "INPUT_MIN_VERDICT": "STRETCH",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }
        (tmp_path / "output.txt").write_text("")

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue", return_value=analysis), \
             patch("app.core.profiles.PROFILES_DIR", profiles_dir), \
             patch("app.modes.action.main.add_label", return_value=True) as mock_label, \
             patch("app.modes.action.main.post_comment"):
            main()
            mock_label.assert_called_once_with("org/repo", 42, "fake-gh-token", label_name="good first issue")

    def test_no_label_when_verdict_not_in_map(self, tmp_path):
        event_path = _write_event(tmp_path)
        profiles_dir = self._make_profile_dir(tmp_path)
        analysis = {"verdict": "STRETCH", "summary": "Harder fix", "claimed": False}

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "INPUT_REPO_PROFILE": "test",
            "INPUT_MIN_VERDICT": "STRETCH",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }
        (tmp_path / "output.txt").write_text("")

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue", return_value=analysis), \
             patch("app.core.profiles.PROFILES_DIR", profiles_dir), \
             patch("app.modes.action.main.add_label") as mock_label, \
             patch("app.modes.action.main.post_comment") as mock_comment:
            main()
            mock_label.assert_not_called()
            mock_comment.assert_called_once()

    def test_falls_back_without_profile(self, tmp_path):
        event_path = _write_event(tmp_path)
        analysis = {"verdict": "STRETCH", "summary": "Task", "claimed": False}

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "INPUT_MIN_VERDICT": "STRETCH",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }
        (tmp_path / "output.txt").write_text("")

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue", return_value=analysis), \
             patch("app.modes.action.main.add_label", return_value=True) as mock_label, \
             patch("app.modes.action.main.post_comment"):
            main()
            mock_label.assert_called_once_with("org/repo", 42, "fake-gh-token")

    def test_suggests_label_when_auto_label_false(self, tmp_path):
        event_path = _write_event(tmp_path)
        profiles_dir = self._make_profile_dir(tmp_path, auto_label=False)
        analysis = {"verdict": "GO FOR IT", "summary": "Easy fix", "claimed": False}

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "INPUT_REPO_PROFILE": "test",
            "INPUT_MIN_VERDICT": "STRETCH",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }
        (tmp_path / "output.txt").write_text("")

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue", return_value=analysis), \
             patch("app.core.profiles.PROFILES_DIR", profiles_dir), \
             patch("app.modes.action.main.add_label") as mock_label, \
             patch("app.modes.action.main.post_comment") as mock_comment:
            main()
            mock_label.assert_not_called()
            mock_comment.assert_called_once()
            _, kwargs = mock_comment.call_args
            assert kwargs.get("suggested_label") == "good first issue"

    def test_auto_labels_when_auto_label_true(self, tmp_path):
        event_path = _write_event(tmp_path)
        profiles_dir = self._make_profile_dir(tmp_path, auto_label=True)
        analysis = {"verdict": "GO FOR IT", "summary": "Easy fix", "claimed": False}

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "INPUT_REPO_PROFILE": "test",
            "INPUT_MIN_VERDICT": "STRETCH",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }
        (tmp_path / "output.txt").write_text("")

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue", return_value=analysis), \
             patch("app.core.profiles.PROFILES_DIR", profiles_dir), \
             patch("app.modes.action.main.add_label", return_value=True) as mock_label, \
             patch("app.modes.action.main.post_comment") as mock_comment:
            main()
            mock_label.assert_called_once_with("org/repo", 42, "fake-gh-token", label_name="good first issue")
            mock_comment.assert_called_once()
            _, kwargs = mock_comment.call_args
            assert "suggested_label" not in kwargs or kwargs.get("suggested_label") is None


class TestFetchIssueFromApi:
    def test_returns_issue_dict(self):
        issue_resp = MagicMock(status_code=200)
        issue_resp.json.return_value = {
            "number": 62,
            "title": "Fix widget rendering",
            "body": "The widget doesn't render correctly",
            "html_url": "https://github.com/org/repo/issues/62",
            "labels": [{"name": "bug"}],
        }
        repo_resp = MagicMock(status_code=200)
        repo_resp.json.return_value = {"language": "Rust"}

        with patch("app.modes.action.main.requests") as mock_requests:
            mock_requests.get.side_effect = [issue_resp, repo_resp]
            result = fetch_issue_from_api("org/repo", 62, "fake-token")

        assert result["repo"] == "org/repo"
        assert result["number"] == 62
        assert result["title"] == "Fix widget rendering"
        assert result["body"] == "The widget doesn't render correctly"
        assert result["labels"] == ["bug"]
        assert result["comments"] == []
        assert result["repo_language"] == "Rust"

    def test_returns_none_on_failure(self):
        resp = MagicMock(status_code=404, text="Not Found")
        with patch("app.modes.action.main.requests") as mock_requests:
            mock_requests.get.return_value = resp
            result = fetch_issue_from_api("org/repo", 999, "fake-token")
        assert result is None

    def test_handles_null_body(self):
        issue_resp = MagicMock(status_code=200)
        issue_resp.json.return_value = {
            "number": 5,
            "title": "Empty body",
            "body": None,
            "html_url": "https://github.com/org/repo/issues/5",
            "labels": [],
        }
        repo_resp = MagicMock(status_code=200)
        repo_resp.json.return_value = {"language": "Python"}

        with patch("app.modes.action.main.requests") as mock_requests:
            mock_requests.get.side_effect = [issue_resp, repo_resp]
            result = fetch_issue_from_api("org/repo", 5, "fake-token")
        assert result["body"] == ""


class TestWorkflowDispatch:
    def _write_dispatch_event(self, tmp_path, issue_number="62"):
        event = {"action": "workflow_dispatch", "inputs": {"issue_number": issue_number}}
        path = tmp_path / "event.json"
        path.write_text(json.dumps(event))
        return str(path)

    def test_fetches_from_api_when_no_issue_in_event(self, tmp_path):
        event_path = self._write_dispatch_event(tmp_path, "62")
        (tmp_path / "output.txt").write_text("")
        analysis = {"verdict": "GO FOR IT", "summary": "Easy fix", "claimed": False}

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "INPUT_ISSUE_NUMBER": "62",
            "INPUT_MIN_VERDICT": "STRETCH",
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }

        fake_issue = {
            "repo": "org/repo", "number": 62, "title": "Fix widget",
            "body": "broken", "url": "https://github.com/org/repo/issues/62",
            "labels": [], "comments": [], "repo_language": "Rust",
        }

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.fetch_issue_from_api", return_value=fake_issue) as mock_fetch, \
             patch("app.modes.action.main.assess_issue", return_value=analysis), \
             patch("app.modes.action.main.add_label", return_value=True), \
             patch("app.modes.action.main.post_comment"):
            main()
            mock_fetch.assert_called_once_with("org/repo", 62, "fake-gh-token")

    def test_exits_when_no_issue_and_no_number(self, tmp_path):
        event = {"action": "workflow_dispatch", "inputs": {}}
        path = tmp_path / "event.json"
        path.write_text(json.dumps(event))
        (tmp_path / "output.txt").write_text("")

        env = {
            "GITHUB_EVENT_PATH": str(path),
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue") as mock_assess:
            main()
            mock_assess.assert_not_called()


class TestAutoLabelOverride:
    def _make_profile_dir(self, tmp_path, auto_label=False):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir(exist_ok=True)
        profile_data = {
            "repos": ["org/repo"],
            "label_map": {"JUMP ON IT": "good first issue", "GO FOR IT": "good first issue"},
            "auto_label": auto_label,
        }
        (profiles_dir / "test.yaml").write_text(yaml.dump(profile_data))
        return profiles_dir

    def test_override_enables_labeling(self, tmp_path):
        event_path = _write_event(tmp_path)
        profiles_dir = self._make_profile_dir(tmp_path, auto_label=False)
        analysis = {"verdict": "GO FOR IT", "summary": "Easy fix", "claimed": False}
        (tmp_path / "output.txt").write_text("")

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "INPUT_REPO_PROFILE": "test",
            "INPUT_AUTO_LABEL": "true",
            "INPUT_MIN_VERDICT": "STRETCH",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue", return_value=analysis), \
             patch("app.core.profiles.PROFILES_DIR", profiles_dir), \
             patch("app.modes.action.main.add_label", return_value=True) as mock_label, \
             patch("app.modes.action.main.post_comment"):
            main()
            mock_label.assert_called_once_with("org/repo", 42, "fake-gh-token", label_name="good first issue")

    def test_no_override_suggests_label(self, tmp_path):
        event_path = _write_event(tmp_path)
        profiles_dir = self._make_profile_dir(tmp_path, auto_label=False)
        analysis = {"verdict": "GO FOR IT", "summary": "Easy fix", "claimed": False}
        (tmp_path / "output.txt").write_text("")

        env = {
            "GITHUB_EVENT_PATH": event_path,
            "INPUT_LLM_TOKEN": "fake-llm-token",
            "INPUT_GITHUB_TOKEN": "fake-gh-token",
            "INPUT_REPO_PROFILE": "test",
            "INPUT_MIN_VERDICT": "STRETCH",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        }

        with patch.dict(os.environ, env, clear=False), \
             patch("app.modes.action.main.assess_issue", return_value=analysis), \
             patch("app.core.profiles.PROFILES_DIR", profiles_dir), \
             patch("app.modes.action.main.add_label") as mock_label, \
             patch("app.modes.action.main.post_comment") as mock_comment:
            main()
            mock_label.assert_not_called()
            mock_comment.assert_called_once()
            _, kwargs = mock_comment.call_args
            assert kwargs.get("suggested_label") == "good first issue"
