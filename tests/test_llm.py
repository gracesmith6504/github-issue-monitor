import json
from unittest.mock import patch, MagicMock

import pytest

from app.core.llm import (
    GitHubModelsClient,
    LLMClient,
    _strip_markdown_fences,
    create_llm_client,
    resolve_model,
    DEFAULT_MODELS,
)


class TestStripMarkdownFences:
    def test_no_fences(self):
        assert _strip_markdown_fences('{"a": 1}') == '{"a": 1}'

    def test_json_fences(self):
        text = '```json\n{"a": 1}\n```'
        assert _strip_markdown_fences(text) == '{"a": 1}'

    def test_plain_fences(self):
        text = '```\n{"a": 1}\n```'
        assert _strip_markdown_fences(text) == '{"a": 1}'


class TestGitHubModelsClient:
    def test_successful_json_response(self):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content='{"verdict": "GO FOR IT"}'))
        ]
        client = GitHubModelsClient.__new__(GitHubModelsClient)
        client._client = mock_openai

        result = client.assess("system", "user", "gpt-4o")
        assert result == {"verdict": "GO FOR IT"}

    def test_returns_none_on_json_parse_error(self):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="not json"))
        ]
        client = GitHubModelsClient.__new__(GitHubModelsClient)
        client._client = mock_openai

        result = client.assess("system", "user", "gpt-4o")
        assert result is None

    def test_retries_on_transient_error(self):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.side_effect = [
            RuntimeError("rate limit"),
            MagicMock(choices=[MagicMock(message=MagicMock(content='{"ok": true}'))]),
        ]
        client = GitHubModelsClient.__new__(GitHubModelsClient)
        client._client = mock_openai

        with patch("app.core.llm.time.sleep"):
            result = client.assess("system", "user", "gpt-4o")
        assert result == {"ok": True}

    def test_returns_none_after_max_retries(self):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.side_effect = RuntimeError("down")
        client = GitHubModelsClient.__new__(GitHubModelsClient)
        client._client = mock_openai

        with patch("app.core.llm.time.sleep"):
            result = client.assess("system", "user", "gpt-4o")
        assert result is None


class TestAnthropicClient:
    def _make_client(self):
        mock_anthropic_module = MagicMock()
        mock_sdk_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_sdk_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic_module}):
            from app.core.llm import AnthropicClient
            client = AnthropicClient(api_key="sk-test")

        return client, mock_sdk_client

    def test_successful_json_response(self):
        client, mock_sdk = self._make_client()
        mock_sdk.messages.create.return_value.content = [
            MagicMock(text='{"verdict": "STRETCH"}')
        ]

        result = client.assess("system", "user", "claude-sonnet-4-6")
        assert result == {"verdict": "STRETCH"}

        call_kwargs = mock_sdk.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "system"
        assert call_kwargs["max_tokens"] == 4096

    def test_strips_markdown_fences(self):
        client, mock_sdk = self._make_client()
        mock_sdk.messages.create.return_value.content = [
            MagicMock(text='```json\n{"verdict": "GO FOR IT"}\n```')
        ]

        result = client.assess("system", "user", "claude-sonnet-4-6")
        assert result == {"verdict": "GO FOR IT"}


class TestVertexClient:
    def _make_client(self):
        mock_anthropic_module = MagicMock()
        mock_sdk_client = MagicMock()
        mock_anthropic_module.AnthropicVertex.return_value = mock_sdk_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic_module}):
            from app.core.llm import VertexClient
            client = VertexClient(project_id="my-project", region="us-east5")

        return client, mock_sdk_client

    def test_successful_json_response(self):
        client, mock_sdk = self._make_client()
        mock_sdk.messages.create.return_value.content = [
            MagicMock(text='{"verdict": "JUMP ON IT"}')
        ]

        result = client.assess("system", "user", "claude-sonnet-4-6")
        assert result == {"verdict": "JUMP ON IT"}


class TestResolveModel:
    def test_explicit_model_wins(self):
        assert resolve_model("github", "gpt-4o-mini") == "gpt-4o-mini"

    def test_github_default(self):
        assert resolve_model("github", "") == "gpt-4o"
        assert resolve_model("github", None) == "gpt-4o"

    def test_anthropic_default(self):
        assert resolve_model("anthropic", "") == "claude-sonnet-4-6"

    def test_vertex_default(self):
        assert resolve_model("vertex", "") == "claude-sonnet-4-6"

    def test_unknown_provider_falls_back(self):
        assert resolve_model("unknown", "") == DEFAULT_MODELS["github"]


class TestCreateLlmClient:
    def test_github_default(self):
        client = create_llm_client(provider="github", api_key="test")
        assert isinstance(client, GitHubModelsClient)

    def test_github_with_custom_base_url(self):
        client = create_llm_client(
            provider="github", api_key="test", base_url="https://custom.api/v1"
        )
        assert isinstance(client, GitHubModelsClient)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            create_llm_client(provider="ollama", api_key="test")

    def test_missing_api_key_for_github_raises(self):
        with pytest.raises(ValueError, match="api_key"):
            create_llm_client(provider="github")

    def test_missing_api_key_for_anthropic_raises(self):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            create_llm_client(provider="anthropic")

    def test_missing_project_id_for_vertex_raises(self):
        with pytest.raises(ValueError, match="VERTEX_PROJECT_ID"):
            create_llm_client(provider="vertex")

    def test_case_insensitive_provider(self):
        client = create_llm_client(provider="GitHub", api_key="test")
        assert isinstance(client, GitHubModelsClient)

    def test_backward_compat_alias(self):
        assert LLMClient is GitHubModelsClient
