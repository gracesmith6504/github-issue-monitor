import os
import time
import logging
from datetime import datetime, timezone

from app.core.assessment import assess_issue
from app.core.llm import GitHubModelsClient
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


def run_once(config, poller, llm_client, run_start):
    for repo in config["watch_repos"]:
        new_issues = poller.poll(repo, config["last_checked"], config["notify_repo"],
                                 limit=config["max_issues_per_repo"])

        for i, issue in enumerate(new_issues):
            if i > 0:
                time.sleep(config["analysis_delay"])
            logger.info(f"Analyzing: {issue['repo']} #{issue['number']} — {issue['title']}")

            analysis = assess_issue(issue, llm_client, config["llm_model"])
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
    logger.info(f"LLM model: {config['llm_model']}")
    logger.info(f"Min verdict: {config['min_verdict']}")
    logger.info(f"Checking issues since: {config['last_checked']}")

    poller = Poller(config["monitor_token"])
    llm_client = GitHubModelsClient(api_key=config["monitor_token"])

    if os.environ.get("RUN_ONCE") == "true":
        logger.info("Running single pass (GitHub Actions mode)")
        run_start = datetime.now(timezone.utc).isoformat()
        run_once(config, poller, llm_client, run_start)
    else:
        logger.info(f"Poll interval: {config['poll_interval']}s")
        while True:
            run_start = datetime.now(timezone.utc).isoformat()
            run_once(config, poller, llm_client, run_start)
            config["last_checked"] = run_start
            time.sleep(config["poll_interval"])


if __name__ == "__main__":
    main()
