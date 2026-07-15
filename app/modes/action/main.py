import json
import logging
import os
import sys

from app.core.assessment import assess_issue
from app.core.llm import GitHubModelsClient
from app.core.profiles import load_profile
from app.core.prompt import build_system_prompt
from app.core.verdict import meets_threshold
from app.modes.action.labeler import add_label, post_comment, GOOD_FIRST_ISSUE_LABEL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_event():
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        logger.error("GITHUB_EVENT_PATH not set")
        sys.exit(1)
    with open(event_path) as f:
        return json.load(f)


def build_issue_dict(event):
    issue = event["issue"]
    return {
        "repo": event["repository"]["full_name"],
        "number": issue["number"],
        "title": issue["title"],
        "body": issue.get("body") or "",
        "url": issue["html_url"],
        "labels": [l["name"] for l in issue.get("labels", [])],
        "comments": [],
        "repo_language": event["repository"].get("language"),
    }


def _set_output(key, value):
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"{key}={value}\n")


def main():
    llm_token = os.environ.get("INPUT_LLM_TOKEN") or os.environ.get("INPUT_LLM-TOKEN")
    if not llm_token:
        logger.error("llm-token input is required")
        sys.exit(1)

    github_token = os.environ.get("INPUT_GITHUB_TOKEN") or os.environ.get("INPUT_GITHUB-TOKEN")
    if not github_token:
        logger.error("github-token input is required")
        sys.exit(1)

    model = os.environ.get("INPUT_LLM_MODEL") or os.environ.get("INPUT_LLM-MODEL") or "gpt-4o"
    min_verdict = (os.environ.get("INPUT_MIN_VERDICT") or os.environ.get("INPUT_MIN-VERDICT") or "STRETCH").upper()

    profile_name = os.environ.get("INPUT_REPO_PROFILE") or os.environ.get("INPUT_REPO-PROFILE") or ""
    profile = None
    if profile_name.strip():
        try:
            profile = load_profile(profile_name.strip())
            logger.info(f"Loaded profile: {profile.name}")
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Failed to load profile '{profile_name}': {e}")

    system_prompt = build_system_prompt(profile)

    event = load_event()
    issue_dict = build_issue_dict(event)

    logger.info(f"Assessing: {issue_dict['repo']} #{issue_dict['number']} — {issue_dict['title']}")

    llm_client = GitHubModelsClient(api_key=llm_token)
    analysis = assess_issue(issue_dict, llm_client, model, system_prompt=system_prompt)

    if not analysis:
        logger.warning("Assessment failed, exiting gracefully")
        _set_output("verdict", "error")
        return

    verdict = analysis.get("verdict", "")
    _set_output("verdict", verdict)
    _set_output("summary", analysis.get("summary", ""))

    if not meets_threshold(verdict, min_verdict):
        logger.info(f"Verdict '{verdict}' below threshold '{min_verdict}', skipping")
        return

    repo = issue_dict["repo"]
    number = issue_dict["number"]

    if profile and profile.label_map:
        label_name = profile.label_map.get(verdict)
        if label_name:
            if add_label(repo, number, github_token, label_name=label_name):
                _set_output("label", label_name)
        else:
            logger.info(f"Verdict '{verdict}' has no label in profile — comment only")
    else:
        if add_label(repo, number, github_token):
            _set_output("label", GOOD_FIRST_ISSUE_LABEL)

    post_comment(repo, number, analysis, github_token)
    logger.info(f"Done — {repo} #{number}: {verdict}")


if __name__ == "__main__":
    main()
