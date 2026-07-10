import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

GOOD_FIRST_ISSUE_LABELS = {
    "good first issue",
    "good-first-issue",
    "beginner",
    "beginner-friendly",
    "starter",
    "easy",
    "newcomer",
    "first-timers-only",
}

APPROACHABLE_LABELS = {
    "documentation",
    "docs",
    "typo",
    "test",
    "tests",
    "help wanted",
    "help-wanted",
}

SYSTEM_PROMPT = """You are assessing GitHub issues for someone who is new to this repository and has access to Claude Code (an AI coding assistant).

The key question is NOT "is this issue easy?" It is: "does this issue give a newcomer a clear enough starting point that they and Claude Code could figure it out?"

Claude Code can help write code, explain unfamiliar syntax, navigate a codebase, and implement fixes. It cannot substitute for architectural knowledge that isn't written down anywhere, or judgment calls that require months of context on the project.

Assess the issue on two things:
1. STARTING POINT — does the issue tell you WHERE to look? (specific file, function, error message, reproduction steps, or a clear description of what's wrong)
2. SOLVABILITY WITH AI — once you've found the starting point, is the fix something a newcomer + Claude Code could implement? Or does it require deep architectural judgment that AI can't substitute for?

Use these five verdicts:

- "JUMP ON IT": Clear starting point (file/function/error mentioned), straightforward fix. You and Claude will nail this. Claim it now before someone else does.
- "GO FOR IT": Clear starting point AND the fix is implementable without deep security/protocol/architectural expertise. Claude Code can guide you through it. Knowing which folder or module is involved is NOT enough for GO FOR IT — you also need to know what to actually change. Will take effort but very doable.
- "STRETCH": Starting point is vague but you could begin investigating by reading the code with Claude — exploring the relevant module, tracing a call stack, reading tests. The issue describes the problem clearly enough that you'd know what to look at. Worth attempting if you have time.
- "LONG SHOT": Very little direction. Even finding the starting point requires running the system in production conditions, profiling tools, or deep expertise to know where to look. Watch for phrases like "cannot pinpoint it", "could be anywhere", "needs profiling", "we don't know why" — these mean there's no codebase entry point for a newcomer. Claude might help you understand things you find but can't find them for you. Real risk of getting stuck for days.
- "NOT YET": No clear entry point. Requires architectural knowledge or cross-system judgment that Claude can't substitute for. Skip this one.

Return a JSON object with these exact fields:
- "summary": 2-3 sentence plain English summary of what the issue is about
- "fix_description": What the fix likely involves — be specific about files/functions if the issue mentions them
- "skills_needed": List of specific skills needed (e.g. ["Rust", "async/await", "HTTP parsing"])
- "verdict": One of "JUMP ON IT", "GO FOR IT", "STRETCH", "LONG SHOT", "NOT YET"
- "verdict_reason": One sentence explaining the verdict based on what's specific to this issue — what the starting point is (or isn't), what expertise is needed, what's vague. Do NOT write generic lines like "Claude Code can help" — that applies to every issue and adds nothing.

Return ONLY the JSON object, no markdown fences or extra text."""


def analyze_issue(issue, token, model):
    reclaimed = issue.get("trigger") == "unassigned"
    labels = [l.lower() for l in issue.get("labels", [])]

    hint = None
    if reclaimed:
        hint = ("This issue was previously assigned to a contributor who abandoned it. "
                "It has been vetted as actionable by the maintainers and may have useful "
                "comments or partial work from the previous attempt.")

    if any(l in GOOD_FIRST_ISSUE_LABELS for l in labels):
        logger.info(f"[{issue['repo']} #{issue['number']}] Has good-first-issue label")
        gfi = "This issue is explicitly labeled 'good first issue' by the maintainers — they consider it approachable for newcomers."
        hint = f"{hint} {gfi}" if hint else gfi
    elif not reclaimed:
        matched = [l for l in labels if l in APPROACHABLE_LABELS]
        if matched:
            hint = f"This issue is labeled '{matched[0]}' — consider whether it gives a newcomer a clear starting point."

    return _llm_analyze(issue, token, model, hint=hint)


def _llm_analyze(issue, token, model, hint):
    client = OpenAI(
        base_url="https://models.github.ai/inference",
        api_key=token,
    )

    label_note = f"\nNote: {hint}\n" if hint else ""

    user_prompt = f"""Issue from {issue['repo']}:

Title: {issue['title']}

Body:
{issue['body'][:3000] if issue['body'] else '(no description provided)'}

Labels: {', '.join(issue['labels']) if issue['labels'] else 'none'}
{label_note}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        analysis = json.loads(content)
        logger.info(f"[{issue['repo']} #{issue['number']}] Verdict: {analysis.get('verdict')}")
        return analysis

    except json.JSONDecodeError as e:
        logger.error(f"[{issue['repo']} #{issue['number']}] Failed to parse LLM response: {e}")
        return None
    except Exception as e:
        logger.error(f"[{issue['repo']} #{issue['number']}] LLM analysis failed: {e}")
        return None
