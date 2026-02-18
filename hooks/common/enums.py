#!/usr/bin/env python3
"""
Voxhook Common Enums
====================

Centralized enum definitions for hook events, tool names, and other constants
used across the Voxhook hook system. Provides type safety and prevents
string literal errors.

Author: Chong-U (chong-u@aioriented.dev)
Created: 2025
Purpose: Type-safe constants for Voxhook
"""

from enum import StrEnum
from typing import Set


class HookEvent(StrEnum):
    """Claude Code hook event names.

    These are the canonical event names that Claude Code fires during execution.
    """
    STOP = "Stop"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    NOTIFICATION = "Notification"
    SUBAGENT_STOP = "SubagentStop"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"


class ToolName(StrEnum):
    """Claude Code tool names.

    These are the canonical tool names that Claude Code uses for different operations.
    """
    # File operations
    READ = "Read"
    EDIT = "Edit"
    MULTI_EDIT = "MultiEdit"
    WRITE = "Write"

    # Notebook operations
    NOTEBOOK_READ = "NotebookRead"
    NOTEBOOK_EDIT = "NotebookEdit"

    # System operations
    BASH = "Bash"
    LS = "LS"

    # Search operations
    GREP = "Grep"
    GLOB = "Glob"

    # Advanced operations
    TASK = "Task"
    WEB_FETCH = "WebFetch"
    WEB_SEARCH = "WebSearch"

    # Workflow operations
    TODO_WRITE = "TodoWrite"
    EXIT_PLAN_MODE = "ExitPlanMode"


class InputKey(StrEnum):
    """Common JSON input keys from Claude Code hook data.

    These are the standard keys that appear in the JSON data passed to hooks.
    """
    HOOK_EVENT_NAME = "hook_event_name"
    TOOL_NAME = "tool_name"
    TOOL_INPUT = "tool_input"
    MESSAGE = "message"
    STOP_HOOK_ACTIVE = "stop_hook_active"

    # Tool input sub-keys
    FILE_PATH = "file_path"
    COMMAND = "command"
    PATTERN = "pattern"
    CONTENT = "content"
    NEW_STRING = "new_string"
    OLD_STRING = "old_string"


class FileExtension(StrEnum):
    """Common file extensions for context-aware processing."""
    # Programming languages
    PYTHON = ".py"
    JAVASCRIPT = ".js"
    TYPESCRIPT = ".ts"
    TYPESCRIPT_JSX = ".tsx"
    JAVA = ".java"
    CPP = ".cpp"
    C = ".c"
    RUST = ".rs"
    GO = ".go"

    # Web technologies
    HTML = ".html"
    CSS = ".css"
    SCSS = ".scss"

    # Configuration and data
    JSON = ".json"
    YAML = ".yaml"
    YML = ".yml"
    TOML = ".toml"
    XML = ".xml"

    # Documentation
    MARKDOWN = ".md"
    TEXT = ".txt"
    README = "README.md"

    # Special files
    GITIGNORE = ".gitignore"
    DOCKERFILE = "Dockerfile"
    MAKEFILE = "Makefile"


class GitCommand(StrEnum):
    """Git command patterns for context-aware processing."""
    STATUS = "git status"
    ADD = "git add"
    COMMIT = "git commit"
    PUSH = "git push"
    PULL = "git pull"
    FETCH = "git fetch"
    DIFF = "git diff"
    LOG = "git log"
    BRANCH = "git branch"
    CHECKOUT = "git checkout"
    MERGE = "git merge"
    REBASE = "git rebase"
    RESET = "git reset"
    STASH = "git stash"


class CommandType(StrEnum):
    """Command type patterns for bash command categorization."""
    GIT = "git"
    NPM = "npm"
    UV = "uv"
    PYTHON = "python"
    NODE = "node"
    DOCKER = "docker"
    MAKE = "make"
    CURL = "curl"
    WGET = "wget"
    SSH = "ssh"
    SCP = "scp"


class NotificationType(StrEnum):
    """Notification message categories."""
    PERMISSION_REQUEST = "permission_request"
    IDLE_TIMEOUT = "idle_timeout"
    GENERAL = "general"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# Utility sets for quick membership testing
FILE_OPERATION_TOOLS: Set[ToolName] = {
    ToolName.READ,
    ToolName.EDIT,
    ToolName.MULTI_EDIT,
    ToolName.WRITE,
    ToolName.NOTEBOOK_READ,
    ToolName.NOTEBOOK_EDIT,
}

SEARCH_TOOLS: Set[ToolName] = {
    ToolName.GREP,
    ToolName.GLOB,
}

SYSTEM_TOOLS: Set[ToolName] = {
    ToolName.BASH,
    ToolName.LS,
}

WORKFLOW_TOOLS: Set[ToolName] = {
    ToolName.TASK,
    ToolName.TODO_WRITE,
    ToolName.EXIT_PLAN_MODE,
}

WEB_TOOLS: Set[ToolName] = {
    ToolName.WEB_FETCH,
    ToolName.WEB_SEARCH,
}

# Hook events that typically include tool information
TOOL_EVENTS: Set[HookEvent] = {
    HookEvent.PRE_TOOL_USE,
    HookEvent.POST_TOOL_USE,
}

# Hook events that are tool-independent
STANDALONE_EVENTS: Set[HookEvent] = {
    HookEvent.STOP,
    HookEvent.NOTIFICATION,
    HookEvent.SUBAGENT_STOP,
    HookEvent.USER_PROMPT_SUBMIT,
}
