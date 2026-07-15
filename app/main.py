import os
import time
import logging
from datetime import datetime, timezone

from app.config import load_config
from app.poller import Poller
from app.analyzer import analyze_issue
from app import notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_once(config, poller, run_start):
    for repo in config["watch_repos"]:
        new_issues = poller.poll(repo, config["last_checked"], config["notify_repo"],
                                 limit=config["max_issues_per_repo"])

        for i, issue in enumerate(new_issues):
            if i > 0:
                # Rate-limit delay for GitHub Models API
                time.sleep(config["analysis_delay"])
            logger.info(f"Analyzing: {issue['repo']} #{issue['number']} — {issue['title']}")

            analysis = analyze_issue(issue, config["monitor_token"], config["llm_model"])
            if not analysis:
                logger.warning(f"Skipping {issue['repo']} #{issue['number']} — analysis failed")
                continue

            if analysis.get("claimed"):
                logger.info(f"[{issue['repo']} #{issue['number']}] Skipping — claimed in comments")
                continue

            verdict = analysis.get("verdict", "")
            verdict_ranks = ["JUMP ON IT", "GO FOR IT", "STRETCH", "LONG SHOT", "NOT YET"]
            min_verdict = config.get("min_verdict", "STRETCH")
            if verdict in verdict_ranks and min_verdict in verdict_ranks:
                if verdict_ranks.index(verdict) > verdict_ranks.index(min_verdict):
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

    if os.environ.get("RUN_ONCE") == "true":
        logger.info("Running single pass (GitHub Actions mode)")
        run_start = datetime.now(timezone.utc).isoformat()
        run_once(config, poller, run_start)
    else:
        logger.info(f"Poll interval: {config['poll_interval']}s")
        while True:
            run_start = datetime.now(timezone.utc).isoformat()
            run_once(config, poller, run_start)
            config["last_checked"] = run_start
            time.sleep(config["poll_interval"])


if __name__ == "__main__":
    main()
