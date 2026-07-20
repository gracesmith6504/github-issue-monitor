import os
import pytest
from unittest.mock import patch

from app.modes.polling.config import load_config, ConfigError


MINIMAL_ENV = {
    "MONITOR_TOKEN": "ghp_test123",
    "WATCH_REPOS": "org/repo",
    "NOTIFY_REPO": "user/alerts",
}


class TestLoadConfig:
    @patch.dict(os.environ, MINIMAL_ENV, clear=True)
    def test_minimal_valid_config(self):
        config = load_config()
        assert config["monitor_token"] == "ghp_test123"
        assert config["watch_repos"] == ["org/repo"]
        assert config["notify_repo"] == "user/alerts"
        assert config["llm_model"] == ""
        assert config["poll_interval"] == 30
        assert config["min_verdict"] == "STRETCH"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_monitor_token_raises(self):
        with pytest.raises(ConfigError, match="MONITOR_TOKEN"):
            load_config()

    @patch.dict(os.environ, {"MONITOR_TOKEN": "tok"}, clear=True)
    def test_missing_watch_repos_raises(self):
        with pytest.raises(ConfigError, match="WATCH_REPOS"):
            load_config()

    @patch.dict(os.environ, {"MONITOR_TOKEN": "tok", "WATCH_REPOS": "org/repo"}, clear=True)
    def test_missing_notify_repo_raises(self):
        with pytest.raises(ConfigError, match="NOTIFY_REPO"):
            load_config()

    @patch.dict(os.environ, {**MINIMAL_ENV, "LLM_TOKEN": "llm-key-123"}, clear=True)
    def test_llm_token_used_when_set(self):
        config = load_config()
        assert config["llm_token"] == "llm-key-123"

    @patch.dict(os.environ, MINIMAL_ENV, clear=True)
    def test_llm_token_falls_back_to_monitor_token(self):
        config = load_config()
        assert config["llm_token"] == "ghp_test123"

    @patch.dict(os.environ, {**MINIMAL_ENV, "POLL_INTERVAL": "60", "MAX_ISSUES_PER_REPO": "50"}, clear=True)
    def test_integer_env_vars_parsed(self):
        config = load_config()
        assert config["poll_interval"] == 60
        assert config["max_issues_per_repo"] == 50

    @patch.dict(os.environ, {**MINIMAL_ENV, "WATCH_REPOS": "org/a, org/b, org/c"}, clear=True)
    def test_multiple_repos_parsed(self):
        config = load_config()
        assert config["watch_repos"] == ["org/a", "org/b", "org/c"]

    @patch.dict(os.environ, {**MINIMAL_ENV, "GITHUB_APP_ID": "12345", "GITHUB_APP_PRIVATE_KEY": "fake-key", "GITHUB_APP_INSTALLATION_ID": "67890"}, clear=True)
    def test_github_app_config_all_fields(self):
        config = load_config()
        assert config["app_id"] == "12345"
        assert config["private_key"] == "fake-key"
        assert config["installation_id"] == "67890"

    @patch.dict(os.environ, {**MINIMAL_ENV, "GITHUB_APP_ID": "12345"}, clear=True)
    def test_github_app_missing_key_raises(self):
        with pytest.raises(ConfigError, match="GITHUB_APP_PRIVATE_KEY"):
            load_config()

    @patch.dict(os.environ, {**MINIMAL_ENV, "GITHUB_APP_ID": "12345", "GITHUB_APP_PRIVATE_KEY": "key"}, clear=True)
    def test_github_app_missing_installation_id_raises(self):
        with pytest.raises(ConfigError, match="GITHUB_APP_INSTALLATION_ID"):
            load_config()

    @patch.dict(os.environ, {**MINIMAL_ENV, "LLM_ENDPOINT": "https://api.openai.com/v1"}, clear=True)
    def test_llm_endpoint_stored(self):
        config = load_config()
        assert config["llm_endpoint"] == "https://api.openai.com/v1"
