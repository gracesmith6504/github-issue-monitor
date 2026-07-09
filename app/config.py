import os
import sys


def load_config():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN environment variable is required")
        sys.exit(1)

    watch_repos_raw = os.environ.get("WATCH_REPOS")
    if not watch_repos_raw:
        print("ERROR: WATCH_REPOS environment variable is required (comma-separated, e.g. NVIDIA/OpenShell,org/repo)")
        sys.exit(1)

    notify_repo = os.environ.get("NOTIFY_REPO")
    if not notify_repo:
        print("ERROR: NOTIFY_REPO environment variable is required (e.g. youruser/github-issue-monitor)")
        sys.exit(1)

    app_id = os.environ.get("GITHUB_APP_ID")
    if not app_id:
        print("ERROR: GITHUB_APP_ID environment variable is required")
        sys.exit(1)

    private_key_path = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH")
    private_key = os.environ.get("GITHUB_APP_PRIVATE_KEY")
    if private_key_path:
        with open(private_key_path) as f:
            private_key = f.read()
    if not private_key:
        print("ERROR: GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH environment variable is required")
        sys.exit(1)

    installation_id = os.environ.get("GITHUB_APP_INSTALLATION_ID")
    if not installation_id:
        print("ERROR: GITHUB_APP_INSTALLATION_ID environment variable is required")
        sys.exit(1)

    watch_repos = [r.strip() for r in watch_repos_raw.split(",") if r.strip()]
    if not watch_repos:
        print("ERROR: WATCH_REPOS must contain at least one repo")
        sys.exit(1)

    poll_interval = int(os.environ.get("POLL_INTERVAL", "30"))
    llm_model = os.environ.get("LLM_MODEL", "gpt-4o")

    return {
        "token": token,
        "watch_repos": watch_repos,
        "notify_repo": notify_repo,
        "poll_interval": poll_interval,
        "llm_model": llm_model,
        "app_id": app_id,
        "private_key": private_key,
        "installation_id": installation_id,
    }
