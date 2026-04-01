"""
code_edit.py — LangChain tools for reading and editing CourtLink2 source code.

Tools:
    read_file(file_path, start_line, end_line) -> str
        Read a file from the repo, optionally sliced to a line range.

    propose_edit(file_path, old_code, new_code, description) -> str
        Show a diff of a proposed change. Does NOT write anything.
        The user must confirm before edit_file is called.

    edit_file(file_path, old_code, new_code, description) -> str
        Apply a find-and-replace edit to a file after user confirmation.

    git_commit(branch_name, commit_message) -> str
        Create a new git branch (agent/<branch_name>), stage all modified
        tracked files, and commit with the given message.
"""

import os
import textwrap
from pathlib import Path

from langchain_core.tools import tool

# ── Safety config ──────────────────────────────────────────────────────────────

# Absolute repo root — all file operations are sandboxed here
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# File patterns that must never be edited
_BLOCKED_SUFFIXES = {
    ".pfx",
    ".p12",
    ".pem",
    ".key",
    ".cer",
    ".crt",
    ".dll",
    ".exe",
    ".so",
    ".dylib",
}
_BLOCKED_NAMES = {".env", ".env.local", ".env.production", "secrets.json"}

ALL_TOOLS = []


def _safe_path(file_path: str) -> Path:
    """
    Resolve a relative file path against the repo root.
    Raises ValueError if the path escapes the repo root or targets a blocked file.
    """
    # Normalise separators
    clean = file_path.strip().replace("\\", "/")
    resolved = (_REPO_ROOT / clean).resolve()

    # Sandbox check
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError:
        raise ValueError(f"Path '{file_path}' is outside the repository root.")

    # Blocked file check
    if resolved.suffix.lower() in _BLOCKED_SUFFIXES:
        raise ValueError(
            f"Editing '{resolved.name}' is not allowed (binary/credential file)."
        )
    if resolved.name in _BLOCKED_NAMES:
        raise ValueError(f"Editing '{resolved.name}' is not allowed (sensitive file).")

    return resolved


def _make_diff(old_code: str, new_code: str, file_path: str) -> str:
    """Produce a simple unified-style diff string for display."""
    import difflib

    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
    )
    return "\n".join(diff) if diff else "(no diff — old and new code are identical)"


# ── Tools ──────────────────────────────────────────────────────────────────────


@tool
def read_file(file_path: str, start_line: int = 0, end_line: int = 0) -> str:
    """Read a source file from the CourtLink2 repository.

    Returns the file contents with line numbers. Use this before proposing
    any edit so you have the exact current content.

    Args:
        file_path: Path relative to the repo root, e.g.
                   'CourtLink2.CCM/ViewModel/MeetingViewModel.cs'
                   'CourtLink2.Management/Controllers/CallController.cs'
        start_line: First line to return (1-based, inclusive). 0 = from beginning.
        end_line:   Last line to return (1-based, inclusive). 0 = to end of file.
    """
    try:
        path = _safe_path(file_path)
        if not path.exists():
            return f"File not found: {file_path}"

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)

        s = max(0, start_line - 1) if start_line > 0 else 0
        e = min(total, end_line) if end_line > 0 else total

        numbered = "\n".join(
            f"{i + s + 1:5}: {line}" for i, line in enumerate(lines[s:e])
        )
        header = f"// {file_path}  (lines {s + 1}–{e} of {total})\n"
        return header + numbered

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


@tool
def propose_edit(
    file_path: str,
    old_code: str,
    new_code: str,
    description: str,
) -> str:
    """Show a diff preview of a proposed code change WITHOUT writing anything.

    Always call this BEFORE edit_file to show the user what will change.
    Wait for the user to say 'yes', 'confirm', or 'apply' before calling edit_file.

    Args:
        file_path:   Relative path to the file to edit (from repo root).
        old_code:    The exact existing code to be replaced (must match file contents exactly).
        new_code:    The new code to replace it with.
        description: A short human-readable description of what this change does,
                     e.g. 'Fix null reference in AudioSettings.LoadDevices()'
    """
    try:
        path = _safe_path(file_path)
        if not path.exists():
            return f"File not found: {file_path}"

        content = path.read_text(encoding="utf-8", errors="replace")
        if old_code not in content:
            # Try to give a helpful hint
            stripped = old_code.strip()
            if stripped in content:
                return (
                    "The old_code was not found verbatim (possible leading/trailing whitespace mismatch). "
                    "Use read_file to get the exact content, then retry."
                )
            return (
                f"The old_code was not found in {file_path}. "
                "Use read_file to get the exact current content before proposing an edit."
            )

        diff = _make_diff(old_code, new_code, file_path)

        return (
            f"**Proposed change:** {description}\n"
            f"**File:** `{file_path}`\n\n"
            f"```diff\n{diff}\n```\n\n"
            f"Reply **'yes'** to apply this change, or **'no'** to cancel."
        )

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error proposing edit: {e}"


