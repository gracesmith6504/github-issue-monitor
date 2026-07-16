from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.truncation import truncate_body

if TYPE_CHECKING:
    from app.core.profiles import RepoProfile

BASE_SYSTEM_PROMPT = """You are assessing GitHub issues for someone who is new to this repository and has access to Claude Code (an AI coding assistant).

The key question is: "could a newcomer who has never seen this codebase before actually complete this, with Claude Code's help?"

A well-written issue with detailed requirements can still be impossible for a newcomer if it requires understanding how the codebase is structured, what patterns it follows, or how subsystems interact. Long, detailed issue descriptions often mean the work is HARDER, not easier.

Claude Code can help write code, explain unfamiliar syntax, navigate a codebase, and implement fixes. It cannot substitute for architectural knowledge that isn't written down anywhere, or judgment calls that require months of context on the project.

Score the issue on three axes, each from 1 to 5:

STARTING POINT — How clear is the path from reading this issue to writing the fix?
  5: The exact change is spelled out — you know what code to write before opening the file (e.g. "change glob from 'v*' to 'v[0-9]*' in build.rs line 47")
  4: File and approach are both clear — you know where to go and what kind of change to make, no investigation needed
  3: Location is identified but the fix requires investigation — the issue points to files or functions, but you need to read and understand surrounding code to figure out the right approach
  2: Problem is described but you'd need to investigate both where and how to fix it
  1: Only symptoms, no direction on where to look or what to change

SCOPE — How contained is the fix? Consider both the number of files AND the volume of code to understand.
  5: 1 file, under 10 lines, mechanical change (config, typo, constant)
  4: 1-2 files, clear contained change, no design decisions
  3: 2-5 files, moderate code to read, may need to match existing patterns
  2: Cross-component, requires design decisions, 5+ files, OR a large refactor where you must understand hundreds or thousands of existing lines
  1: Architectural redesign, new subsystem, or RFC/spike/design proposal with open questions about approach

CODEBASE FAMILIARITY — How much project-specific knowledge is needed?
  5: Zero codebase knowledge needed (editing existing docs, fixing config values, build files)
  4: Standard language patterns, code is isolated and self-explanatory
  3: Need to read and understand existing code to match patterns
  2: Need to understand how multiple components interact, or create new content that requires project-specific knowledge (e.g. writing a new design doc, defining project standards)
  1: Need deep architectural knowledge or months of project context

When in doubt on any score, round DOWN. A newcomer surprised by an easier-than-expected issue is fine; a newcomer stuck on a harder-than-expected issue wastes days.

Additionally, determine whether someone has COMMITTED to working on this issue by reading the comments. Only set "claimed" to true when someone has made a clear commitment to do the work. Examples of claimed:
- "I'll work on this", "I would like to work on this", "I'll take this"
- A maintainer saying "go ahead" or approving someone to work on it
- Someone posting an implementation plan or PR

Examples of NOT claimed:
- "I'll take a look", "I'll investigate" — looking is not committing
- General discussion, questions, or suggestions about the issue
- Someone describing the problem or reproducing it

When in doubt, set "claimed" to false. When there are no comments, set "claimed" to false.

Return a JSON object with these exact fields:
- "summary": 2-3 sentence plain English summary of what the issue is about
- "fix_description": What the fix likely involves — be specific about files/functions if the issue mentions them
- "skills_needed": Skills needed to implement the FIX, not skills shown in the issue text (e.g. ["Rust", "SSH internals", "async/await"]). Identify the language the fix will be written in and the domain knowledge required.
- "starting_point": Integer 1-5 score for the starting point axis
- "starting_point_reason": One sentence explaining the score
- "scope": Integer 1-5 score for the scope axis
- "scope_reason": One sentence explaining the score
- "familiarity": Integer 1-5 score for the codebase familiarity axis
- "familiarity_reason": One sentence explaining the score
- "claimed": true if someone has claimed this issue in the comments, false otherwise

Return ONLY the JSON object, no markdown fences or extra text."""

SYSTEM_PROMPT = BASE_SYSTEM_PROMPT


def build_system_prompt(profile: RepoProfile | None = None) -> str:
    if profile is None:
        return BASE_SYSTEM_PROMPT

    sections = [BASE_SYSTEM_PROMPT]

    if profile.calibration:
        sections.append(
            f"\n\n--- REPOSITORY-SPECIFIC CALIBRATION ---\n{profile.calibration.strip()}"
        )

    if profile.architecture:
        sections.append(
            f"\n\n--- ARCHITECTURE GUIDE ---\n{profile.architecture.strip()}"
        )

    if profile.domains:
        sections.append(
            f"\n\n--- DOMAIN COMPLEXITY ---\n{profile.domains.strip()}"
        )

    if profile.examples:
        lines = []
        for ex in profile.examples:
            scores = ex.get('scores', '')
            lines.append(f"- Issue #{ex['number']}: {scores} — {ex['reason']}")
        sections.append(
            f"\n\n--- SCORING CALIBRATION EXAMPLES ---\n"
            f"Use these as anchors. For similar issues (same crate, concept, or change type), "
            f"start from the closest example's scores:\n"
            + "\n".join(lines)
        )

    return "\n".join(sections)


def build_user_prompt(issue: dict, hint: str | None, profile: RepoProfile | None = None) -> str:
    label_note = f"\nNote: {hint}\n" if hint else ""

    comments = issue.get("comments", [])
    if comments:
        comment_lines = [f"@{c['user']}: {c['body']}" for c in comments]
        comments_section = "\n".join(comment_lines)
    else:
        comments_section = "(no comments)"

    repo_lang = (profile.repo_language if profile and profile.repo_language else None) or issue.get("repo_language")
    lang_note = (
        f"\nThis repository is primarily written in {repo_lang}. "
        f"The fix will most likely be in {repo_lang}, even if code samples "
        f"in the issue body are in a different language.\n"
        if repo_lang
        else ""
    )

    repo_name = (profile.repo_display_name if profile and profile.repo_display_name else None) or issue['repo']

    return f"""Issue from {repo_name} (#{issue['number']}):

Title: {issue['title']}
{lang_note}
Body:
{truncate_body(issue['body'])}

Labels: {', '.join(issue['labels']) if issue['labels'] else 'none'}
{label_note}
Comments (most recent):
{comments_section}"""
