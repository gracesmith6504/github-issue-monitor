# GitHub Issue Monitor

Monitor any GitHub repo for new unassigned issues. Each issue gets an LLM-powered assessment (summary, difficulty, skills needed, go/no-go verdict) delivered as a GitHub notification issue — which means you get an email automatically.

Works on repos you don't own. No webhooks needed. Polls every 30 seconds using ETags so it's virtually free on rate limits.

## Quick Start

### 1. Create a GitHub PAT

Go to [github.com/settings/tokens](https://github.com/settings/tokens) and create a token with these scopes:
- `repo` (to create notification issues)
- `models` (to use GitHub Models for LLM analysis)

### 2. Run locally

```bash
git clone https://github.com/gracesmith6504/github-issue-monitor.git
cd github-issue-monitor
pip install -r requirements.txt

export GITHUB_TOKEN="ghp_your_token_here"
export WATCH_REPOS="NVIDIA/OpenShell"
export NOTIFY_REPO="your-username/github-issue-monitor"

python -m app.main
```

### 3. (Optional) Deploy to OpenShift/Kubernetes

```bash
# Build and push the container
podman build -t quay.io/your-username/github-issue-monitor:latest .
podman push quay.io/your-username/github-issue-monitor:latest

# Deploy
oc new-project issue-monitor
oc create secret generic github-token --from-literal=GITHUB_TOKEN=ghp_...
# Edit k8s/configmap.yaml with your repos
oc apply -f k8s/configmap.yaml
oc apply -f k8s/deployment.yaml
```

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT with `repo` + `models` scopes |
| `WATCH_REPOS` | Yes | — | Comma-separated repos to monitor (e.g. `NVIDIA/OpenShell,org/repo`) |
| `NOTIFY_REPO` | Yes | — | Repo where notification issues are created |
| `POLL_INTERVAL` | No | `30` | Seconds between polls |
| `LLM_MODEL` | No | `gpt-4o` | GitHub Models model to use for analysis |

## How It Works

1. Polls the GitHub Events API for each watched repo every 30 seconds
2. Uses ETags so unchanged responses don't count against rate limits
3. Filters for new `IssuesEvent` with `action: "opened"` and no assignee
4. Sends the issue to an LLM (via GitHub Models, free) for assessment
5. Creates a notification issue in your repo with the analysis
6. GitHub emails you automatically because you own the notification repo
7. Dedup check prevents duplicate notifications on restarts

## Notification Format

Each notification issue includes:
- Link to the original issue
- Plain English summary
- What the fix involves
- Skills needed
- Difficulty rating (easy/medium/hard)
- Verdict: **GO FOR IT** / **STRETCH** / **NOT YET**
- Color-coded labels for quick scanning

## License

MIT
