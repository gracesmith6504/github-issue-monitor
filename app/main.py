import os
import time
import logging
import requests
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


def _update_last_checked(token, notify_repo, run_start):
    owner, repo = notify_repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/variables/LAST_CHECKED"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    payload = {"name": "LAST_CHECKED", "value": run_start}
    resp = requests.patch(url, headers=headers, json=payload, timeout=10)
    if resp.status_code == 404:
        requests.post(
            f"https://api.github.com/repos/{owner}/{repo}/actions/variables",
            headers=headers, json=payload, timeout=10,
        )
        logger.info("LAST_CHECKED variable created")
    elif resp.status_code in (200, 204):
        logger.info(f"LAST_CHECKED updated to {run_start}")
    else:
        logger.warning(f"Failed to update LAST_CHECKED: {resp.status_code} {resp.text[:200]}")


def run_once(config, poller, run_start):
    for repo in config["watch_repos"]:
        new_issues = poller.poll(repo, config["last_checked"], config["notify_repo"])

        for issue in new_issues:
            logger.info(f"Analyzing: {issue['repo']} #{issue['number']} — {issue['title']}")

            analysis = analyze_issue(issue, config["monitor_token"], config["llm_model"])
            if not analysis:
                logger.warning(f"Skipping {issue['repo']} #{issue['number']} — analysis failed")
                continue

            verdict = analysis.get("verdict", "")
            if verdict in ("LONG SHOT", "NOT YET"):
                logger.info(f"[{issue['repo']} #{issue['number']}] Verdict: {verdict} — skipping notification")
                continue

            if config.get("app_id"):
                notifier.notify(issue, analysis, config["notify_repo"],
                                config["app_id"], config["private_key"], config["installation_id"])
            else:
                notifier.notify_simple(issue, analysis, config["notify_repo"], config["notify_token"])

    _update_last_checked(config["monitor_token"], config["notify_repo"], run_start)


def main():
    config = load_config()

    logger.info("GitHub Issue Monitor starting up")
    logger.info(f"Watching repos: {', '.join(config['watch_repos'])}")
    logger.info(f"Notifications go to: {config['notify_repo']}")
    logger.info(f"LLM model: {config['llm_model']}")
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
            time.sleep(config["poll_interval"])


if __name__ == "__main__":
    main()
