# Backport Audit Agent

Small CLI tool that checks Jira issues in a fixVersion and reports whether their
GitHub PRs made it into a release branch.

It does not create backports. It only audits.

## Install

```bash
git clone https://github.com/eldar101/backport-audit-agent.git
cd backport-audit-agent

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Auth

The tool tries existing auth first:

- Jira env vars: `JIRA_API_TOKEN`, `JIRA_TOKEN`, `JIRA_USER`, `JIRA_EMAIL`,
  `JIRA_BASE_URL`, `JIRA_URL`
- Jira CLI config: `~/.config/.jira/.config.yml`
- `.netrc` for the Jira host
- GitHub env vars: `GITHUB_TOKEN`, `GH_TOKEN`
- GitHub CLI auth: `gh auth token`

If something is missing, it prompts.

Typical setup:

```bash
export JIRA_BASE_URL='https://jira.example.com'
export JIRA_USER='you@example.com'
export JIRA_API_TOKEN='your-jira-token'

gh auth login
```

## Run

```bash
backport-audit audit \
  --fix-version 1.2.0-rc1 \
  --target-branch release-1.2 \
  --repo owner/repo
```

Optional Jira project filter:

```bash
backport-audit audit \
  --project PROJ \
  --fix-version 1.2.0-rc1 \
  --target-branch release-1.2 \
  --repo owner/repo
```

If some Jira issues belong to another GitHub repo, route by title marker:

```bash
backport-audit audit \
  --fix-version 1.2.0-rc1 \
  --target-branch release-1.2 \
  --repo owner/backend \
  --repo-route '[UI]=owner/frontend'
```

## Output

The console shows counts and progress.

Reports are written to:

```text
reports/backport-audit-1.2.0-rc1.md
reports/backport-audit-1.2.0-rc1.json
reports/backport-audit-1.2.0-rc1.csv
```

Per issue, the report shows whether it is:

- `BACKPORTED_CONFIRMED`
- `PROBABLY_BACKPORTED`
- `NOT_BACKPORTED`
- `CLOSED_NO_PR`
- `PR_NOT_MERGED`
- `MANUAL_REVIEW`
- `OPEN_OR_UNRESOLVED`

## Useful Options

Use exact Jira JQL:

```bash
backport-audit audit \
  --fix-version 1.2.0-rc1 \
  --jql 'fixVersion in ("1.2.0-rc1")' \
  --target-branch release-1.2 \
  --repo owner/repo
```

Use a different closed status:

```bash
backport-audit audit \
  --fix-version 1.2.0-rc1 \
  --closed-status Done \
  --target-branch release-1.2 \
  --repo owner/repo
```

Clean a broken local clone cache:

```bash
rm -rf .cache
```
