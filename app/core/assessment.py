from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.hints import build_hint
from app.core.llm import LLMClientProtocol as LLMClient
from app.core.prompt import SYSTEM_PROMPT, build_user_prompt

if TYPE_CHECKING:
    from app.core.profiles import RepoProfile

logger = logging.getLogger(__name__)


def assess_issue(
    issue: dict,
    llm_client: LLMClient,
    model: str,
    system_prompt: str | None = None,
    profile: RepoProfile | None = None,
) -> dict | None:
    hint = build_hint(issue)
    prompt = system_prompt or SYSTEM_PROMPT
    user_prompt = build_user_prompt(issue, hint, profile=profile)
    analysis = llm_client.assess(prompt, user_prompt, model)
    if analysis:
        logger.info(f"[{issue['repo']} #{issue['number']}] Verdict: {analysis.get('verdict')}")
    return analysis
