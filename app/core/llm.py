import json
import time
import logging
from typing import Protocol

from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://models.github.ai/inference"
DEFAULT_VERTEX_REGION = "us-east5"

PROVIDERS = ("github", "anthropic", "vertex")

DEFAULT_MODELS = {
    "github": "gpt-4o",
    "anthropic": "claude-sonnet-4-6",
    "vertex": "claude-sonnet-4-6",
}


class LLMClientProtocol(Protocol):
    def assess(self, system_prompt: str, user_prompt: str, model: str) -> dict | None: ...


def _strip_markdown_fences(text: str) -> str:
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text


class GitHubModelsClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL):
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def assess(self, system_prompt: str, user_prompt: str, model: str) -> dict | None:
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0,
                    response_format={"type": "json_object"},
                )

                if not response.choices:
                    logger.error("LLM returned empty choices")
                    return None
                content = response.choices[0].message.content
                if content is None:
                    logger.error("LLM returned null content")
                    return None
                return json.loads(content.strip())

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response: {e}")
                return None
            except Exception as e:
                if attempt < max_retries:
                    delay = 5 * (3 ** attempt)
                    logger.warning(f"LLM failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"LLM analysis failed after {max_retries + 1} attempts: {e}")
                    return None


class AnthropicClient:
    def __init__(self, api_key: str):
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for the anthropic provider. "
                "Install it with: pip install 'anthropic>=0.39.0'"
            )
        self._client = Anthropic(api_key=api_key)

    def assess(self, system_prompt: str, user_prompt: str, model: str) -> dict | None:
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = self._client.messages.create(
                    model=model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0,
                    max_tokens=4096,
                )

                content = _strip_markdown_fences(response.content[0].text.strip())
                return json.loads(content)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response: {e}")
                return None
            except Exception as e:
                if attempt < max_retries:
                    delay = 5 * (3 ** attempt)
                    logger.warning(f"LLM failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"LLM analysis failed after {max_retries + 1} attempts: {e}")
                    return None


class VertexClient:
    def __init__(self, project_id: str, region: str = DEFAULT_VERTEX_REGION):
        try:
            from anthropic import AnthropicVertex
        except ImportError:
            raise ImportError(
                "The 'anthropic[vertex]' package is required for the vertex provider. "
                "Install it with: pip install 'anthropic[vertex]>=0.39.0'"
            )
        self._client = AnthropicVertex(project_id=project_id, region=region)

    def assess(self, system_prompt: str, user_prompt: str, model: str) -> dict | None:
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = self._client.messages.create(
                    model=model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0,
                    max_tokens=4096,
                )

                content = _strip_markdown_fences(response.content[0].text.strip())
                return json.loads(content)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response: {e}")
                return None
            except Exception as e:
                if attempt < max_retries:
                    delay = 5 * (3 ** attempt)
                    logger.warning(f"LLM failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"LLM analysis failed after {max_retries + 1} attempts: {e}")
                    return None


LLMClient = GitHubModelsClient


def resolve_model(provider: str, explicit_model: str | None) -> str:
    if explicit_model:
        return explicit_model
    return DEFAULT_MODELS.get(provider, DEFAULT_MODELS["github"])


def create_llm_client(
    provider: str = "github",
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    project_id: str | None = None,
    region: str = DEFAULT_VERTEX_REGION,
) -> LLMClientProtocol:
    provider = provider.lower().strip()
    if provider not in PROVIDERS:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. Must be one of: {', '.join(PROVIDERS)}"
        )

    if provider == "github":
        if not api_key:
            raise ValueError("api_key is required for the github provider")
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return GitHubModelsClient(**kwargs)

    elif provider == "anthropic":
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required for the anthropic provider"
            )
        return AnthropicClient(api_key=api_key)

    elif provider == "vertex":
        if not project_id:
            raise ValueError(
                "VERTEX_PROJECT_ID is required for the vertex provider"
            )
        return VertexClient(project_id=project_id, region=region)
