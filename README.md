# Backport Audit Agent

Small CLI tool that checks Jira issues in a fixVersion and reports whether their
GitHub PRs made it into a release branch.

It does not create backports. It only audits.

## Requirements

- Python 3.10+
- Git
- Network access to Jira and GitHub
- Optional: GitHub CLI (`gh`) if you want the tool to reuse `gh auth login`
- Optional: Jira CLI config if you want the tool to reuse an existing Jira URL/token

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
  --release-branch release-1.2 \
  --github-repo owner/repo
```

Optional Jira project filter:

```bash
backport-audit audit \
  --jira-project PROJ \
  --fix-version 1.2.0-rc1 \
  --release-branch release-1.2 \
  --github-repo owner/repo
```

If some Jira issues belong to another GitHub repo, route by title marker:

```bash
backport-audit audit \
  --fix-version 1.2.0-rc1 \
  --release-branch release-1.2 \
  --github-repo owner/backend \
  --repo-route '[UI]=owner/frontend'
```

Short flag names are also supported:

- `--project` is the same as `--jira-project`
- `--repo` is the same as `--github-repo`
- `--target-branch` is the same as `--release-branch`

## Output

The console and report files show these buckets:

- bugs that are closed
- bugs that are not closed
- bugs that are closed, have PR, and are backported
- bugs that are closed, have PR, and are not backported
- bugs that are closed and do not have PR

The CSV and Markdown reports include Jira issue links, Jira labels, GitHub PR links,
and PR creators. Each issue row includes its Jira status, discovered PR links,
audit result, and the evidence used for that result.

Reports are written to:

```text
reports/backport-audit-1.2.0-rc1.md
reports/backport-audit-1.2.0-rc1.csv
```

If you also want a JSON report for scripts or automation, add `--json`.

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

## Safety Notes

- Use read-only Jira and GitHub tokens when possible.
- The tool runs `git` without a shell and only clones `https://github.com/owner/repo.git`.
- CSV output is escaped so Jira text cannot run spreadsheet formulas when opened.
- Reports can contain private Jira issue text and PR links. Do not publish them unless that data is public.
