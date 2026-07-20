import json
from unittest.mock import patch, MagicMock
import pytest

from app.core.llm import LLMClient


def _mock_response(content_dict=None, content_str=None, null_content=False, empty_choices=False):
    response = MagicMock()
    if empty_choices:
        response.choices = []
        return response
    choice = MagicMock()
    if null_content:
        choice.message.content = None
    elif content_str is not None:
        choice.message.content = content_str
    elif content_dict is not None:
        choice.message.content = json.dumps(content_dict)
    else:
        choice.message.content = json.dumps({"result": "ok"})
    response.choices = [choice]
    return response


class TestLLMClientAssess:
    @patch("app.core.llm.OpenAI")
    def test_valid_json_returns_parsed_dict(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response({"score": 5})

        client = LLMClient(api_key="test-key")
        result = client.assess("system", "user", "gpt-4o")
        assert result == {"score": 5}

    @patch("app.core.llm.OpenAI")
    def test_null_content_returns_none(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response(null_content=True)

        client = LLMClient(api_key="test-key")
        result = client.assess("system", "user", "gpt-4o")
        assert result is None

    @patch("app.core.llm.OpenAI")
    def test_empty_choices_returns_none(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response(empty_choices=True)

        client = LLMClient(api_key="test-key")
        result = client.assess("system", "user", "gpt-4o")
        assert result is None

    @patch("app.core.llm.OpenAI")
    def test_invalid_json_returns_none(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_response(content_str="not json {{{")

        client = LLMClient(api_key="test-key")
        result = client.assess("system", "user", "gpt-4o")
        assert result is None

    @patch("app.core.llm.time")
    @patch("app.core.llm.OpenAI")
    def test_transient_error_retries_then_succeeds(self, mock_openai_cls, mock_time):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = [
            ConnectionError("timeout"),
            _mock_response({"retried": True}),
        ]

        client = LLMClient(api_key="test-key")
        result = client.assess("system", "user", "gpt-4o")
        assert result == {"retried": True}
        assert mock_client.chat.completions.create.call_count == 2
        mock_time.sleep.assert_called_once_with(5)

    @patch("app.core.llm.time")
    @patch("app.core.llm.OpenAI")
    def test_all_retries_exhausted_returns_none(self, mock_openai_cls, mock_time):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = ConnectionError("timeout")

        client = LLMClient(api_key="test-key")
        result = client.assess("system", "user", "gpt-4o")
        assert result is None
        assert mock_client.chat.completions.create.call_count == 3

    @patch("app.core.llm.OpenAI")
    def test_custom_base_url(self, mock_openai_cls):
        LLMClient(api_key="test-key", base_url="https://custom.api/v1")
        mock_openai_cls.assert_called_once_with(base_url="https://custom.api/v1", api_key="test-key")
