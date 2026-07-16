import json
import time
import logging
from typing import Protocol

from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://models.github.ai/inference"


class LLMClientProtocol(Protocol):
    def assess(self, system_prompt: str, user_prompt: str, model: str) -> dict | None: ...


class LLMClient:
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
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )

                content = response.choices[0].message.content.strip()
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
