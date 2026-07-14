import json
import time
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

The key question is NOT "is this issue easy?" and NOT "is this issue well-written?" It is: "could a newcomer who has never seen this codebase before actually complete this, with Claude Code's help?"

A well-written issue with detailed requirements can still be impossible for a newcomer if it requires understanding how the codebase is structured, what patterns it follows, or how subsystems interact. Long, detailed issue descriptions often mean the work is HARDER, not easier — they describe complex problems that need complex solutions.

Claude Code can help write code, explain unfamiliar syntax, navigate a codebase, and implement fixes. It cannot substitute for architectural knowledge that isn't written down anywhere, or judgment calls that require months of context on the project.

Assess the issue on THREE things:
1. STARTING POINT — does the issue tell you WHERE to look? (specific file, function, error message, reproduction steps)
2. SCOPE — is the fix contained to one file or a small area, or does it touch multiple subsystems, require design decisions, or need consistency with existing patterns across the codebase?
3. CODEBASE FAMILIARITY — could someone who has never read this codebase implement the fix? Or would they need to understand existing conventions, internal APIs, or how components interact?

Red flags that should push the verdict DOWN (toward STRETCH, LONG SHOT, or NOT YET):
- Spikes, RFCs, or design proposals — these are exploratory work, not implementation tasks
- Refactors — require understanding the current patterns to change them safely
- Issues that touch 3+ files or subsystems
- Issues that say "consistent with existing X" or "follow the pattern of Y" — a newcomer doesn't know what X or Y look like
- New subsystems or features that require design decisions (what API shape, what error handling strategy, what data model)
- Issues with words like "contract", "harness", "framework", "abstraction", "lifecycle"

Complexity domains that push toward STRETCH or below even when the issue is well-written — these are areas where Claude Code helps write code but cannot make the judgment calls:
- Auth, OAuth, or credential lifecycle — designing token flows, session management, or security scoping
- Networking internals — proxy chains, HTTP CONNECT, TLS termination, tunneling, DNS resolution
- SSH, PTY, or terminal handling — session lifecycle, channel management, signal propagation
- Concurrency or streaming protocols — async lifecycles, bidirectional gRPC, race conditions
- Security boundaries — policy enforcement, sandboxing, access control decisions
- New feature implementation requiring API design — choosing the right interface shape, error semantics, data model

Use these five verdicts:

- "JUMP ON IT": Clear starting point, small scope (1-2 files), no codebase familiarity needed. Fix a typo, update a config, add a simple flag. Claim it now.
- "GO FOR IT": Clear starting point, moderate scope, AND the fix is self-contained — you don't need to understand how the rest of the codebase works to make the change. A bug with reproduction steps and an obvious fix location. NOT for refactors, spikes, or anything requiring design decisions.
- "STRETCH": The issue is well-described but the fix requires either reading significant existing code to understand patterns, touching multiple files, or making judgment calls about implementation approach. Worth attempting with time and patience.
- "LONG SHOT": Requires deep expertise, production environment access, or understanding the full architecture. Real risk of getting stuck for days.
- "NOT YET": Architectural work, cross-system design, or requires months of project context. Skip this one.

When in doubt between two verdicts, pick the LOWER one. A newcomer surprised by an easier-than-expected issue is fine. A newcomer stuck on a harder-than-expected issue wastes days and gets discouraged.

Additionally, determine whether someone has COMMITTED to working on this issue by reading the comments. Only set "claimed" to true when someone has made a clear commitment to do the work. Examples of claimed:
- "I'll work on this", "I would like to work on this", "I'll take this", "I'm working on a fix"
- A maintainer saying "go ahead" or approving someone to work on it
- Someone posting an implementation plan or PR

Examples of NOT claimed — these are just investigation or discussion, not a commitment:
- "I'll take a look", "I'll investigate", "Let me check" — looking is not committing
- "Not sure I have time to fix it" — explicitly declining
- General discussion, questions, or suggestions about the issue
- Someone describing the problem or reproducing it

When in doubt, set "claimed" to false — it is better to notify about a claimed issue than to miss an available one.
When there are no comments, set "claimed" to false.

Return a JSON object with these exact fields:
- "summary": 2-3 sentence plain English summary of what the issue is about
- "fix_description": What the fix likely involves — be specific about files/functions if the issue mentions them
- "skills_needed": Skills needed to implement the FIX, not skills shown in the issue text (e.g. ["Rust", "SSH internals", "async/await"]). Identify the language the fix will be written in (which may differ from code samples in the issue body like reproduction scripts) and the domain knowledge required.
- "verdict": One of "JUMP ON IT", "GO FOR IT", "STRETCH", "LONG SHOT", "NOT YET"
- "verdict_reason": One sentence explaining the verdict based on what's specific to this issue — what the starting point is (or isn't), what expertise is needed, what's vague. Do NOT write generic lines like "Claude Code can help" — that applies to every issue and adds nothing.
- "claimed": true if someone has claimed this issue in the comments, false otherwise

Return ONLY the JSON object, no markdown fences or extra text."""


def analyze_issue(issue, token, model):
    reclaimed = issue.get("trigger") == "reclaimed"
    labels = [l.lower() for l in issue.get("labels", [])]

    hint = None
    if reclaimed:
        signals = issue.get("reclaimed_signals", [])
        parts = []
        if any(s == "closed-pr" for s in signals):
            parts.append("A linked pull request was closed without being merged — there may be partial work or review feedback from the abandoned PR.")
        if any(s == "unassigned" for s in signals):
            parts.append("A contributor was previously assigned but removed.")
        if any(s.startswith("removed-label:") for s in signals):
            parts.append("Work-in-progress markers were removed, suggesting work was started but not completed.")
        if not parts:
            parts.append("This issue was previously claimed and abandoned.")
        parts.append("Check the comments for useful context.")
        hint = " ".join(parts)

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

    comments = issue.get("comments", [])
    if comments:
        comment_lines = []
        for c in comments:
            comment_lines.append(f"@{c['user']}: {c['body']}")
        comments_section = "\n".join(comment_lines)
    else:
        comments_section = "(no comments)"

    repo_lang = issue.get('repo_language')
    lang_note = f"\nThis repository is primarily written in {repo_lang}. The fix will most likely be in {repo_lang}, even if code samples in the issue body are in a different language.\n" if repo_lang else ""

    user_prompt = f"""Issue from {issue['repo']}:

Title: {issue['title']}
{lang_note}
Body:
{issue['body'][:3000] if issue['body'] else '(no description provided)'}

Labels: {', '.join(issue['labels']) if issue['labels'] else 'none'}
{label_note}
Comments (most recent):
{comments_section}"""

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content.strip()
            analysis = json.loads(content)
            logger.info(f"[{issue['repo']} #{issue['number']}] Verdict: {analysis.get('verdict')}")
            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"[{issue['repo']} #{issue['number']}] Failed to parse LLM response: {e}")
            return None
        except Exception as e:
            if attempt < max_retries:
                delay = 5 * (3 ** attempt)
                logger.warning(f"[{issue['repo']} #{issue['number']}] LLM failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s: {e}")
                time.sleep(delay)
            else:
                logger.error(f"[{issue['repo']} #{issue['number']}] LLM analysis failed after {max_retries + 1} attempts: {e}")
                return None