@tool
def edit_file(
    file_path: str,
    old_code: str,
    new_code: str,
    description: str,
) -> str:
    """Apply a code edit to a file in the CourtLink2 repository.

    IMPORTANT: Only call this after the user has confirmed the change via propose_edit.
    Replaces the first occurrence of old_code with new_code in the file.

    Args:
        file_path:   Relative path to the file to edit (from repo root).
        old_code:    The exact existing code to be replaced (must match file exactly).
        new_code:    The new code to replace it with.
        description: Short description of what this change does.
    """
    try:
        path = _safe_path(file_path)
        if not path.exists():
            return f"File not found: {file_path}"

        content = path.read_text(encoding="utf-8", errors="replace")

        if old_code not in content:
            return (
                f"Edit failed: old_code not found in {file_path}. "
                "The file may have changed. Use read_file to get fresh content and retry."
            )

        new_content = content.replace(old_code, new_code, 1)
        path.write_text(new_content, encoding="utf-8")

        # Count changed lines for the summary
        old_lines = old_code.count("\n") + 1
        new_lines = new_code.count("\n") + 1

        return (
            f"Edit applied to `{file_path}`.\n"
            f"- Replaced {old_lines} line(s) with {new_lines} line(s).\n"
            f"- Description: {description}\n\n"
            f"Call git_commit to create a branch and commit this change."
        )

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error editing file: {e}"


@tool
def git_commit(branch_name: str, commit_message: str) -> str:
    """Create a new git branch and commit all modified tracked files.

    Creates branch 'agent/<branch_name>' from the current HEAD,
    stages all modified tracked files (no untracked), and commits.

    Always call this after edit_file to save the change in git.

    Args:
        branch_name:    Short name for the fix, e.g. 'fix-audio-null-ref'.
                        Will be prefixed with 'agent/' automatically.
        commit_message: Descriptive commit message, e.g.
                        'Fix null reference in AudioSettings.LoadDevices when device list is empty'
    """
    try:
        import git as gitlib

        repo = gitlib.Repo(_REPO_ROOT)

        # Sanitise branch name
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "-", branch_name.strip()).strip("-")
        full_branch = f"agent/{safe_name}"

        # Check if branch already exists
        existing_branches = [b.name for b in repo.branches]
        if full_branch in existing_branches:
            repo.git.checkout(full_branch)
            created = False
        else:
            repo.git.checkout("-b", full_branch)
            created = True

        # Stage all modified tracked files (not untracked)
        modified = [item.a_path for item in repo.index.diff(None)]
        if not modified:
            # Also check staged
            staged = [item.a_path for item in repo.index.diff("HEAD")]
            if not staged:
                return (
                    f"No modified files to commit on branch '{full_branch}'. "
                    "Make sure edit_file was called successfully first."
                )

        repo.git.add("-u")  # stage all tracked modified files
        commit = repo.index.commit(commit_message)

        branch_status = "created" if created else "already existed, switched to"
        return (
            f"Committed successfully.\n"
            f"- Branch: `{full_branch}` ({branch_status})\n"
            f"- Commit: `{commit.hexsha[:8]}`\n"
            f"- Message: {commit_message}\n"
            f"- Files committed: {', '.join(modified) if modified else '(see staged)'}\n\n"
            f"To review: `git diff main..{full_branch}`"
        )

    except Exception as e:
        return f"Git error: {e}"


import re  # noqa: E402 — needed by git_commit above

ALL_TOOLS = [read_file, propose_edit, edit_file, git_commit]
