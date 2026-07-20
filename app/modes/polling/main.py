import os
import time
import logging
from datetime import datetime, timezone

from app.core.assessment import assess_issue
from app.core.llm import create_llm_client, resolve_model
from app.core.profiles import find_profile_for_repo
from app.core.prompt import build_system_prompt
from app.core.verdict import meets_threshold
from app.modes.polling.config import load_config
from app.modes.polling.poller import Poller
from app.modes.polling import notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_once(config, poller, llm_client):
    for repo in config["watch_repos"]:
        profile = find_profile_for_repo(repo)
        if profile:
            logger.info(f"[{repo}] Using profile: {profile.name}")
        system_prompt = build_system_prompt(profile)

        new_issues = poller.poll(repo, config["last_checked"], config["notify_repo"],
                                 limit=config["max_issues_per_repo"])

        for i, issue in enumerate(new_issues):
            if i > 0:
                time.sleep(config["analysis_delay"])
            logger.info(f"Analyzing: {issue['repo']} #{issue['number']} — {issue['title']}")

            analysis = assess_issue(issue, llm_client, config["_resolved_model"],
                                    system_prompt=system_prompt, profile=profile)
            if not analysis:
                logger.warning(f"Skipping {issue['repo']} #{issue['number']} — analysis failed")
                continue

            if analysis.get("claimed"):
                logger.info(f"[{issue['repo']} #{issue['number']}] Skipping — claimed in comments")
                continue

            verdict = analysis.get("verdict", "")
            min_verdict = config.get("min_verdict", "STRETCH")
            if not meets_threshold(verdict, min_verdict):
                logger.info(f"[{issue['repo']} #{issue['number']}] Verdict: {verdict} — below {min_verdict} threshold, skipping")
                continue

            if config.get("app_id"):
                notifier.notify(issue, analysis, config["notify_repo"],
                                config["app_id"], config["private_key"], config["installation_id"])
            else:
                notifier.notify_simple(issue, analysis, config["notify_repo"], config["notify_token"])


def main():
    config = load_config()

    logger.info("GitHub Issue Monitor starting up")
    logger.info(f"Watching repos: {', '.join(config['watch_repos'])}")
    logger.info(f"Notifications go to: {config['notify_repo']}")
    provider = config["llm_provider"]
    config["_resolved_model"] = resolve_model(provider, config["llm_model"])
    logger.info(f"LLM provider: {provider}")
    logger.info(f"LLM model: {config['_resolved_model']}")
    logger.info(f"Min verdict: {config['min_verdict']}")
    logger.info(f"Checking issues since: {config['last_checked']}")

    poller = Poller(config["monitor_token"])
    llm_client = create_llm_client(
        provider=provider,
        api_key=config.get("anthropic_api_key") if provider == "anthropic" else config.get("llm_token") or config["monitor_token"],
        base_url=config.get("llm_endpoint") or None,
        project_id=config.get("vertex_project_id") or None,
        region=config.get("vertex_region", "us-east5"),
    )

    if os.environ.get("RUN_ONCE") == "true":
        logger.info("Running single pass (GitHub Actions mode)")
        run_once(config, poller, llm_client)
    else:
        logger.info(f"Poll interval: {config['poll_interval']}s")
        while True:
            run_start = datetime.now(timezone.utc).isoformat()
            run_once(config, poller, llm_client)
            config["last_checked"] = run_start
            time.sleep(config["poll_interval"])


if __name__ == "__main__":
    main()
