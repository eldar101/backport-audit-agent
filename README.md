# Backport Audit Agent

Backport Audit Agent is a deterministic CLI for release managers who need to verify
whether Jira bugs assigned to a fixVersion were backported to the matching GitHub
release branch.

This is an audit tool, not an auto-backport tool. It does not create cherry-picks or
backport pull requests.

## What It Checks

Given a Jira fixVersion, the CLI:

1. Queries Jira for bugs in that fixVersion.
2. Splits bugs into open/unresolved and closed/resolved.
3. Finds related GitHub pull requests from:
   - Jira remote links
   - Jira issue description
   - Jira issue comments
   - GitHub PR search by Jira key
4. Inspects merged PR commits and changed files.
5. Verifies whether the fix exists on the target release branch using local `git`.
6. Writes console, Markdown, JSON, and CSV reports.

## Verification Levels

The source of truth is Jira, GitHub, and local git history. LLM guessing is not used.

The verifier checks, in order:

1. The original merge commit is already an ancestor of the target branch.
2. The target branch has `git cherry-pick -x` evidence:
   `cherry picked from commit <sha>`.
3. A stable `git patch-id` from a PR commit exists on the target branch.
4. Target-branch commit messages mention the Jira key, PR number, PR URL, PR title,
   or original commit subject.
5. Target-branch commits touch the same changed files, which is marked for manual review.

## Statuses

- `OPEN_OR_UNRESOLVED`
- `CLOSED_NO_PR`
- `PR_NOT_MERGED`
- `BACKPORTED_CONFIRMED`
- `PROBABLY_BACKPORTED`
- `NOT_BACKPORTED`
- `MANUAL_REVIEW`
- `ERROR`

## Install

Use Python 3.10 or newer.

```bash
git clone https://github.com/eldar101/backport-audit-agent.git
cd backport-audit-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For development:

```bash
python -m pip install -e '.[dev]'
```

## Authentication

The CLI first tries to reuse existing credentials. If anything required is missing,
it prompts securely and does not save secrets to disk.

Credential discovery order:

1. Explicit CLI values, where available.
2. Environment variables.
3. Local CLI config:
   - GitHub: `gh auth token`
   - Jira: simple values from `JIRA_CONFIG_FILE`, `~/.config/.jira/.config.yml`,
     `~/.jira.d/config.yml`, `~/.jira/config.yml`, `~/.config/jira/config.yml`,
     or `~/.config/jira/config.yaml`
   - Jira token from `.netrc` for the configured Jira host
4. Interactive prompt.

Supported Jira environment variables:

```bash
JIRA_BASE_URL
JIRA_URL
JIRA_SERVER
ATLASSIAN_SITE
JIRA_USER
JIRA_EMAIL
JIRA_USERNAME
ATLASSIAN_EMAIL
JIRA_TOKEN
JIRA_API_TOKEN
JIRA_PERSONAL_ACCESS_TOKEN
ATLASSIAN_API_TOKEN
```

Supported GitHub environment variables:

```bash
GITHUB_TOKEN
GH_TOKEN
```

### Jira Cloud

Create an API token at:

```text
https://id.atlassian.com/manage-profile/security/api-tokens
```

Set:

```bash
export JIRA_BASE_URL='https://your-domain.atlassian.net'
export JIRA_USER='you@example.com'
export JIRA_TOKEN='your-jira-api-token'
```

If you use `ankitpokhrel/jira-cli`, the tool can reuse the Jira server/login from:

```text
~/.config/.jira/.config.yml
```

That CLI usually stores the API token in `.netrc` or expects `JIRA_API_TOKEN`.
This tool supports both. Example `.netrc` entry:

```text
machine your-domain.atlassian.net
  login you@example.com
  password your-jira-api-token
