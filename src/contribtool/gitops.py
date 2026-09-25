from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .errors import GitError, ValidationError


class GitRepo:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        result = self.run("rev-parse", "--show-toplevel")
        self.root = Path(result.stdout.strip()).resolve()

    def run(self, *args: str, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            process = subprocess.run(
                ["git", *args], cwd=self.path, env=env, capture_output=True,
                text=True, check=False,
            )
        except FileNotFoundError as exc:
            raise GitError("Git executable not found") from exc
        if check and process.returncode:
            detail = (process.stderr or process.stdout).strip()
            raise GitError(detail or f"git {' '.join(args)} failed")
        return process

    def status(self) -> str:
        return self.run("status", "--porcelain=v1").stdout.strip()

    def branch(self) -> str:
        return self.run("branch", "--show-current").stdout.strip()

    def identity(self) -> tuple[str, str]:
        return (
            self.run("config", "user.name", check=False).stdout.strip(),
            self.run("config", "user.email", check=False).stdout.strip(),
        )

    def remote(self, name: str = "origin") -> str:
        value = self.run("remote", "get-url", name, check=False).stdout.strip()
        if value.startswith("http://") or value.startswith("https://"):
            parsed = urlsplit(value)
            host = parsed.hostname or ""
            if parsed.port:
                host = f"{host}:{parsed.port}"
            return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))
        return value

    def head(self) -> str:
        return self.run("rev-parse", "HEAD").stdout.strip()

    def schedule_sequences(self, schedule_id: str) -> set[int]:
        body = self.run("log", "--all", "--format=%B%x00").stdout
        sequences: set[int] = set()
        marker = f"Contrib-Schedule-Id: {schedule_id}"
        for commit in body.split("\x00"):
            if marker not in commit:
                continue
            for line in commit.splitlines():
                if line.startswith("Contrib-Sequence:"):
                    try:
                        sequences.add(int(line.split(":", 1)[1].strip()))
                    except ValueError:
                        continue
        return sequences

    def commit(self, message: str, timestamp: str, files: list[str]) -> str:
        self.run("add", "--", *files)
        staged = self.run("diff", "--cached", "--name-only").stdout.splitlines()
        if set(staged) != set(files):
            raise ValidationError("staged paths contain unexpected files")
        environment = os.environ.copy()
        environment["GIT_AUTHOR_DATE"] = timestamp
        environment["GIT_COMMITTER_DATE"] = timestamp
        self.run("commit", "--only", "-m", message, "--", *files, env=environment)
        return self.head()


def validate_repo(path: Path, branch: str | None = None, allow_dirty: bool = False) -> GitRepo:
    try:
        repo = GitRepo(path)
    except GitError:
        raise
    except Exception as exc:
        raise ValidationError(f"not a Git repository: {path}") from exc
    active = repo.branch()
    if not active:
        raise ValidationError("detached HEAD is not supported")
    if branch and active != branch:
        raise ValidationError(f"active branch is {active}, expected {branch}")
    dirty_lines = [line for line in repo.status().splitlines() if not line.startswith("?? .contribution-tool/")]
    if dirty_lines and not allow_dirty:
        raise ValidationError("worktree has uncommitted changes")
    name, email = repo.identity()
    if not name or not email:
        raise ValidationError("Git user.name and user.email are required")
    return repo
