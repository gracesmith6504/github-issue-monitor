import time
import logging

from app.config import load_config
from app.poller import Poller
from app.analyzer import analyze_issue
from app.notifier import notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    config = load_config()

    logger.info("GitHub Issue Monitor starting up")
    logger.info(f"Watching repos: {', '.join(config['watch_repos'])}")
    logger.info(f"Notifications go to: {config['notify_repo']}")
    logger.info(f"Poll interval: {config['poll_interval']}s")
    logger.info(f"LLM model: {config['llm_model']}")

    poller = Poller(config["token"])

    while True:
        for repo in config["watch_repos"]:
            new_issues = poller.poll(repo)

            for issue in new_issues:
                logger.info(f"Analyzing: {issue['repo']} #{issue['number']} — {issue['title']}")

                analysis = analyze_issue(issue, config["token"], config["llm_model"])
                if not analysis:
                    logger.warning(f"Skipping {issue['repo']} #{issue['number']} — analysis failed")
                    continue

                notify(issue, analysis, config["notify_repo"],
                       config["app_id"], config["private_key"], config["installation_id"])

        time.sleep(config["poll_interval"])


if __name__ == "__main__":
    main()
