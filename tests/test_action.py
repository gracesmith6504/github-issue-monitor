import json
import os
from unittest.mock import patch, MagicMock

import yaml

from app.core.profiles import RepoProfile
from app.modes.action.main import build_issue_dict, main
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
            "summary": "Simple fix",
            "fix_description": "Edit the README",
            "skills_needed": ["Markdown"],
            "verdict_reason": "Just a typo",
        }
        with patch("app.modes.action.labeler.requests") as mock_requests:
            mock_requests.post.return_value = MagicMock(status_code=201)
            post_comment("org/repo", 42, analysis, "fake-token")
            call_json = mock_requests.post.call_args[1]["json"]
            assert "GO FOR IT" in call_json["body"]
            assert "Simple fix" in call_json["body"]
            assert "Edit the README" in call_json["body"]
            assert "Markdown" in call_json["body"]


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
    def _make_profile_dir(self, tmp_path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile_data = {
            "repos": ["org/repo"],
            "label_map": {"JUMP ON IT": "good first issue", "GO FOR IT": "good first issue"},
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
