# GitHub Issue Monitor

**The problem:** You want to contribute to open source but the issues you can actually do get claimed before you even see them.

**The solution:** A bot that watches GitHub repos and emails you the moment a new issue appears that matches your skill level.

It polls every 30 seconds. An LLM reads the actual issue content — not labels, because people don't label things — and gives you:
- A plain English summary of the issue
- What the fix involves
- What skills you'd need
- A difficulty rating (easy / medium / hard)
- A verdict: **GO FOR IT**, **STRETCH**, or **NOT YET**

You only get emailed on GO FOR IT and STRETCH. Everything else is silently skipped.

Works on repos you don't own. No webhooks needed. Completely free.

---

## Setup Guide

This takes about 10 minutes. You'll need a GitHub account — that's it.

### Step 1: Clone this repo

This is the tool itself. Open your terminal and run:

```bash
git clone https://github.com/gracesmith6504/github-issue-monitor.git
cd github-issue-monitor
pip install -r requirements.txt
```

If `pip` doesn't work, try `pip3`.

### Step 2: Create a notification repo

This is a separate repo where the bot posts notifications. You want this separate so the tool's Issues tab stays clean.

1. Go to [github.com/new](https://github.com/new)
2. Name it `my-issue-alerts` (or whatever you like)
3. Set it to **Private** (only you can see your notifications)
4. Click **Create repository**

<!-- Screenshot: docs/images/create-repo.png -->

Now turn on email notifications for this repo:
1. Go to your new repo on GitHub
2. Click the **Watch** button (top right)
3. Select **Custom**
4. Tick **Issues** only
5. Click **Apply**

<!-- Screenshot: docs/images/watch-settings.png -->

### Step 3: Create a GitHub token

This is how the bot logs into GitHub to read issues and call the LLM.

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **Generate new token** → **Generate new token (classic)**
3. Name it `issue-monitor`
4. Tick the **`repo`** scope (the top-level checkbox)
5. Click **Generate token**
6. **Copy the token now** — you can't see it again after you leave this page

<!-- Screenshot: docs/images/create-token.png -->

### Step 4: Create a GitHub App

This is the clever bit. The bot needs its own identity so that when it creates a notification, GitHub knows *you* didn't create it — and sends you an email.

1. Go to [github.com/settings/apps/new](https://github.com/settings/apps/new)
2. Fill in these fields:

| Field | What to enter |
|---|---|
| **GitHub App name** | `issue-monitor-bot-YOURNAME` (must be unique on all of GitHub, so add your username) |
| **Homepage URL** | `https://github.com/gracesmith6504/github-issue-monitor` |

3. Scroll down to **Webhook** — **uncheck** "Active" (we don't use webhooks)
4. Scroll down to **Permissions** → **Repository permissions** → set **Issues** to **Read and write**
5. Leave everything else as default
6. Click **Create GitHub App**

<!-- Screenshot: docs/images/create-app.png -->

You'll land on the app's settings page. You need two things from here:

**Get the App ID:**
- It's shown near the top of the page, labelled "App ID"
- Write it down

**Get the private key:**
- Scroll to the bottom of the page
- Click **Generate a private key**
- A `.pem` file will download — save it somewhere safe (not inside this repo)

<!-- Screenshot: docs/images/app-id-and-key.png -->

### Step 5: Install the app on your notification repo

This gives the bot permission to create issues in your notification repo.

1. In the left sidebar of your app's settings, click **Install App**
2. Click **Install** next to your account
3. Select **Only select repositories**
4. Pick your notification repo (`my-issue-alerts` or whatever you named it in Step 2)
5. Click **Install**

<!-- Screenshot: docs/images/install-app.png -->

**Get the Installation ID:**
- After installing, look at the URL in your browser
- It looks like `https://github.com/settings/installations/12345678`
- The number at the end is your Installation ID — write it down

### Step 6: Run it

Put it all together. In your terminal:

```bash
cd github-issue-monitor

export GITHUB_TOKEN="ghp_paste_your_token_here"
export WATCH_REPOS="NVIDIA/OpenShell"
export NOTIFY_REPO="your-username/my-issue-alerts"
export GITHUB_APP_ID="your_app_id"
export GITHUB_APP_INSTALLATION_ID="your_installation_id"
export GITHUB_APP_PRIVATE_KEY_PATH="/path/to/your-downloaded-file.pem"

python -m app.main
```

Replace:
- `ghp_paste_your_token_here` with your token from Step 3
- `NVIDIA/OpenShell` with whatever repo you want to watch (or keep it — add more with commas: `NVIDIA/OpenShell,kubernetes/kubernetes`)
- `your-username/my-issue-alerts` with your notification repo from Step 2
- `your_app_id` with the App ID from Step 4
- `your_installation_id` with the Installation ID from Step 5
- `/path/to/your-downloaded-file.pem` with where your `.pem` file is (probably `~/Downloads/something.pem`)

You should see output like:

```
2026-07-09 12:00:00 INFO GitHub Issue Monitor starting up
2026-07-09 12:00:00 INFO Watching repos: NVIDIA/OpenShell
2026-07-09 12:00:00 INFO Notifications go to: your-username/my-issue-alerts
2026-07-09 12:00:01 INFO [NVIDIA/OpenShell] Found 1 new unassigned issue(s)
2026-07-09 12:00:01 INFO Analyzing: NVIDIA/OpenShell #1234 — Fix typo in README
2026-07-09 12:00:04 INFO [NVIDIA/OpenShell #1234] Verdict: GO FOR IT
2026-07-09 12:00:05 INFO Notification created: https://github.com/your-username/my-issue-alerts/issues/1
```

Press **Ctrl+C** to stop it.

### Step 7 (Optional): Watch multiple repos

Just add more repos separated by commas:

```bash
export WATCH_REPOS="NVIDIA/OpenShell,kubernetes/kubernetes,langchain-ai/langchain"
```

### Step 8 (Optional): Run 24/7 on OpenShift or Kubernetes

Instead of running on your laptop (which stops when you close it), deploy as a pod:

```bash
# Build the container
podman build -t quay.io/your-username/github-issue-monitor:latest .
podman push quay.io/your-username/github-issue-monitor:latest

# Deploy to your cluster
oc new-project issue-monitor
oc create secret generic issue-monitor-secret \
  --from-literal=GITHUB_TOKEN=ghp_... \
  --from-literal=GITHUB_APP_ID=... \
  --from-literal=GITHUB_APP_INSTALLATION_ID=... \
  --from-file=GITHUB_APP_PRIVATE_KEY=/path/to/key.pem
oc apply -f k8s/configmap.yaml
oc apply -f k8s/deployment.yaml
```

---

## Configuration Reference

| Variable | Required | Default | What it is |
|---|---|---|---|
| `GITHUB_TOKEN` | Yes | — | Your GitHub token from Step 3 |
| `WATCH_REPOS` | Yes | — | Repos to monitor, comma-separated |
| `NOTIFY_REPO` | Yes | — | Your private notification repo from Step 2 |
| `GITHUB_APP_ID` | Yes | — | App ID from Step 4 |
| `GITHUB_APP_INSTALLATION_ID` | Yes | — | Installation ID from Step 5 |
| `GITHUB_APP_PRIVATE_KEY_PATH` | Yes | — | Path to your `.pem` file from Step 4 |
| `POLL_INTERVAL` | No | `30` | Seconds between checks |
| `LLM_MODEL` | No | `gpt-4o` | Which LLM to use (via GitHub Models) |

## How It Works

1. Polls the GitHub Events API every 30 seconds for each repo you're watching
2. Uses ETags (a caching trick) so most polls are free and don't count against rate limits
3. When it finds a new unassigned issue, sends it to an LLM for assessment
4. If the verdict is GO FOR IT or STRETCH, creates a notification in your private repo
5. Because the GitHub App bot creates the issue (not you), GitHub sends you an email
6. If the verdict is NOT YET, it's silently skipped — no noise

## Costs

**Free.** GitHub API with ETags costs nothing. GitHub Models LLM is free. If you deploy to a cluster, the pod uses 64MB RAM — basically nothing.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ERROR: GITHUB_TOKEN environment variable is required` | You forgot to `export` one of the variables — check all 6 are set |
| `Failed to create notification: 403` | Your GitHub App isn't installed on the notification repo — redo Step 5 |
| `LLM analysis failed` | GitHub Models might be down — wait a few minutes and try again |
| Not getting emails | Make sure you're watching the notification repo with Custom → Issues (Step 2) |
| Getting too many NOT YET notifications | Update to the latest code — the filter was added after the first version |

## License

MIT
