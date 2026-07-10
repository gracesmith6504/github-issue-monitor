# GitHub Issue Monitor

**The problem:** You want to contribute to open source but the issues you can actually do get claimed before you even see them.

**The solution:** A bot that watches GitHub repos and emails you the moment a new issue appears that matches your skill level.

An LLM reads the actual issue content and asks: **does this issue give a newcomer a clear enough starting point that they and Claude Code could figure it out?**

It gives you:
- A plain English summary of the issue
- What the fix likely involves (specific files/functions if mentioned)
- What skills you'd need
- A difficulty rating (easy / medium / hard)
- A verdict — one of five levels:

| Verdict | Meaning |
|---|---|
| **JUMP ON IT** | Clear starting point, straightforward fix. Claim it before someone else does. |
| **GO FOR IT** | Clear starting point, harder fix — Claude Code can guide you through it. |
| **STRETCH** | Vague starting point but enough context to investigate with Claude. Worth attempting. |
| **LONG SHOT** | Very little direction. Real risk of getting stuck. Only if you're feeling adventurous. |
| **NOT YET** | No clear entry point. Needs deep architectural knowledge. Skip this one. |

You get notified on JUMP ON IT, GO FOR IT, and STRETCH. LONG SHOT and NOT YET are silently skipped.

Works on repos you don't own. No webhooks needed. Completely free.

---

## Quick Setup (GitHub Actions) — 2 minutes

No server, no terminal, no installs. GitHub runs it for you every 5 minutes.

### 1. Fork this repo

Click the **Fork** button at the top of this page.

### 2. Add your GitHub token

Your fork needs a token to call the LLM and create notification issues.

1. Create a token: [github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)** → tick **`repo`** → **Generate token** → copy it
2. In your fork, go to **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
3. Name: `MONITOR_TOKEN`, Value: paste your token

### 3. Set which repos to watch

1. In your fork, go to **Settings** → **Secrets and variables** → **Actions** → **Variables** tab → **New repository variable**
2. Name: `WATCH_REPOS`, Value: `NVIDIA/OpenShell` (or any repos you want, comma-separated)

### 4. Enable the workflow

1. In your fork, go to the **Actions** tab
2. Click **I understand my workflows, go ahead and enable them**
3. Click **Issue Monitor** in the left sidebar
4. Click **Enable workflow**

### 5. Watch your fork for notifications

1. Go to your fork's main page
2. Click **Watch** (top right) → **Custom** → tick **Issues** → **Apply**

That's it. Every 5 minutes, GitHub checks your watched repos for new unassigned issues, analyzes them with an LLM, and creates a notification issue in your fork if one is suitable. You get an email because `github-actions[bot]` creates the issue, not you.

You can also click **Run workflow** in the Actions tab to test it immediately.

---

## Full Setup (30-second polling) — 10 minutes

For faster detection, run the Python app yourself. Polls every 30 seconds instead of every 5 minutes. Can be deployed on OpenShift/Kubernetes to run 24/7.

This requires a **GitHub App** so the bot has its own identity (otherwise GitHub won't email you about issues you created yourself).

### Step 1: Clone this repo

```bash
git clone https://github.com/gracesmith6504/github-issue-monitor.git
cd github-issue-monitor
pip install -r requirements.txt
```

If `pip` doesn't work, try `pip3`.

### Step 2: Create a notification repo

A separate private repo where the bot posts notifications. Keeps the tool's Issues tab clean.

1. Go to [github.com/new](https://github.com/new)
2. Name it `my-issue-alerts` (or whatever you like)
3. Set it to **Private**
4. Click **Create repository**

Turn on email notifications:
1. Go to your new repo on GitHub
2. Click **Watch** (top right) → **Custom** → tick **Issues** → **Apply**

### Step 3: Create a GitHub token

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **Generate new token** → **Generate new token (classic)**
3. Name it `issue-monitor`, tick **`repo`**, click **Generate token**
4. **Copy the token now** — you can't see it again

### Step 4: Create a GitHub App

The bot needs its own identity so GitHub emails you when it creates a notification.

1. Go to [github.com/settings/apps/new](https://github.com/settings/apps/new)
2. **Name:** `issue-monitor-bot-YOURNAME` (must be globally unique)
3. **Homepage URL:** `https://github.com/gracesmith6504/github-issue-monitor`
4. **Webhook:** uncheck "Active"
5. **Permissions** → **Repository permissions** → **Issues:** Read and write
6. Click **Create GitHub App**
7. Note the **App ID** at the top of the page
8. Scroll down → **Generate a private key** (downloads a `.pem` file)

### Step 5: Install the app on your notification repo

1. In your app's settings → **Install App** → **Install** on your account
2. Select **Only select repositories** → pick your notification repo
3. Click **Install**
4. Note the **Installation ID** from the URL: `https://github.com/settings/installations/XXXXX`

### Step 6: Run it

```bash
export GITHUB_TOKEN="ghp_your_token"
export WATCH_REPOS="NVIDIA/OpenShell"
export NOTIFY_REPO="your-username/my-issue-alerts"
export GITHUB_APP_ID="your_app_id"
export GITHUB_APP_INSTALLATION_ID="your_installation_id"
export GITHUB_APP_PRIVATE_KEY_PATH="/path/to/your-key.pem"

python -m app.main
```

Watch multiple repos by adding commas: `NVIDIA/OpenShell,kubernetes/kubernetes`

Press **Ctrl+C** to stop.

### Step 7 (Optional): Run 24/7 on OpenShift/Kubernetes

```bash
podman build -t quay.io/your-username/github-issue-monitor:latest .
podman push quay.io/your-username/github-issue-monitor:latest

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

## How It Works

1. Polls the GitHub Events API for each repo you're watching
2. Uses ETags (a caching trick) so most polls don't count against rate limits
3. When it finds a new unassigned issue, checks its labels — `good first issue` is an instant strong signal
4. Sends the issue to an LLM (GitHub Models, free) which asks: does this give a newcomer a clear starting point? Could they tackle it with Claude Code?
5. If the verdict is JUMP ON IT, GO FOR IT, or STRETCH — creates a notification issue in your alerts repo
6. LONG SHOT and NOT YET are silently skipped — no noise
7. GitHub emails you because a bot created the issue, not you

## Costs

**Free.** GitHub API, GitHub Models LLM, and GitHub Actions are all free. If you deploy to a cluster, the pod uses 64MB RAM.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ERROR: GITHUB_TOKEN environment variable is required` | You forgot to `export` one of the variables |
| `Failed to create notification: 403` | GitHub App isn't installed on the notification repo |
| `LLM analysis failed` | GitHub Models might be down — wait and retry |
| Not getting emails | Watch the notification repo: Custom → Issues |
| Actions workflow not running | Go to Actions tab and enable it |

## License

MIT
