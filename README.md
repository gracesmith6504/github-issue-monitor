# GitHub Issue Monitor

An LLM-powered tool that finds GitHub issues suitable for newcomers. It rates each issue on how clear the fix is, how contained the scope is, and how much domain knowledge is needed — then tells you whether to go for it.

Each assessment includes a plain English summary, what the fix likely involves, skills needed, and a verdict:

| | Verdict | Score | Meaning |
|---|---|---|---|
| 🟢 | **JUMP ON IT** | 13-15 | The fix is spelled out. Anyone can do this. |
| 🔵 | **GO FOR IT** | 10-12 | Clear path, contained scope. |
| 🟡 | **STRETCH** | 7-9 | Doable but needs some domain knowledge. |
| 🟠 | **LONG SHOT** | 5-6 | Needs domain expertise. |
| 🔴 | **NOT YET** | 3-4 | Deep architectural knowledge required. |

By default, only STRETCH or above get notified. You can change this with `MIN_VERDICT`.

---

## Polling Mode — Get emailed when good issues appear

Fork this repo and it watches repos for new and reclaimed issues, analyses them, and emails you the ones worth working on — even when your laptop is off.

It also detects **reclaimed issues** — previously claimed but then abandoned (unassigned, PR closed without merge, etc.). These show up with `[RECLAIMED]` in the subject line.

![Email notification example](docs/email-example.png)

### Quick Setup — 2 minutes

#### 1. Fork this repo

Click the **Fork** button at the top of this page.

#### 2. Set which repos to watch

1. In your fork: **Settings** → **Secrets and variables** → **Actions** → **Variables** tab → **New repository variable**
2. Name: `WATCH_REPOS`, Value: everything after `github.com/` in the repo URL — for example:
   - `https://github.com/NVIDIA/OpenShell` → `NVIDIA/OpenShell`
   - `https://github.com/kagenti/kagenti-operator` → `kagenti/kagenti-operator`
   - Multiple repos: `NVIDIA/OpenShell,kagenti/kagenti-operator`

> **Important:** This goes under the **Variables** tab, not Secrets — they're on the same page but different tabs. If you add it as a Secret it will silently not work.

#### 3. Enable the workflow

In your fork: **Actions** tab → **I understand my workflows, go ahead and enable them** → Click **Issue Monitor** in the sidebar → **Enable workflow**

#### 4. Subscribe to email notifications

In your fork: Click **Watch** (top right) → **All Activity** → **Apply**

That's it. GitHub runs the monitor every hour, analyses new and updated issues, and creates a notification in your fork's Issues tab. You get an email because `github-actions[bot]` opens it, not you.

> **Want to change the frequency?** Edit `.github/workflows/monitor.yml` in your fork and change the cron line. For example, `'*/5 * * * *'` for every 5 minutes. GitHub Actions minimum is 5 minutes.

### Optional settings

Add these as repository **Variables** (same place as `WATCH_REPOS`):

| Variable | What it does |
|---|---|
| `MIN_VERDICT` | Minimum verdict to notify you. Default: `STRETCH`. Set to `GO FOR IT` for fewer notifications. |
| `NOTIFY_REPO` | Send notifications to a different repo instead of your fork. Requires `MONITOR_TOKEN` secret with a PAT. |

---

## Action Mode — Auto-label issues on any repo

Install this on a repo and every new issue gets assessed automatically. Newcomer-friendly issues get the `good first issue` label and a detailed comment.

### Setup

