import os
import sys
from datetime import datetime, timedelta, timezone


def load_config():
    monitor_token = os.environ.get("MONITOR_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not monitor_token:
        print("ERROR: MONITOR_TOKEN environment variable is required")
        sys.exit(1)

    notify_token = os.environ.get("NOTIFY_TOKEN") or os.environ.get("GITHUB_TOKEN") or monitor_token

    watch_repos_raw = os.environ.get("WATCH_REPOS")
    if not watch_repos_raw:
        print("ERROR: WATCH_REPOS environment variable is required (comma-separated, e.g. NVIDIA/OpenShell,org/repo)")
        sys.exit(1)

    notify_repo = os.environ.get("NOTIFY_REPO")
    if not notify_repo:
        print("ERROR: NOTIFY_REPO environment variable is required (e.g. youruser/github-issue-monitor)")
        sys.exit(1)

    watch_repos = [r.strip() for r in watch_repos_raw.split(",") if r.strip()]
    if not watch_repos:
        print("ERROR: WATCH_REPOS must contain at least one repo")
        sys.exit(1)

    poll_interval = int(os.environ.get("POLL_INTERVAL", "30"))
    llm_model = os.environ.get("LLM_MODEL", "gpt-4o")
    min_verdict = os.environ.get("MIN_VERDICT", "STRETCH").upper()
    max_issues_per_repo = int(os.environ.get("MAX_ISSUES_PER_REPO", "20"))
    analysis_delay = int(os.environ.get("ANALYSIS_DELAY", "7"))

    last_checked_raw = os.environ.get("LAST_CHECKED")
    if last_checked_raw:
        last_checked = last_checked_raw
    else:
        last_checked = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()

    config = {
        "monitor_token": monitor_token,
        "notify_token": notify_token,
        "watch_repos": watch_repos,
        "notify_repo": notify_repo,
        "poll_interval": poll_interval,
        "llm_model": llm_model,
        "min_verdict": min_verdict,
        "last_checked": last_checked,
        "max_issues_per_repo": max_issues_per_repo,
        "analysis_delay": analysis_delay,
    }

    app_id = os.environ.get("GITHUB_APP_ID")
    if app_id:
        private_key_path = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH")
        private_key = os.environ.get("GITHUB_APP_PRIVATE_KEY")
        if private_key_path:
            with open(private_key_path) as f:
                private_key = f.read()
        if not private_key:
            print("ERROR: GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH required when GITHUB_APP_ID is set")
            sys.exit(1)

        installation_id = os.environ.get("GITHUB_APP_INSTALLATION_ID")
        if not installation_id:
            print("ERROR: GITHUB_APP_INSTALLATION_ID required when GITHUB_APP_ID is set")
            sys.exit(1)

        config["app_id"] = app_id
        config["private_key"] = private_key
        config["installation_id"] = installation_id

    return config
