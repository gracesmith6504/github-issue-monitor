# GitHub Issue Monitor

A bot that watches GitHub repos and emails you the moment a new issue appears that matches your skill level.

Works on repos you don't own. No webhooks needed. Polls every 30 seconds using ETags so it's virtually free on rate limits. An LLM reads the actual issue content — not labels — and gives you a difficulty rating and a GO FOR IT / STRETCH / NOT YET verdict. You only get emailed on issues you can actually tackle.

## Setup (10 minutes)

### Step 1: Fork this repo

Click **Fork** at the top of this page. This is where your notification issues will appear.

### Step 2: Create a GitHub PAT

Go to [github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)**

Select these scopes:
- `repo`

Name it `issue-monitor`, click **Generate token**, copy it.

### Step 3: Create a GitHub App

This is needed so the bot creates issues as itself (not as you), which triggers email notifications.

1. Go to [github.com/settings/apps/new](https://github.com/settings/apps/new)
2. Fill in:
   - **Name:** `issue-monitor-bot-yourname` (must be unique)
   - **Homepage URL:** your fork's URL
   - **Webhook:** uncheck "Active"
3. Under **Permissions** → **Repository permissions**:
   - **Issues:** Read and write
4. Under **Where can this GitHub App be installed?**: select **Only on this account**
5. Click **Create GitHub App**
6. Note the **App ID** at the top of the page
7. Scroll down → **Generate a private key** (downloads a `.pem` file)

### Step 4: Install the app on your fork

1. Go to `https://github.com/settings/apps/YOUR-APP-NAME/installations`
2. Click **Install**
3. Select your account
4. Choose **Only select repositories** → pick your fork
5. Click **Install**
6. Note the **Installation ID** from the URL: `https://github.com/settings/installations/XXXXX`

### Step 5: Run it

```bash
git clone https://github.com/YOUR-USERNAME/github-issue-monitor.git
cd github-issue-monitor
pip install -r requirements.txt

export GITHUB_TOKEN="ghp_your_token"
export WATCH_REPOS="NVIDIA/OpenShell"
export NOTIFY_REPO="your-username/github-issue-monitor"
export GITHUB_APP_ID="your_app_id"
export GITHUB_APP_INSTALLATION_ID="your_installation_id"
export GITHUB_APP_PRIVATE_KEY_PATH="/path/to/your-private-key.pem"

python -m app.main
```

You should see it start polling. When it finds a suitable issue, a notification appears in your repo's Issues tab and you get an email.

### Step 6 (Optional): Deploy to OpenShift/Kubernetes

Run it 24/7 as a pod instead of on your laptop.

```bash
# Build and push the container
podman build -t quay.io/your-username/github-issue-monitor:latest .
podman push quay.io/your-username/github-issue-monitor:latest

# Deploy
oc new-project issue-monitor
oc create secret generic github-token \
  --from-literal=GITHUB_TOKEN=ghp_... \
  --from-literal=GITHUB_APP_ID=... \
  --from-literal=GITHUB_APP_INSTALLATION_ID=... \
  --from-file=GITHUB_APP_PRIVATE_KEY=/path/to/key.pem
oc apply -f k8s/configmap.yaml
oc apply -f k8s/deployment.yaml
```

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT with `repo` scope |
| `WATCH_REPOS` | Yes | — | Comma-separated repos to monitor (e.g. `NVIDIA/OpenShell,org/repo`) |
| `NOTIFY_REPO` | Yes | — | Your fork where notification issues are created |
| `GITHUB_APP_ID` | Yes | — | Your GitHub App's ID |
| `GITHUB_APP_INSTALLATION_ID` | Yes | — | Installation ID from Step 4 |
| `GITHUB_APP_PRIVATE_KEY_PATH` | Yes | — | Path to your `.pem` file (or set `GITHUB_APP_PRIVATE_KEY` with the key contents directly) |
| `POLL_INTERVAL` | No | `30` | Seconds between polls |
| `LLM_MODEL` | No | `gpt-4o` | GitHub Models model to use |

## How It Works

1. Polls the GitHub Events API for each watched repo every 30 seconds
2. Uses ETags so unchanged responses don't count against rate limits
3. Filters for new issues that are unassigned
4. Sends the issue to an LLM (via GitHub Models, free) for assessment
5. Only notifies on GO FOR IT and STRETCH verdicts (skips NOT YET)
6. Creates a notification issue in your repo via the GitHub App bot
7. GitHub emails you because the bot (not you) created the issue
8. Dedup check prevents duplicate notifications on restarts

## What You Get

Each notification includes:
- Link to the original issue
- Plain English summary
- What the fix involves
- Skills needed
- Difficulty rating (easy/medium/hard)
- Verdict: **GO FOR IT** or **STRETCH**
- Color-coded labels for quick scanning

## Costs

Nothing. GitHub API with ETags is free. GitHub Models LLM is free. The pod uses 64MB RAM.

## License

MIT
