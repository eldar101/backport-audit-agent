from __future__ import annotations

import shutil
from pathlib import Path

from backport_audit.models import AuditStatus, PullRequestDetails, VerificationResult
from backport_audit.util import run_git


class GitVerifier:
    def __init__(self, repo_dir: str | Path, github_repo: str) -> None:
        self.repo_dir = Path(repo_dir).expanduser().resolve()
        self.github_repo = github_repo
        self._target_refs: dict[str, str] = {}
        self._target_patch_ids: dict[str, dict[str, str]] = {}
        self._commit_patch_ids: dict[str, list[str]] = {}

    def ensure_repo(self) -> None:
        if (self.repo_dir / ".git").exists():
            result = self._git(["fetch", "--all", "--prune"])
            if result.returncode != 0:
                raise RuntimeError(f"git fetch failed: {result.stderr.strip()}")
            return
        if self.repo_dir.exists():
            if any(self.repo_dir.iterdir()):
                raise RuntimeError(
                    f"Clone directory {self.repo_dir} exists but is not a git repository. "
                    "Pass --clone-dir with a clean path or remove that directory."
                )
            self.repo_dir.rmdir()

        self.repo_dir.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/{self.github_repo}.git"
        result = run_git(["clone", url, str(self.repo_dir)], cwd=self.repo_dir.parent)
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr.strip()}")

    def clear_invalid_cache(self) -> None:
        if self.repo_dir.exists() and not (self.repo_dir / ".git").exists():
            shutil.rmtree(self.repo_dir)

    def verify_pr(
        self,
        *,
        issue_key: str,
        pr: PullRequestDetails,
        target_branch: str,
    ) -> VerificationResult:
        if not pr.merged:
            return VerificationResult(
                status=AuditStatus.PR_NOT_MERGED,
                method="github_pr_state",
                evidence=[f"{pr.ref.url} is not merged"],
            )

        target_ref = self._resolve_target_ref(target_branch)
        merge_sha = pr.merge_commit_sha
        if merge_sha and self._is_ancestor(merge_sha, target_ref):
            return VerificationResult(
                status=AuditStatus.BACKPORTED_CONFIRMED,
                method="merge_commit_ancestor",
                evidence=[f"{merge_sha} is an ancestor of {target_ref}"],
            )

        for source_sha in [sha for sha in [merge_sha, *pr.commits] if sha]:
            marker = f"cherry picked from commit {source_sha}"
            found = self._git_log_grep(marker, target_ref)
            if found:
                return VerificationResult(
                    status=AuditStatus.BACKPORTED_CONFIRMED,
                    method="cherry_pick_x",
                    evidence=[f"{target_ref} contains '{marker}' in commit {found[0]}"],
                )

        patch_match = self._patch_id_match(pr.commits, target_ref)
        if patch_match:
            return VerificationResult(
                status=AuditStatus.BACKPORTED_CONFIRMED,
                method="patch_id",
                evidence=[patch_match],
            )

        metadata_hits = self._metadata_hits(issue_key, pr, target_ref)
        if metadata_hits:
            return VerificationResult(
                status=AuditStatus.PROBABLY_BACKPORTED,
                method="metadata_search",
                evidence=metadata_hits[:5],
            )

        if pr.changed_files and self._changed_file_overlap(pr.changed_files, target_ref):
            return VerificationResult(
                status=AuditStatus.MANUAL_REVIEW,
                method="changed_file_overlap",
                evidence=[
                    "Release branch has commits touching one or more changed files, "
                    "but no exact backport evidence was found."
                ],
            )

        return VerificationResult(
            status=AuditStatus.NOT_BACKPORTED,
            method="no_evidence",
            evidence=[f"No backport evidence found on {target_ref}"],
        )

    def _resolve_target_ref(self, target_branch: str) -> str:
        if target_branch in self._target_refs:
            return self._target_refs[target_branch]
        for ref in (f"origin/{target_branch}", target_branch):
            result = self._git(["rev-parse", "--verify", ref])
            if result.returncode == 0:
                self._target_refs[target_branch] = ref
                return ref
        raise RuntimeError(f"Target branch '{target_branch}' was not found locally or on origin.")

    def _is_ancestor(self, sha: str, target_ref: str) -> bool:
        return self._git(["merge-base", "--is-ancestor", sha, target_ref]).returncode == 0

    def _git_log_grep(self, pattern: str, target_ref: str) -> list[str]:
        result = self._git(["log", target_ref, "--format=%H", f"--grep={pattern}", "-F"])
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _patch_id_match(self, source_commits: list[str], target_ref: str) -> str | None:
        target_patch_ids = self._patch_ids_for_range(target_ref)
        if not target_patch_ids:
            return None

        for source_sha in source_commits:
            source_patch_ids = self._patch_ids_for_commit(source_sha)
            for patch_id in source_patch_ids:
                if patch_id in target_patch_ids:
                    return (
                        f"Patch-id {patch_id} from source commit {source_sha} exists on "
                        f"{target_ref} as {target_patch_ids[patch_id]}"
                    )
        return None

    def _patch_ids_for_range(self, target_ref: str) -> dict[str, str]:
        if target_ref in self._target_patch_ids:
            return self._target_patch_ids[target_ref]
        result = self._git(["log", target_ref, "--format=%H", "--no-merges", "-n", "5000"])
        if result.returncode != 0:
            return {}
        patch_ids: dict[str, str] = {}
        for commit in [line.strip() for line in result.stdout.splitlines() if line.strip()]:
            for patch_id in self._patch_ids_for_commit(commit):
                patch_ids[patch_id] = commit
        self._target_patch_ids[target_ref] = patch_ids
        return patch_ids

    def _patch_ids_for_commit(self, commit: str) -> list[str]:
        if commit in self._commit_patch_ids:
            return self._commit_patch_ids[commit]
        show = self._git(["show", "--format=", "--no-ext-diff", commit])
        if show.returncode != 0 or not show.stdout.strip():
            return []
        patch_id = run_git_with_input(["patch-id", "--stable"], cwd=self.repo_dir, data=show.stdout)
        if patch_id.returncode != 0:
            return []
        patch_ids = [
            line.split()[0]
            for line in patch_id.stdout.splitlines()
            if line.strip() and len(line.split()) >= 1
        ]
        self._commit_patch_ids[commit] = patch_ids
        return patch_ids

    def _metadata_hits(
        self,
        issue_key: str,
        pr: PullRequestDetails,
        target_ref: str,
    ) -> list[str]:
        queries = [issue_key, f"#{pr.ref.number}", f"pull/{pr.ref.number}"]
        if pr.title:
            queries.append(pr.title)
        queries.extend(subject for subject in pr.commit_subjects.values() if subject)

        hits: list[str] = []
        for query in dict.fromkeys(queries):
            for commit in self._git_log_grep(query, target_ref):
                hits.append(f"{target_ref} commit {commit} matches '{query}'")
        return hits

    def _changed_file_overlap(self, changed_files: list[str], target_ref: str) -> bool:
        for filename in changed_files[:50]:
            result = self._git(["log", target_ref, "--format=%H", "-n", "1", "--", filename])
            if result.returncode == 0 and result.stdout.strip():
                return True
        return False

    def _git(self, args: list[str]):
        result = run_git(args, cwd=self.repo_dir)
        return result


def run_git_with_input(args: list[str], *, cwd: str | Path, data: str):
    import subprocess

    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        input=data,
        check=False,
        text=True,
        capture_output=True,
    )
