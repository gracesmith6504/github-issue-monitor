import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a GitHub issue analyst. Given an issue title and body, assess whether it's suitable for a junior developer / open-source beginner.

Return a JSON object with these fields:
- "summary": 2-3 sentence plain English summary of what the issue is about
- "fix_description": What the fix likely involves (files to change, approach)
- "skills_needed": List of skills/technologies needed (e.g. ["Python", "REST APIs", "testing"])
- "difficulty": One of "easy", "medium", "hard"
  - easy: documentation, config, typo, small one-file change
  - medium: code change in 1-2 files, requires some domain knowledge
  - hard: multi-file change, deep domain knowledge, complex debugging
- "verdict": One of "GO FOR IT", "STRETCH", "NOT YET"
  - GO FOR IT: a beginner could tackle this with some effort
  - STRETCH: doable but will be challenging, good learning opportunity
  - NOT YET: requires deep expertise or major refactoring
- "verdict_reason": One sentence explaining the verdict

Return ONLY the JSON object, no markdown fences or extra text."""


def analyze_issue(issue, token, model):
    client = OpenAI(
        base_url="https://models.github.ai/inference",
        api_key=token,
    )

    user_prompt = f"""Issue from {issue['repo']}:

Title: {issue['title']}

Body:
{issue['body'][:3000] if issue['body'] else '(no description provided)'}

Labels: {', '.join(issue['labels']) if issue['labels'] else 'none'}"""

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