```

### Jira Data Center or Server

If your Jira uses Personal Access Tokens, omit `JIRA_USER` and set only:

```bash
export JIRA_BASE_URL='https://jira.example.com'
export JIRA_TOKEN='your-jira-personal-access-token'
```

When `JIRA_USER` is unset, the CLI uses:

```text
Authorization: Bearer <JIRA_TOKEN>
```

### GitHub

Create a GitHub token with read access to the target repository.

For public repos, a fine-grained token with repository read permissions is enough.
For private repos, grant access to the private repository.

If you already use the GitHub CLI, this is usually enough:

```bash
gh auth login
gh auth status
```

The tool will reuse `gh auth token` when `GITHUB_TOKEN` and `GH_TOKEN` are not set.

Set:

```bash
export GITHUB_TOKEN='github_pat_or_classic_token'
```

`GH_TOKEN` is also accepted.

## Usage

Quick run with existing auth:

```bash
backport-audit audit \
  --project PROJ \
  --fix-version 1.2.0-rc1 \
  --repo example/service
```

This reuses `gh auth token` for GitHub if no GitHub token env var is set. It also
tries Jira environment variables and common Jira CLI config files before prompting.

Basic run with an explicit Jira URL:

```bash
backport-audit audit \
  --jira-url https://jira.example.com \
  --project PROJ \
  --fix-version 1.2.0-rc1 \
  --repo example/service
```

By default, `1.2.0-rc1` maps to `release-1.2`. Use `--target-branch` when your
backport branch does not match that default.

By default, generated JQL matches all issues in the fixVersion:

```text
project = PROJ AND fixVersion in ("1.2.0-rc1")
```

If you only want a specific issue type, pass it explicitly:

```bash
backport-audit audit \
  --project PROJ \
  --fix-version 1.2.0-rc1 \
  --issue-type Bug \
  --repo example/service
```

The closed bucket uses `status = Closed` by default. Override it if your Jira
workflow uses another terminal status:

```bash
backport-audit audit \
  --project PROJ \
  --fix-version 1.2.0-rc1 \
  --closed-status Done \
  --repo example/service
```

To use the exact JQL that works in Jira:

```bash
backport-audit audit \
  --fix-version 1.2.0-rc1 \
  --jql 'project = PROJ AND fixVersion in ("1.2.0-rc1")' \
  --repo example/service
```

Override the target branch:

```bash
backport-audit audit \
  --fix-version 1.2.0-rc1 \
  --target-branch release-1.2 \
  --repo example/service \
  --project PROJ
```

Use a specific local clone directory for git verification:

```bash
backport-audit audit \
  --fix-version 1.2.0-rc1 \
  --repo example/service \
  --clone-dir /tmp/service-backport-audit
```

If `--clone-dir` is omitted, the tool clones or reuses:

```text
.cache/<owner>-<repo>
```

Reports are written to `reports/` by default:

```text
reports/backport-audit-1.2.0-rc1.md
reports/backport-audit-1.2.0-rc1.json
reports/backport-audit-1.2.0-rc1.csv
```

Override output location:

```bash
backport-audit audit \
  --fix-version 1.2.0-rc1 \
  --repo example/service \
  --output-dir /tmp/backport-report
```

## Example Summary

```text
FixVersion: 1.2.0-rc1
Target branch: release-1.2

Total bugs: 34
Closed bugs: 29
Open/unresolved: 5
Closed with PR: 24
Closed without PR: 5
Backported confirmed: 20
Probably backported: 2
Not backported: 2
Manual review: 5
```

## Notes and Limitations

- Jira Cloud search uses the enhanced `/rest/api/3/search/jql` endpoint. If that
  endpoint is unavailable, the tool falls back to legacy `/rest/api/2/search` for
  Jira Data Center or older Jira installations.
- `git patch-id` checks the latest 5000 non-merge commits on the target branch.
- Adapted backports may be marked `MANUAL_REVIEW` if the patch changed materially.
- The tool currently searches GitHub PRs by Jira key in the configured repo. If a Jira
  issue points to PRs in another repo, explicit GitHub PR URLs in Jira are still honored.
- For best audit accuracy, use `git cherry-pick -x` for backports and include Jira keys
  in PR titles or commit messages.
