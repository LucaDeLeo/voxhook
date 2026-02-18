#!/usr/bin/env python3
"""
Voxhook Common Utilities
========================

Utility functions for converting between string literals and enums,
providing safe conversion with fallback handling.

Author: Chong-U (chong-u@aioriented.dev)
Created: 2025
Purpose: Safe enum conversion utilities for Voxhook
"""

import logging
from typing import Optional, Dict, Any, Type, TypeVar
from pathlib import Path

from .enums import (
    HookEvent,
    ToolName,
    InputKey,
    FileExtension,
    GitCommand,
    CommandType,
    NotificationType,
)

# Type variable for enum types
EnumType = TypeVar('EnumType')

# Logger for this module
logger = logging.getLogger('voxhook.common.utils')


def safe_enum_from_string(enum_class: Type[EnumType], value: str, fallback: Optional[EnumType] = None) -> Optional[EnumType]:
    """Safely convert a string value to an enum, with optional fallback.

    Args:
        enum_class: The enum class to convert to
        value: String value to convert
        fallback: Optional fallback enum value if conversion fails

    Returns:
        Enum value if conversion succeeds, fallback if provided, None otherwise
    """
    if not value:
        return fallback

    # Guard against non-string input to prevent AttributeError on .lower()
    if not isinstance(value, str):
        logger.warning(f"Expected str, got {type(value).__name__}: {value}")
        return fallback

    try:
        # Try direct conversion first
        return enum_class(value)
    except ValueError:
        # Try case-insensitive search for string enums
        if hasattr(enum_class, '__members__'):
            for enum_member in enum_class:
                if hasattr(enum_member, 'value') and str(enum_member.value).lower() == value.lower():
                    logger.debug(f"Case-insensitive match found: '{value}' -> {enum_member}")
                    return enum_member

        # Log the failed conversion
        logger.warning(f"Could not convert '{value}' to {enum_class.__name__}, using fallback: {fallback}")
        return fallback


def get_hook_event(hook_data: Dict[str, Any]) -> Optional[HookEvent]:
    """Extract and convert hook event name from hook data."""
    event_name = hook_data.get(InputKey.HOOK_EVENT_NAME.value)
    return safe_enum_from_string(HookEvent, event_name)


def get_tool_name(hook_data: Dict[str, Any]) -> Optional[ToolName]:
    """Extract and convert tool name from hook data."""
    tool_name = hook_data.get(InputKey.TOOL_NAME.value)
    return safe_enum_from_string(ToolName, tool_name)


def get_file_extension(file_path: str) -> Optional[FileExtension]:
    """Extract and convert file extension from file path."""
    if not file_path:
        return None

    path_obj = Path(file_path)
    filename = path_obj.name
    filename_lower = filename.lower()
    extension = path_obj.suffix.lower()

    # Check for special filenames first (case-insensitive)
    special_files = {
        "readme.md": FileExtension.README,
        ".gitignore": FileExtension.GITIGNORE,
        "dockerfile": FileExtension.DOCKERFILE,
        "makefile": FileExtension.MAKEFILE,
    }

    if filename_lower in special_files:
        return special_files[filename_lower]

    # Then check for extensions
    return safe_enum_from_string(FileExtension, extension)


def get_git_command(command: str) -> Optional[GitCommand]:
    """Extract and convert git command from bash command string."""
    if not command:
        return None

    import shlex

    # Tokenize to handle prefixes like "sudo", "env", "git -C path"
    try:
        tokens = shlex.split(command.strip())
    except ValueError:
        # Fallback to simple split if shlex fails (unbalanced quotes, etc.)
        tokens = command.strip().split()

    if not tokens:
        return None

    # Skip common command prefixes
    skip_prefixes = {'sudo', 'env', 'nice', 'time', 'nohup'}
    i = 0
    while i < len(tokens) and tokens[i] in skip_prefixes:
        i += 1

    # Find "git" token
    if i >= len(tokens) or tokens[i] != 'git':
        return None

    # Skip past "git" and any git flags to find the subcommand
    i += 1
    while i < len(tokens) and tokens[i].startswith('-'):
        # Skip flags that take arguments (e.g., -C path, -c config=value)
        if tokens[i] in {'-C', '-c', '--git-dir', '--work-tree', '--namespace'}:
            i += 2  # Skip flag and its argument
        else:
            i += 1  # Skip standalone flag

    if i >= len(tokens):
        return None

    # Build the git subcommand string and match
    subcommand = f"git {tokens[i]}"
    return safe_enum_from_string(GitCommand, subcommand)


