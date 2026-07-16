from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.hints import build_hint
from app.core.llm import LLMClientProtocol as LLMClient
from app.core.prompt import SYSTEM_PROMPT, build_user_prompt
from app.core.scoring import build_verdict_reason, clamp_score, compute_verdict, lookup_example

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
    if not analysis:
        return None

    example = lookup_example(issue["number"], profile)
    if example:
        for key in ("starting_point", "scope", "familiarity",
                     "starting_point_reason", "scope_reason", "familiarity_reason"):
            analysis[key] = example[key]
    else:
        for axis in ("starting_point", "scope", "familiarity"):
            analysis[axis] = clamp_score(analysis.get(axis))

    thresholds = profile.verdict_thresholds if profile else None
    verdict, total = compute_verdict(
        analysis["starting_point"], analysis["scope"], analysis["familiarity"],
        thresholds=thresholds,
    )
    analysis["verdict"] = verdict
    analysis["total_score"] = total
    analysis["verdict_reason"] = build_verdict_reason(analysis)

    logger.info(
        f"[{issue['repo']} #{issue['number']}] "
        f"Scores: SP={analysis['starting_point']} Scope={analysis['scope']} "
        f"Fam={analysis['familiarity']} Total={total} -> {verdict}"
    )
    return analysis
