from __future__ import annotations

import fnmatch
import json
import os
import re
import signal
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol, Sequence


class CodexAdapterError(RuntimeError):
    """Raised when a Codex implementation cannot be trusted."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        stdout: str = "",
        stderr: str = "",
        final_output: str = "",
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.stdout = stdout
        self.stderr = stderr
        self.final_output = final_output


class CodexTimeoutError(CodexAdapterError):
    def __init__(self, stdout: str, stderr: str) -> None:
        super().__init__(
            "Codex execution timed out",
            retryable=True,
            stdout=stdout,
            stderr=stderr,
        )


class AmbiguousCodexCompletion(CodexAdapterError):
    pass


SAFE_EXECUTION_ENVIRONMENT_KEYS = frozenset(
    {
        "CODEX_HOME",
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "SSL_CERT_FILE",
        "TMPDIR",
    }
)


def safe_execution_environment(values: Mapping[str, str]) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in values.items()
        if key in SAFE_EXECUTION_ENVIRONMENT_KEYS and value
    }


@dataclass(frozen=True, slots=True)
class VerificationCommand:
    name: str
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.argv or any(not item for item in self.argv):
            raise ValueError("verification commands require a name and fixed argv")


@dataclass(frozen=True, slots=True)
class EngineeringExecutionPolicy:
    version: str
    repository: str
    workspace_id: str
    client_id: str
    base_ref: str
    allowed_paths: tuple[str, ...]
    verification_profile: str
    verification_commands: tuple[VerificationCommand, ...]
    timeout_seconds: int = 1800
    max_attempts: int = 2
    codex_executable: str = "codex"

    def __post_init__(self) -> None:
        safe = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}"
        for field_name in ("version", "workspace_id", "client_id"):
            if not re.fullmatch(safe, str(getattr(self, field_name))):
                raise ValueError(f"execution policy {field_name} is invalid")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise ValueError("execution policy repository must use owner/name")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", self.base_ref):
            raise ValueError("execution policy base_ref is invalid")
        if not self.allowed_paths:
            raise ValueError("execution policy requires allowed paths")
        for pattern in self.allowed_paths:
            if (
                not pattern.strip()
                or pattern.startswith(("/", "\\"))
                or ".." in PurePosixPath(pattern).parts
                or "\\" in pattern
            ):
                raise ValueError("execution policy contains an unsafe path pattern")
        if not self.verification_profile.strip() or not self.verification_commands:
            raise ValueError("execution policy requires a verification profile")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 7200:
            raise ValueError("execution policy timeout must be between 1 and 7200 seconds")
        if self.max_attempts <= 0 or self.max_attempts > 5:
            raise ValueError("execution policy max_attempts must be between 1 and 5")
        if not self.codex_executable.strip():
            raise ValueError("execution policy codex executable is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "verification_commands": [
                {"name": item.name, "argv": list(item.argv)}
                for item in self.verification_commands
            ],
        }

    @property
    def digest(self) -> str:
        import hashlib

        canonical = json.dumps(
            self.to_dict(), separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def path_allowed(self, relative_path: str) -> bool:
        path = PurePosixPath(relative_path)
        if (
            path.is_absolute()
            or not path.parts
            or ".." in path.parts
            or "\\" in relative_path
        ):
            return False
        return any(
            self._path_parts_match(path.parts, PurePosixPath(pattern).parts)
            for pattern in self.allowed_paths
        )

    @staticmethod
    def _path_parts_match(
        path_parts: tuple[str, ...],
        pattern_parts: tuple[str, ...],
    ) -> bool:
        def expand_double_stars(states: set[int]) -> set[int]:
            expanded = set(states)
            pending = list(states)
            while pending:
                index = pending.pop()
                if (
                    index < len(pattern_parts)
                    and pattern_parts[index] == "**"
                    and index + 1 not in expanded
                ):
                    expanded.add(index + 1)
                    pending.append(index + 1)
            return expanded

        states = expand_double_stars({0})
        for part in path_parts:
            next_states: set[int] = set()
            for index in states:
                if index == len(pattern_parts):
                    continue
                pattern = pattern_parts[index]
                if pattern == "**":
                    next_states.add(index)
                elif fnmatch.fnmatchcase(part, pattern):
                    next_states.add(index + 1)
            states = expand_double_stars(next_states)
            if not states:
                return False
        return len(pattern_parts) in expand_double_stars(states)


@dataclass(frozen=True, slots=True)
class CodexProcessResult:
    returncode: int
    stdout: str
    stderr: str
    final_output: str


class CodexProcessRunner(Protocol):
    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        prompt: str,
        output_path: Path,
        timeout_seconds: int,
        environment: Mapping[str, str],
    ) -> CodexProcessResult: ...


class SubprocessCodexRunner:
    """Run one fixed Codex argv without a shell and terminate its process group."""

    TERMINATION_GRACE_SECONDS = 2

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        prompt: str,
        output_path: Path,
        timeout_seconds: int,
        environment: Mapping[str, str],
    ) -> CodexProcessResult:
        try:
            process = subprocess.Popen(
                list(command),
                cwd=cwd,
                env=dict(environment),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except OSError as exc:
            raise CodexAdapterError(
                f"Codex process could not be started: {exc}",
                retryable=True,
            ) from exc
        try:
            stdout, stderr = process.communicate(prompt, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            stdout = str(exc.stdout or "")
            stderr = str(exc.stderr or "")
            try:
                os.killpg(process.pid, signal.SIGTERM)
                extra_out, extra_err = process.communicate(
                    timeout=self.TERMINATION_GRACE_SECONDS
                )
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                extra_out, extra_err = process.communicate()
            stdout += str(extra_out or "")
            stderr += str(extra_err or "")
            raise CodexTimeoutError(stdout, stderr) from exc
        try:
            final_output = output_path.read_text(encoding="utf-8")
        except OSError:
            final_output = ""
        return CodexProcessResult(
            returncode=int(process.returncode),
            stdout=stdout,
            stderr=stderr,
            final_output=final_output,
        )


class GitCommandRunner(Protocol):
    def run(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: int = 120,
    ) -> subprocess.CompletedProcess[str]: ...


class SubprocessGitRunner:
    def run(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: int = 120,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["git", *arguments],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CodexAdapterError(f"Git verification failed: {exc}") from exc


@dataclass(frozen=True, slots=True)
class WorktreeIdentity:
    path: str
    branch: str
    base_commit: str


@dataclass(frozen=True, slots=True)
class VerificationResult:
    name: str
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "argv": list(self.argv),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True, slots=True)
class VerifiedImplementation:
    base_commit: str
    head_commit: str
    branch: str
    changed_files: tuple[str, ...]
    diff_summary: str
    verifications: tuple[VerificationResult, ...]


class GitWorktreeManager:
    OUTPUT_LIMIT = 20_000

    def __init__(
        self,
        repository_root: str | Path,
        worktree_root: str | Path,
        *,
        runner: GitCommandRunner | None = None,
        verification_environment: Mapping[str, str] | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.worktree_root = Path(worktree_root).resolve()
        self.runner = runner or SubprocessGitRunner()
        values = verification_environment or os.environ
        self.verification_environment = safe_execution_environment(values)

    def assert_repository(self, expected_repository: str) -> None:
        if not (self.repository_root / ".git").exists():
            raise CodexAdapterError("configured engineering repository is not a Git repository")
        remote = self._git(("remote", "get-url", "origin"), self.repository_root)
        if self._normalise_remote(remote) != expected_repository.casefold():
            raise CodexAdapterError("configured engineering repository identity does not match")

    def prepare(self, run_id: str, branch: str, base_ref: str) -> WorktreeIdentity:
        base_commit = self._git(
            ("rev-parse", "--verify", f"{base_ref}^{{commit}}"),
            self.repository_root,
        )
        path = (self.worktree_root / run_id).resolve()
        if self.worktree_root != path and self.worktree_root not in path.parents:
            raise CodexAdapterError("engineering worktree escaped its configured root")
        if path.exists():
            current_branch = self._git(("branch", "--show-current"), path)
            current_base = self._git(("merge-base", base_commit, "HEAD"), path)
            if current_branch != branch or current_base != base_commit:
                raise AmbiguousCodexCompletion(
                    "existing engineering worktree does not match the recorded branch and base"
                )
            return WorktreeIdentity(str(path), branch, base_commit)
        self.worktree_root.mkdir(parents=True, exist_ok=True)
        branch_exists = bool(
            self._git(("branch", "--list", branch), self.repository_root)
        )
        arguments = (
            ("worktree", "add", str(path), branch)
            if branch_exists
            else ("worktree", "add", "-b", branch, str(path), base_commit)
        )
        self.runner.run(arguments, cwd=self.repository_root)
        return WorktreeIdentity(str(path), branch, base_commit)

    def verify(
        self,
        identity: WorktreeIdentity,
        completion: Mapping[str, Any],
        policy: EngineeringExecutionPolicy,
    ) -> VerifiedImplementation:
        path = Path(identity.path)
        branch = self._git(("branch", "--show-current"), path)
        head = self._git(("rev-parse", "HEAD"), path)
        if branch != identity.branch:
            raise AmbiguousCodexCompletion("Codex completed on an unexpected branch")
        if completion.get("base_commit") != identity.base_commit:
            raise AmbiguousCodexCompletion("Codex reported a contradictory base commit")
        if completion.get("commit") != head:
            raise AmbiguousCodexCompletion("Codex reported a contradictory head commit")
        ancestor = self.runner.run(
            ("merge-base", "--is-ancestor", identity.base_commit, head),
            cwd=path,
        )
        if ancestor.returncode != 0:
            raise AmbiguousCodexCompletion("engineering base is not an ancestor of the result")
        if head == identity.base_commit:
            raise CodexAdapterError("Codex did not create a local implementation commit")
        if self._git(
            ("rev-list", "--merges", f"{identity.base_commit}..{head}"),
            path,
        ):
            raise CodexAdapterError("Codex implementation contains a merge commit")
        status = self._git(("status", "--porcelain"), path)
        if status:
            raise AmbiguousCodexCompletion("Codex left an uncommitted or untracked worktree")
        changed_files = tuple(
            item
            for item in self._git(
                ("diff", "--name-only", f"{identity.base_commit}..{head}"),
                path,
            ).splitlines()
            if item
        )
        if not changed_files:
            raise CodexAdapterError("Codex implementation commit contains no changed files")
        forbidden = [item for item in changed_files if not policy.path_allowed(item)]
        if forbidden:
            raise CodexAdapterError(
                "Codex changed forbidden paths: " + ", ".join(sorted(forbidden))
            )
        reported_files = tuple(str(item) for item in completion.get("changed_files", ()))
        if tuple(sorted(reported_files)) != tuple(sorted(changed_files)):
            raise AmbiguousCodexCompletion("Codex reported a contradictory changed-file set")
        diff_summary = self._git(
            ("diff", "--stat", f"{identity.base_commit}..{head}"),
            path,
        )
        verifications: list[VerificationResult] = []
        for command in policy.verification_commands:
            try:
                completed = subprocess.run(
                    list(command.argv),
                    cwd=path,
                    env=self.verification_environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=policy.timeout_seconds,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise CodexAdapterError(
                    f"verification command could not complete: {command.name}"
                ) from exc
            result = VerificationResult(
                name=command.name,
                argv=command.argv,
                returncode=int(completed.returncode),
                stdout=str(completed.stdout or "")[: self.OUTPUT_LIMIT],
                stderr=str(completed.stderr or "")[: self.OUTPUT_LIMIT],
            )
            verifications.append(result)
            if result.returncode != 0:
                raise CodexAdapterError(
                    f"configured verification failed: {command.name}"
                )
        if self._git(("status", "--porcelain"), path):
            raise AmbiguousCodexCompletion("verification left the worktree dirty")
        return VerifiedImplementation(
            base_commit=identity.base_commit,
            head_commit=head,
            branch=branch,
            changed_files=changed_files,
            diff_summary=diff_summary,
            verifications=tuple(verifications),
        )

    def inspect(self, identity: WorktreeIdentity) -> str:
        path = Path(identity.path)
        if not path.exists():
            return "missing"
        branch = self._git(("branch", "--show-current"), path)
        head = self._git(("rev-parse", "HEAD"), path)
        status = self._git(("status", "--porcelain"), path)
        if branch != identity.branch:
            return "ambiguous"
        if head == identity.base_commit and not status:
            return "not_started"
        if status:
            return "ambiguous"
        return "committed"

    def _git(self, arguments: Sequence[str], cwd: Path) -> str:
        return str(self.runner.run(arguments, cwd=cwd).stdout or "").strip()

    @staticmethod
    def _normalise_remote(value: str) -> str:
        text = value.strip()
        match = re.match(r"git@github\.com:(.+?)(?:\.git)?$", text)
        if match:
            return match.group(1).casefold()
        match = re.match(r"https://github\.com/(.+?)(?:\.git)?$", text)
        if match:
            return match.group(1).casefold()
        return text.rstrip("/").removesuffix(".git").casefold()


@dataclass(frozen=True, slots=True)
class CodexInvocation:
    task_id: str
    run_id: str
    prompt: str
    worktree: WorktreeIdentity


@dataclass(frozen=True, slots=True)
class CodexAdapterResult:
    process: CodexProcessResult
    completion: Mapping[str, Any]
    verified: VerifiedImplementation


class CodexImplementationAdapter:
    OUTPUT_LIMIT = 100_000

    def __init__(
        self,
        *,
        policy: EngineeringExecutionPolicy,
        worktrees: GitWorktreeManager,
        schema_path: str | Path,
        state_dir: str | Path,
        runner: CodexProcessRunner | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.policy = policy
        self.worktrees = worktrees
        self.schema_path = Path(schema_path).resolve()
        self.state_dir = Path(state_dir).resolve()
        self.runner = runner or SubprocessCodexRunner()
        self.environment = self._safe_environment(environment or os.environ)

    def execute(self, invocation: CodexInvocation) -> CodexAdapterResult:
        self.worktrees.assert_repository(self.policy.repository)
        output_root = self.state_dir / "engineering-codex-output"
        output_root.mkdir(parents=True, exist_ok=True)
        output_path = output_root / f"{invocation.run_id}.json"
        command = (
            self.policy.codex_executable,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--strict-config",
            "--sandbox",
            "workspace-write",
            "-c",
            'approval_policy="never"',
            "-c",
            "sandbox_workspace_write.network_access=false",
            "--json",
            "--output-schema",
            str(self.schema_path),
            "--output-last-message",
            str(output_path),
            "--cd",
            invocation.worktree.path,
            "-",
        )
        process = self.runner.run(
            command,
            cwd=Path(invocation.worktree.path),
            prompt=invocation.prompt,
            output_path=output_path,
            timeout_seconds=self.policy.timeout_seconds,
            environment=self.environment,
        )
        if process.returncode != 0:
            raise CodexAdapterError(
                f"Codex exited with status {process.returncode}",
                retryable=True,
                stdout=process.stdout,
                stderr=process.stderr,
                final_output=process.final_output,
            )
        try:
            completion = self._parse_completion(
                process.final_output,
                task_id=invocation.task_id,
                run_id=invocation.run_id,
            )
            if completion["status"] != "completed":
                raise CodexAdapterError(
                    "Codex did not report a completed implementation",
                    retryable=False,
                )
            verified = self.worktrees.verify(
                invocation.worktree,
                completion,
                self.policy,
            )
        except CodexAdapterError as exc:
            exc.stdout = process.stdout
            exc.stderr = process.stderr
            exc.final_output = process.final_output
            raise
        return CodexAdapterResult(process, completion, verified)

    def reconcile(self, invocation: CodexInvocation) -> CodexAdapterResult:
        output_path = (
            self.state_dir
            / "engineering-codex-output"
            / f"{invocation.run_id}.json"
        )
        try:
            final_output = output_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise AmbiguousCodexCompletion(
                "Codex completion receipt is missing"
            ) from exc
        completion = self._parse_completion(
            final_output,
            task_id=invocation.task_id,
            run_id=invocation.run_id,
        )
        if completion["status"] != "completed":
            raise AmbiguousCodexCompletion(
                "Codex completion receipt is not successful"
            )
        verified = self.worktrees.verify(
            invocation.worktree,
            completion,
            self.policy,
        )
        return CodexAdapterResult(
            CodexProcessResult(0, "", "", final_output),
            completion,
            verified,
        )

    def _parse_completion(
        self,
        payload: str,
        *,
        task_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        if not payload.strip():
            raise AmbiguousCodexCompletion("Codex returned no structured final output")
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise AmbiguousCodexCompletion(
                "Codex returned malformed structured output"
            ) from exc
        required = {
            "schema_version",
            "task_id",
            "run_id",
            "status",
            "base_commit",
            "commit",
            "changed_files",
            "tests",
            "summary",
            "blockers",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise AmbiguousCodexCompletion("Codex output does not match the required schema")
        if value["schema_version"] != 1:
            raise AmbiguousCodexCompletion("Codex output schema version is unsupported")
        if value["task_id"] != task_id or value["run_id"] != run_id:
            raise AmbiguousCodexCompletion("Codex output identity is contradictory")
        if value["status"] not in {"completed", "blocked", "failed"}:
            raise AmbiguousCodexCompletion("Codex output status is unsupported")
        for field in ("changed_files", "tests", "blockers"):
            if not isinstance(value[field], list) or not all(
                isinstance(item, str) and item.strip() for item in value[field]
            ):
                raise AmbiguousCodexCompletion(f"Codex output {field} is invalid")
        for field in ("base_commit", "commit"):
            if not re.fullmatch(r"[A-Fa-f0-9]{7,64}", str(value[field])):
                raise AmbiguousCodexCompletion(f"Codex output {field} is invalid")
        if not str(value["summary"]).strip():
            raise AmbiguousCodexCompletion("Codex output summary is required")
        return value

    @staticmethod
    def _safe_environment(values: Mapping[str, str]) -> dict[str, str]:
        return safe_execution_environment(values)
