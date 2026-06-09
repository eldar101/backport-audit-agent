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

Credentials are read from environment variables. If they are missing, the CLI prompts
for them securely and does not save them to disk.

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

Set:

```bash
export GITHUB_TOKEN='github_pat_or_classic_token'
```

`GH_TOKEN` is also accepted.

## Usage

Basic run:

```bash
backport-audit audit \
  --jira-url "$JIRA_BASE_URL" \
  --project EDM \
  --fix-version 1.2.0-rc1 \
  --repo flightctl/flightctl
```

By default, `1.2.0-rc1` maps to `release-1.2`.

Override the target branch:

```bash
backport-audit audit \
  --fix-version 1.2.0-rc1 \
  --target-branch release-1.2 \
  --repo flightctl/flightctl \
  --project EDM
```

Use a specific local clone directory for git verification:

```bash
backport-audit audit \
  --fix-version 1.2.0-rc1 \
  --repo flightctl/flightctl \
  --clone-dir /tmp/flightctl-backport-audit
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
  --repo flightctl/flightctl \
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

- `git patch-id` checks the latest 5000 non-merge commits on the target branch.
- Adapted backports may be marked `MANUAL_REVIEW` if the patch changed materially.
- The tool currently searches GitHub PRs by Jira key in the configured repo. If a Jira
  issue points to PRs in another repo, explicit GitHub PR URLs in Jira are still honored.
- For best audit accuracy, use `git cherry-pick -x` for backports and include Jira keys
  in PR titles or commit messages.