def get_command_type(command: str) -> Optional[CommandType]:
    """Extract and convert command type from bash command string."""
    if not command:
        return None

    command = command.strip()

    # Try to match against known command types
    for cmd_type in CommandType:
        if command.startswith(cmd_type.value + " ") or command == cmd_type.value:
            return cmd_type

    return None


def categorize_notification_message(message: str) -> NotificationType:
    """Categorize a notification message into a type."""
    if not message:
        return NotificationType.GENERAL

    message_lower = message.lower()

    if "permission" in message_lower and "use" in message_lower:
        return NotificationType.PERMISSION_REQUEST

    if "waiting for your input" in message_lower or "waiting for input" in message_lower:
        return NotificationType.IDLE_TIMEOUT

    if any(keyword in message_lower for keyword in ["error", "failed", "exception", "critical"]):
        return NotificationType.ERROR

    if any(keyword in message_lower for keyword in ["warning", "warn", "caution"]):
        return NotificationType.WARNING

    return NotificationType.GENERAL


def extract_tool_input_value(hook_data: Dict[str, Any], key: InputKey) -> Optional[str]:
    """Extract a value from tool_input section of hook data."""
    tool_input = hook_data.get(InputKey.TOOL_INPUT.value, {})
    if not isinstance(tool_input, dict):
        return None

    return tool_input.get(key.value)


def is_file_operation_tool(tool_name: Optional[ToolName]) -> bool:
    """Check if a tool is a file operation tool."""
    if not tool_name:
        return False

    from .enums import FILE_OPERATION_TOOLS
    return tool_name in FILE_OPERATION_TOOLS


def is_system_tool(tool_name: Optional[ToolName]) -> bool:
    """Check if a tool is a system operation tool."""
    if not tool_name:
        return False

    from .enums import SYSTEM_TOOLS
    return tool_name in SYSTEM_TOOLS


def is_search_tool(tool_name: Optional[ToolName]) -> bool:
    """Check if a tool is a search operation tool."""
    if not tool_name:
        return False

    from .enums import SEARCH_TOOLS
    return tool_name in SEARCH_TOOLS


def enum_to_json_value(enum_value: Optional[EnumType]) -> Optional[str]:
    """Convert an enum value to its JSON string representation."""
    if enum_value is None:
        return None

    if hasattr(enum_value, 'value'):
        return str(enum_value.value)

    return str(enum_value)


def debug_hook_data(hook_data: Dict[str, Any], logger: logging.Logger) -> None:
    """Debug utility to log parsed hook data with enum conversions."""
    if not logger.isEnabledFor(logging.DEBUG):
        return

    logger.debug("=== HOOK DATA ANALYSIS ===")

    hook_event = get_hook_event(hook_data)
    tool_name = get_tool_name(hook_data)

    logger.debug(f"Hook Event: {hook_event} (raw: {hook_data.get('hook_event_name')})")
    logger.debug(f"Tool Name: {tool_name} (raw: {hook_data.get('tool_name')})")

    file_path = extract_tool_input_value(hook_data, InputKey.FILE_PATH)
    if file_path:
        file_ext = get_file_extension(file_path)
        logger.debug(f"File Path: {file_path} -> Extension: {file_ext}")

    command = extract_tool_input_value(hook_data, InputKey.COMMAND)
    if command:
        git_cmd = get_git_command(command)
        cmd_type = get_command_type(command)
        logger.debug(f"Command: {command}")
        logger.debug(f"  -> Git Command: {git_cmd}")
        logger.debug(f"  -> Command Type: {cmd_type}")

    message = hook_data.get(InputKey.MESSAGE.value)
    if message:
        msg_type = categorize_notification_message(message)
        logger.debug(f"Notification: {message} -> Type: {msg_type}")

    if tool_name:
        logger.debug(f"Tool Categories:")
        logger.debug(f"  -> File Operation: {is_file_operation_tool(tool_name)}")
        logger.debug(f"  -> System Tool: {is_system_tool(tool_name)}")
        logger.debug(f"  -> Search Tool: {is_search_tool(tool_name)}")

    logger.debug("=== END HOOK DATA ANALYSIS ===")