1. Add an `LLM_TOKEN` secret to the target repo (Settings → Secrets → Actions) — your GitHub token works for [GitHub Models](https://github.com/marketplace/models). See [LLM Providers](#llm-providers) for other options.

2. Create `.github/workflows/newcomer-assess.yml`:

```yaml
name: Assess newcomer-friendliness

on:
  issues:
    types: [opened]

permissions:
  issues: write

jobs:
  assess:
    runs-on: ubuntu-latest
    steps:
      - uses: gracesmith6504/github-issue-monitor@main
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          llm-token: ${{ secrets.LLM_TOKEN }}
```

### Action inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `github-token` | Yes | — | Token with `issues:write` permission |
| `llm-provider` | No | `github` | `github`, `anthropic`, or `vertex` ([details](#llm-providers)) |
| `llm-token` | Depends | — | API key for the LLM (required for `github` provider) |
| `llm-model` | No | *(auto)* | LLM model (auto-selected per provider) |
| `anthropic-api-key` | Depends | — | Required for `anthropic` provider |
| `vertex-project-id` | Depends | — | Required for `vertex` provider |
| `vertex-region` | No | `us-east5` | Vertex AI region |
| `min-verdict` | No | `STRETCH` | Minimum verdict to apply the label |
| `repo-profile` | No | — | Repo profile for calibrated assessment (e.g. `openshell`) |

---

## LLM Providers

You can configure which LLM the monitor uses. **GitHub Models is the default** — no extra setup needed.

| Provider | What it is | Auth |
|---|---|---|
| `github` (default) | [GitHub Models](https://github.com/marketplace/models) — OpenAI-compatible | Your GitHub token (already set up) |
| `anthropic` | [Anthropic API](https://console.anthropic.com/) — Claude directly | Anthropic API key |
| `vertex` | Claude via [Google Vertex AI](https://cloud.google.com/vertex-ai) | Google Cloud service account |

### Switching providers

Set `LLM_PROVIDER` as a repository **Variable**. The model is auto-selected — you only need `LLM_MODEL` if you want to override it.

| `LLM_PROVIDER` | Default model |
|---|---|
| `github` | `gpt-4o` |
| `anthropic` | `claude-sonnet-4-6` |
| `vertex` | `claude-sonnet-4-6` |

### Provider: `github` (default)

No extra setup. Your GitHub token works as the API key.

### Provider: `anthropic`

Add `LLM_PROVIDER=anthropic` as a repository **Variable** and `ANTHROPIC_API_KEY` as a repository **Secret**.

### Provider: `vertex`

Uses Claude via Google Vertex AI. Authenticates with a Google Cloud service account — no API key needed. You need access to a GCP project with Vertex AI enabled.

**Setup:** Ask Claude Code:

> Set up Vertex AI as the LLM provider for my github-issue-monitor fork. I need a GCP service account key, GitHub secret, and repo variables.

It will walk you through everything.

---

## How It Works

1. **Assessment engine** — sends the issue title, body, labels, and comments to a [configurable LLM](#llm-providers) which scores it on three axes (starting point, scope, familiarity). Scores are 1-5 each, summed for the verdict.
2. **Repo profiles** — optional YAML configs in `profiles/` inject repo-specific calibration into the LLM prompt.
3. **Claimed detection** — checks for assignment, linked PRs, fork activity, and comment patterns ("I'll work on this") to skip issues someone is already working on.
4. **Action mode** adds a label and posts a detailed assessment comment on the issue.
5. **Polling mode** creates a notification issue in your fork (GitHub emails you).

## Troubleshooting

| Problem | Fix |
|---|---|
| `WATCH_REPOS environment variable is required` | You added `WATCH_REPOS` as a Secret instead of a Variable — move it to the **Variables** tab |
| `LLM analysis failed` | LLM endpoint might be down or rate-limited — wait and retry |
| `No module named 'anthropic'` | Install the SDK: `pip install 'anthropic[vertex]>=0.39.0'` |
| Not getting emails | Watch the repo with **All Activity** (not Custom) |
| No notifications appearing | The watched repos might not have had new issues recently |
| Actions workflow not running | Go to Actions tab and enable it |

## Development

```bash
git clone https://github.com/YOUR-USERNAME/github-issue-monitor.git
cd github-issue-monitor
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

## License

MIT
