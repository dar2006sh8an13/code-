"""Centralized command permission policy manager evaluating ALLOW, DENY, and REQUIRE_APPROVAL verdicts."""

from enum import Enum
import os
from pathlib import Path
import shlex
from typing import List, Optional, Union
from pydantic import BaseModel, Field

from codeagent.execution.command_validator import (
    ALLOWED_BASE_EXECUTABLES,
    DANGEROUS_ARG_PATTERNS,
    DANGEROUS_COMMANDS,
    SHELL_INJECTION_TOKENS,
)


class PolicyVerdict(str, Enum):
    """The three possible command policy evaluation outcomes."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class PermissionEvaluationResult(BaseModel):
    """Structured decision explaining a command permission evaluation."""

    verdict: PolicyVerdict
    command: str
    executable: str
    subcommand: Optional[str] = None
    reason: str
    risk_level: str = "low"  # "low", "medium", "high", "critical"
    requires_approval: bool = False


class SafetyPermissionManager:
    """Enforces Python-governed command permission rules across all tool and CLI entry points."""

    # Read-only commands that can be executed safely without prompt
    READ_ONLY_GIT_SUBCOMMANDS = {
        "status", "diff", "log", "branch", "show", "rev-parse", "cat-file", "tag"
    }

    # Mutating commands that strictly require human confirmation
    MUTATING_GIT_SUBCOMMANDS = {
        "add", "commit", "switch", "checkout", "merge", "rebase", "stash", "restore"
    }

    # Categorically denied dangerous Git subcommands and flags
    DENIED_GIT_OPERATIONS = [
        (["push", "--force"], "Force-pushing to remote branches is categorically denied."),
        (["push", "-f"], "Force-pushing to remote branches is categorically denied."),
        (["reset", "--hard"], "Hard reset destroys uncommitted working tree changes."),
        (["clean", "-f"], "Force cleaning working tree removes untracked files permanently."),
        (["clean", "-fd"], "Force cleaning working tree removes untracked files permanently."),
        (["branch", "-D"], "Force-deleting branches without merge check is denied."),
    ]

    def __init__(self, workspace_root: Optional[Union[str, Path]] = None) -> None:
        """Initialize SafetyPermissionManager."""
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

    def parse_command_args(self, command: str) -> List[str]:
        """Safely split command string into tokenized arguments handling Windows paths."""
        try:
            # On Windows, shlex with posix=False handles Windows backslashes correctly
            return shlex.split(command, posix=os.name != "nt")
        except ValueError:
            # Fallback on basic whitespace split if quoting is malformed
            return command.strip().split()

    def evaluate_command(self, command: str) -> PermissionEvaluationResult:
        """Evaluate a command string against security rules.

        Returns:
            PermissionEvaluationResult with verdict ALLOW, DENY, or REQUIRE_APPROVAL.
        """
        clean_cmd = command.strip()
        if not clean_cmd:
            return PermissionEvaluationResult(
                verdict=PolicyVerdict.DENY,
                command=command,
                executable="",
                reason="Empty command string is not allowed.",
                risk_level="critical",
                requires_approval=False,
            )

        # 1. Check for unauthorized shell chaining / injection tokens
        for token in SHELL_INJECTION_TOKENS:
            if token in clean_cmd:
                return PermissionEvaluationResult(
                    verdict=PolicyVerdict.DENY,
                    command=command,
                    executable="",
                    reason=f"Shell chaining operator '{token}' detected. Subcommands must be run independently.",
                    risk_level="critical",
                    requires_approval=False,
                )

        args = self.parse_command_args(clean_cmd)
        if not args:
            return PermissionEvaluationResult(
                verdict=PolicyVerdict.DENY,
                command=command,
                executable="",
                reason="Failed to parse command arguments.",
                risk_level="critical",
                requires_approval=False,
            )

        raw_exe = args[0]
        exe_name = Path(raw_exe).name.lower()
        if exe_name.endswith(".exe"):
            exe_base = exe_name[:-4]
        else:
            exe_base = exe_name

        # 2. Check explicitly dangerous or disallowed base executables
        if exe_base in DANGEROUS_COMMANDS or raw_exe.lower() in DANGEROUS_COMMANDS:
            return PermissionEvaluationResult(
                verdict=PolicyVerdict.DENY,
                command=command,
                executable=raw_exe,
                reason=f"Executable '{raw_exe}' is blacklisted as a destructive or administrative command.",
                risk_level="critical",
                requires_approval=False,
            )

        # Check destructive recursive deletion commands (rm -rf, del /s, rmdir /s)
        if exe_base in ("rm", "del", "erase", "rd", "rmdir"):
            sub_flags = [a.lower() for a in args[1:]]
            if any(f in sub_flags for f in ("-rf", "-fr", "-r", "/s", "/q")) or any(
                a.startswith(("-rf", "-fr", "/s", "/q")) for a in sub_flags
            ):
                return PermissionEvaluationResult(
                    verdict=PolicyVerdict.DENY,
                    command=command,
                    executable=raw_exe,
                    reason=f"Destructive recursive deletion via '{clean_cmd}' is categorically denied.",
                    risk_level="critical",
                    requires_approval=False,
                )

        # 3. Check Git commands
        if exe_base == "git":
            return self._evaluate_git_command(args, clean_cmd)

        # 4. Check Package Managers (pip, npm)
        if exe_base in ("pip", "pip3"):
            sub = args[1].lower() if len(args) > 1 else ""
            if sub in ("install", "uninstall", "update"):
                return PermissionEvaluationResult(
                    verdict=PolicyVerdict.REQUIRE_APPROVAL,
                    command=clean_cmd,
                    executable=raw_exe,
                    subcommand=sub,
                    reason=f"Modifying dependencies via pip {sub} requires human approval.",
                    risk_level="high",
                    requires_approval=True,
                )
            elif sub in ("list", "show", "check", "--version", "help"):
                return PermissionEvaluationResult(
                    verdict=PolicyVerdict.ALLOW,
                    command=clean_cmd,
                    executable=raw_exe,
                    subcommand=sub,
                    reason="Read-only pip query permitted.",
                    risk_level="low",
                    requires_approval=False,
                )

        # 5. Check Python execution
        if exe_base in ("python", "python3"):
            # Reading version or help is read-only
            if len(args) > 1 and args[1] in ("--version", "-V", "--help", "-h"):
                return PermissionEvaluationResult(
                    verdict=PolicyVerdict.ALLOW,
                    command=clean_cmd,
                    executable=raw_exe,
                    reason="Read-only Python interpreter inspection.",
                    risk_level="low",
                    requires_approval=False,
                )
            return PermissionEvaluationResult(
                verdict=PolicyVerdict.REQUIRE_APPROVAL,
                command=clean_cmd,
                executable=raw_exe,
                reason="Executing Python scripts or code snippets requires user approval.",
                risk_level="medium",
                requires_approval=True,
            )

        # 6. Check Test runners
        if exe_base in ("pytest", "unittest"):
            return PermissionEvaluationResult(
                verdict=PolicyVerdict.ALLOW,
                command=clean_cmd,
                executable=raw_exe,
                reason="Running test suite is permitted in sandbox workspace.",
                risk_level="low",
                requires_approval=False,
            )

        # 7. Check basic safe read-only system utilities
        if exe_base in ("echo", "dir", "type", "cat", "ls", "where", "findstr"):
            return PermissionEvaluationResult(
                verdict=PolicyVerdict.ALLOW,
                command=clean_cmd,
                executable=raw_exe,
                reason=f"Read-only utility '{exe_base}' allowed.",
                risk_level="low",
                requires_approval=False,
            )

        # 8. Unclassified command: default to REQUIRE_APPROVAL or DENY
        return PermissionEvaluationResult(
            verdict=PolicyVerdict.REQUIRE_APPROVAL,
            command=clean_cmd,
            executable=raw_exe,
            reason=f"Command '{exe_base}' is not pre-classified and requires explicit user authorization.",
            risk_level="medium",
            requires_approval=True,
        )

    def _evaluate_git_command(self, args: List[str], full_cmd: str) -> PermissionEvaluationResult:
        """Evaluate Git subcommand and argument flags."""
        if len(args) < 2:
            return PermissionEvaluationResult(
                verdict=PolicyVerdict.ALLOW,
                command=full_cmd,
                executable="git",
                reason="Git base command or version check allowed.",
                risk_level="low",
                requires_approval=False,
            )

        # Normalize flags to find subcommand (skipping global flags like -C, -c)
        idx = 1
        while idx < len(args) and args[idx].startswith("-"):
            idx += 1

        if idx >= len(args):
            return PermissionEvaluationResult(
                verdict=PolicyVerdict.ALLOW,
                command=full_cmd,
                executable="git",
                reason="Git flags query allowed.",
                risk_level="low",
                requires_approval=False,
            )

        subcmd = args[idx].lower()
        sub_args = [a.lower() for a in args[idx + 1:]]

        # 1. Denied Git operations check
        for denied_seq, reason in self.DENIED_GIT_OPERATIONS:
            d_sub = denied_seq[0]
            d_flag = denied_seq[1]
            if subcmd == d_sub and d_flag in sub_args:
                return PermissionEvaluationResult(
                    verdict=PolicyVerdict.DENY,
                    command=full_cmd,
                    executable="git",
                    subcommand=subcmd,
                    reason=reason,
                    risk_level="critical",
                    requires_approval=False,
                )

        # 2. Check for force push via refspec (e.g. +main:main)
        if subcmd == "push" and any(a.startswith("+") for a in sub_args):
            return PermissionEvaluationResult(
                verdict=PolicyVerdict.DENY,
                command=full_cmd,
                executable="git",
                subcommand="push",
                reason="Force push refspec (+) is categorically denied.",
                risk_level="critical",
                requires_approval=False,
            )

        # 3. Read-only Git operations
        if subcmd in self.READ_ONLY_GIT_SUBCOMMANDS:
            # Special case: branch -d or branch -D is mutating
            if subcmd == "branch" and any(f in sub_args for f in ("-d", "-D", "-m", "-M")):
                return PermissionEvaluationResult(
                    verdict=PolicyVerdict.REQUIRE_APPROVAL,
                    command=full_cmd,
                    executable="git",
                    subcommand="branch",
                    reason="Branch deletion or renaming requires human confirmation.",
                    risk_level="high",
                    requires_approval=True,
                )
            return PermissionEvaluationResult(
                verdict=PolicyVerdict.ALLOW,
                command=full_cmd,
                executable="git",
                subcommand=subcmd,
                reason=f"Read-only Git operation 'git {subcmd}' allowed.",
                risk_level="low",
                requires_approval=False,
            )

        # 4. Mutating Git operations require approval
        if subcmd in self.MUTATING_GIT_SUBCOMMANDS:
            return PermissionEvaluationResult(
                verdict=PolicyVerdict.REQUIRE_APPROVAL,
                command=full_cmd,
                executable="git",
                subcommand=subcmd,
                reason=f"Modifying repository state via 'git {subcmd}' requires human authorization.",
                risk_level="medium",
                requires_approval=True,
            )

        # 5. Other Git commands require approval
        return PermissionEvaluationResult(
            verdict=PolicyVerdict.REQUIRE_APPROVAL,
            command=full_cmd,
            executable="git",
            subcommand=subcmd,
            reason=f"Git operation 'git {subcmd}' requires explicit human approval.",
            risk_level="medium",
            requires_approval=True,
        )
