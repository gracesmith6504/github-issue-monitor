import json
import logging
import os
import sys

import requests

from app.core.assessment import assess_issue
from app.core.llm import create_llm_client, resolve_model
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


def fetch_issue_from_api(repo, number, token):
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    url = f"https://api.github.com/repos/{repo}/issues/{number}"
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        logger.error(f"Failed to fetch issue #{number}: {resp.status_code} {resp.text[:200]}")
        return None
    issue = resp.json()

    repo_url = f"https://api.github.com/repos/{repo}"
    repo_resp = requests.get(repo_url, headers=headers, timeout=10)
    repo_language = repo_resp.json().get("language") if repo_resp.status_code == 200 else None

    return {
        "repo": repo,
        "number": issue["number"],
        "title": issue["title"],
        "body": issue.get("body") or "",
        "url": issue["html_url"],
        "labels": [l["name"] for l in issue.get("labels", [])],
        "comments": [],
        "repo_language": repo_language,
    }


def _set_output(key, value):
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"{key}={value}\n")


def main():
    github_token = os.environ.get("INPUT_GITHUB_TOKEN") or os.environ.get("INPUT_GITHUB-TOKEN")
    if not github_token:
        logger.error("github-token input is required")
        sys.exit(1)

    llm_provider = (os.environ.get("INPUT_LLM_PROVIDER") or os.environ.get("INPUT_LLM-PROVIDER") or "github").lower().strip()
    llm_token = os.environ.get("INPUT_LLM_TOKEN") or os.environ.get("INPUT_LLM-TOKEN") or ""
    llm_endpoint = os.environ.get("INPUT_LLM_ENDPOINT") or os.environ.get("INPUT_LLM-ENDPOINT") or ""
    model_override = os.environ.get("INPUT_LLM_MODEL") or os.environ.get("INPUT_LLM-MODEL") or ""
    anthropic_api_key = os.environ.get("INPUT_ANTHROPIC_API_KEY") or os.environ.get("INPUT_ANTHROPIC-API-KEY") or ""
    vertex_project_id = os.environ.get("INPUT_VERTEX_PROJECT_ID") or os.environ.get("INPUT_VERTEX-PROJECT-ID") or ""
    vertex_region = os.environ.get("INPUT_VERTEX_REGION") or os.environ.get("INPUT_VERTEX-REGION") or "us-east5"

    if llm_provider == "github" and not llm_token:
        logger.error("llm-token input is required when llm-provider is 'github' (the default)")
        sys.exit(1)

    model = resolve_model(llm_provider, model_override)
    min_verdict = (os.environ.get("INPUT_MIN_VERDICT") or os.environ.get("INPUT_MIN-VERDICT") or "STRETCH").upper()

    profile_name = os.environ.get("INPUT_REPO_PROFILE") or os.environ.get("INPUT_REPO-PROFILE") or ""
    profile = None
    if profile_name.strip():
        try:
            profile = load_profile(profile_name.strip())
            logger.info(f"Loaded profile: {profile.name}")
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Failed to load profile '{profile_name}': {e}")

    auto_label_override = (os.environ.get("INPUT_AUTO_LABEL") or os.environ.get("INPUT_AUTO-LABEL") or "").lower()
    if auto_label_override == "true" and profile:
        profile.auto_label = True

    system_prompt = build_system_prompt(profile)

    issue_number = os.environ.get("INPUT_ISSUE_NUMBER") or os.environ.get("INPUT_ISSUE-NUMBER") or ""
    event = load_event()

    if "issue" in event:
        issue_dict = build_issue_dict(event)
    elif issue_number.strip():
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if not repo:
            logger.error("GITHUB_REPOSITORY not set")
            sys.exit(1)
        issue_dict = fetch_issue_from_api(repo, int(issue_number.strip()), github_token)
        if not issue_dict:
            logger.error(f"Could not fetch issue #{issue_number}")
            return
    else:
        logger.error("No issue in event and no issue-number input provided")
        return

    logger.info(f"Assessing: {issue_dict['repo']} #{issue_dict['number']} — {issue_dict['title']}")

    if llm_provider == "anthropic":
        api_key = anthropic_api_key
        if not api_key:
            logger.error("anthropic-api-key input is required when llm-provider is 'anthropic'")
            sys.exit(1)
    elif llm_provider == "github":
        api_key = llm_token
    else:
        api_key = None

    llm_client = create_llm_client(
        provider=llm_provider,
        api_key=api_key,
        base_url=llm_endpoint or None,
        project_id=vertex_project_id or None,
        region=vertex_region,
    )
    analysis = assess_issue(issue_dict, llm_client, model, system_prompt=system_prompt, profile=profile)

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
        if label_name and profile.auto_label:
            if add_label(repo, number, github_token, label_name=label_name):
                _set_output("label", label_name)
            post_comment(repo, number, analysis, github_token)
        elif label_name:
            post_comment(repo, number, analysis, github_token, suggested_label=label_name)
        else:
            post_comment(repo, number, analysis, github_token)
    else:
        if add_label(repo, number, github_token):
            _set_output("label", GOOD_FIRST_ISSUE_LABEL)
        post_comment(repo, number, analysis, github_token)
    logger.info(f"Done — {repo} #{number}: {verdict}")


if __name__ == "__main__":
    main()
