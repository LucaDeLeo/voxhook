#!/usr/bin/env python3
"""
Voxhook Common Utilities
========================

Centralized enums and utility functions for the Voxhook hook system,
ensuring type safety and preventing string literal errors.

Author: Chong-U (chong-u@aioriented.dev)
Created: 2025
Purpose: Type-safe constants and utilities for Voxhook
"""

# Import main enum classes for easy access
from .enums import (
    HookEvent,
    ToolName,
    InputKey,
    FileExtension,
    GitCommand,
    CommandType,
    NotificationType,
    # Utility sets
    FILE_OPERATION_TOOLS,
    SEARCH_TOOLS,
    SYSTEM_TOOLS,
    WORKFLOW_TOOLS,
    WEB_TOOLS,
    TOOL_EVENTS,
    STANDALONE_EVENTS,
)

# Import awareness detection
from .awareness import AwarenessTier, detect_awareness

# Import utility functions
from .utils import (
    safe_enum_from_string,
    get_hook_event,
    get_tool_name,
    get_file_extension,
    get_git_command,
    get_command_type,
    categorize_notification_message,
    extract_tool_input_value,
    is_file_operation_tool,
    is_system_tool,
    is_search_tool,
    enum_to_json_value,
    debug_hook_data,
)

__all__ = [
    # Awareness
    "AwarenessTier",
    "detect_awareness",
    # Enums
    "HookEvent",
    "ToolName",
    "InputKey",
    "FileExtension",
    "GitCommand",
    "CommandType",
    "NotificationType",
    # Utility sets
    "FILE_OPERATION_TOOLS",
    "SEARCH_TOOLS",
    "SYSTEM_TOOLS",
    "WORKFLOW_TOOLS",
    "WEB_TOOLS",
    "TOOL_EVENTS",
    "STANDALONE_EVENTS",
    # Utility functions
    "safe_enum_from_string",
    "get_hook_event",
    "get_tool_name",
    "get_file_extension",
    "get_git_command",
    "get_command_type",
    "categorize_notification_message",
    "extract_tool_input_value",
    "is_file_operation_tool",
    "is_system_tool",
    "is_search_tool",
    "enum_to_json_value",
    "debug_hook_data",
]

__version__ = "1.0.0"
__author__ = "Chong-U (chong-u@aioriented.dev)"
