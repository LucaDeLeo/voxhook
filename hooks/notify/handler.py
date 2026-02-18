#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx",
# ]
# ///
"""
Voxhook Push Notification Handler
==================================

Sends push notifications via ntfy.sh based on Claude Code hook events.
Uses notification_mapping.json to map events to appropriate messages.

Author: Chong-U (chong-u@aioriented.dev)
Created: 2025
Purpose: Push notification system for Claude Code with context-aware messaging

Usage:
  python handler.py --topic=my-topic
  python handler.py --topic=my-topic --server=https://ntfy.sh
"""

import json
import sys
import argparse
import logging
import random
from pathlib import Path
from typing import Optional

# Add parent directory to path for importing common module
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import (
    HookEvent,
    ToolName,
    InputKey,
    FileExtension,
    GitCommand,
    CommandType,
    NotificationType,
    get_hook_event,
    get_tool_name,
    get_file_extension,
    get_git_command,
    get_command_type,
    categorize_notification_message,
    extract_tool_input_value,
    is_file_operation_tool,
    debug_hook_data,
    enum_to_json_value,
)

# Type aliases for complex recurring types
from typing import Union
NotificationMapping = dict[str, Union[dict[str, str], str, list[str]]]
ToolInput = dict[str, str]
HookData = dict[str, Union[str, dict, None]]
MessageVariations = Union[str, list[str]]

def setup_module_logger(module_name: str, log_file: Path | None = None) -> logging.Logger:
    """Set up a module-specific logger with file handler."""
    logger = logging.getLogger(module_name)

    if logger.handlers:
        return logger  # Already configured

    if log_file is None:
        log_file = Path(__file__).parent / "debug.log"

    handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    return logger

# Initialize module logger
logger = setup_module_logger('voxhook.notify')

def load_notification_mapping() -> NotificationMapping:
    """Load notification mapping configuration from JSON file."""
    script_dir = Path(__file__).parent
    mapping_file = script_dir / "notification_mapping.json"

    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
            logger.debug(f"Loaded notification mapping from {mapping_file}")
            return mapping
    except Exception as e:
        # Fallback mapping if file doesn't exist
        logger.error(f"Could not load notification_mapping.json: {e}, using fallback")
        return {
            "hook_events": {"Stop": "Task completed", "Notification": "Claude notification"},
            "tools": {"Read": "Reading file", "Edit": "Editing code", "Bash": "Running command"},
            "default": {"title": "Claude Code", "message": "Task completed"}
        }

def get_context_aware_notification(hook_event_name: HookEvent, tool_name: ToolName | None = None, tool_input: ToolInput | None = None, input_data: HookData | None = None) -> dict[str, str]:
    """Map Claude's hook/tool names to context-aware notification messages with variation support."""
    mapping = load_notification_mapping()

    # Special handling for Notification events with message context
    if hook_event_name == HookEvent.NOTIFICATION and input_data:
        notification_data = _get_notification_message(mapping, input_data)
        if notification_data:
            logger.debug(f"Notification message mapping: '{notification_data}'")
            return notification_data

    # Try context-aware patterns for file operations and bash commands
    if hook_event_name in [HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE] and tool_name and tool_input:
        context_notification = _get_context_notification(mapping, tool_name, tool_input)
        if context_notification:
            logger.debug(f"Context-aware mapping: {hook_event_name} + {tool_name} -> '{context_notification}'")
            return context_notification
        else:
            logger.warning(f"No context pattern found for {tool_name} with {hook_event_name}, falling back to tool mapping")

    # Fallback to original tool-based mapping
    if hook_event_name in [HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE] and tool_name:
        if tool_name.value in mapping["tools"]:
            notification_data = _select_variation(mapping["tools"][tool_name.value])
            logger.debug(f"Tool mapping: '{tool_name}' -> '{notification_data}' for {hook_event_name}")
            return _ensure_notification_format(notification_data)
        else:
            logger.warning(f"No tool mapping found for '{tool_name}', falling back to hook event mapping")

    # Then try hook events (Stop, Notification, etc.)
    if hook_event_name.value in mapping["hook_events"]:
        hook_config = mapping["hook_events"][hook_event_name.value]

        if isinstance(hook_config, dict):
            if tool_name and tool_name.value in hook_config:
                notification_data = _select_variation(hook_config[tool_name.value])
                logger.debug(f"Tool-specific hook mapping: '{hook_event_name}' + '{tool_name}' -> '{notification_data}'")
                return _ensure_notification_format(notification_data)
            elif "default" in hook_config:
                notification_data = _select_variation(hook_config["default"])
                logger.debug(f"Hook event default mapping: '{hook_event_name}' -> '{notification_data}'")
                return _ensure_notification_format(notification_data)
        else:
            notification_data = _select_variation(hook_config)
            logger.debug(f"Hook event mapping: '{hook_event_name}' -> '{notification_data}'")
            return _ensure_notification_format(notification_data)
    else:
        logger.warning(f"No hook event mapping found for '{hook_event_name}', using default notification")

    # Final fallback to default
    default_config = mapping["default"]
    logger.warning(f"Default fallback for hook='{hook_event_name}', tool='{tool_name}'")
    return _ensure_notification_format(default_config)

def _get_context_notification(mapping: NotificationMapping, tool_name: ToolName, tool_input: ToolInput) -> dict[str, str] | None:
    """Get context-specific notification based on file extensions, filenames, or command patterns."""
    context_patterns = mapping.get("context_patterns", {})

    if is_file_operation_tool(tool_name):
        return _get_file_operation_notification(context_patterns, tool_name, tool_input)

    if tool_name == ToolName.BASH:
        return _get_bash_command_notification(context_patterns, tool_input)

    return None

def _get_file_operation_notification(context_patterns: dict[str, dict], tool_name: ToolName, tool_input: ToolInput) -> dict[str, str] | None:
    """Get notification for file operations based on file extension or filename."""
    file_ops = context_patterns.get("file_operations", {})

    base_tool_name = tool_name.value
    if tool_name in [ToolName.MULTI_EDIT, ToolName.NOTEBOOK_EDIT]:
        base_tool_name = ToolName.EDIT.value
    elif tool_name == ToolName.NOTEBOOK_READ:
        base_tool_name = ToolName.READ.value

    tool_patterns = file_ops.get(base_tool_name, {})
    file_path = tool_input.get(InputKey.FILE_PATH.value, "")

    if not file_path:
        return None

    file_extension = get_file_extension(file_path)
    path_obj = Path(file_path)
    filename = path_obj.name

    by_filename = tool_patterns.get("by_filename", {})
    if filename in by_filename:
        return _ensure_notification_format(_select_variation(by_filename[filename]))

    by_extension = tool_patterns.get("by_extension", {})
    if file_extension and file_extension.value in by_extension:
        return _ensure_notification_format(_select_variation(by_extension[file_extension.value]))

    default_notifications = tool_patterns.get("default", [])
    if default_notifications:
        return _ensure_notification_format(_select_variation(default_notifications))

    return None

def _get_bash_command_notification(context_patterns: dict[str, dict], tool_input: ToolInput) -> dict[str, str] | None:
    """Get notification for bash commands based on command patterns."""
    bash_commands = context_patterns.get("bash_commands", {})
    command = tool_input.get(InputKey.COMMAND.value, "")

    if not command:
        return None

    git_command = get_git_command(command)
    if git_command:
        git_patterns = bash_commands.get("git", {})
        if isinstance(git_patterns, dict) and git_command.value in git_patterns:
            return _ensure_notification_format(_select_variation(git_patterns[git_command.value]))

    command_type = get_command_type(command)
    if command_type:
        cmd_patterns = bash_commands.get(command_type.value, {})
        if isinstance(cmd_patterns, dict):
            for pattern, notifications in cmd_patterns.items():
                if command.strip().startswith(pattern):
                    return _ensure_notification_format(_select_variation(notifications))
        elif isinstance(cmd_patterns, list):
            return _ensure_notification_format(_select_variation(cmd_patterns))

    default_notifications = bash_commands.get("default", [])
    if default_notifications:
        return _ensure_notification_format(_select_variation(default_notifications))

    return None

def _get_notification_message(mapping: NotificationMapping, input_data: HookData) -> dict[str, str] | None:
    """Get context-specific notification for Notification events based on message content."""
    notification_config = mapping["hook_events"].get(HookEvent.NOTIFICATION.value, {})

    if not isinstance(notification_config, dict):
        return _ensure_notification_format(_select_variation(notification_config))

    message = input_data.get(InputKey.MESSAGE.value, "")
    if not message:
        return None

    notification_type = categorize_notification_message(message)

    config_key = notification_type.value
    if config_key in notification_config:
        logger.debug(f"{notification_type.name} detected: {message}")
        return _ensure_notification_format(_select_variation(notification_config[config_key]))

    if "default" in notification_config:
        logger.debug(f"Using default notification for: {message}")
        return _ensure_notification_format(_select_variation(notification_config["default"]))

    return None

def _select_variation(messages: MessageVariations) -> str | dict[str, str]:
    """Select a random variation from available message options."""
    if isinstance(messages, str):
        return messages
    elif isinstance(messages, dict):
        return messages
    elif isinstance(messages, list) and messages:
        return random.choice(messages)
    return "Task completed"

def _ensure_notification_format(notification_data: str | dict[str, str]) -> dict[str, str]:
    """Ensure notification data is in the correct format with title and message."""
    if isinstance(notification_data, dict):
        return notification_data
    elif isinstance(notification_data, str):
        return {"title": "Claude Code", "message": notification_data}
    else:
        return {"title": "Claude Code", "message": "Task completed"}

def send_push_notification(topic: str, title: str, message: str, server: str = "https://ntfy.sh", priority: int = 3, tags: str = "robot") -> bool:
    """Send a push notification via ntfy.sh."""
    logger.info(f"Sending push notification: {title} - {message}")

    try:
        import httpx

        url = f"{server.rstrip('/')}/{topic}"

        try:
            safe_tags = tags.encode('ascii', errors='ignore').decode('ascii') if tags else ""
            if not safe_tags and tags:
                safe_tags = "robot"
        except Exception:
            safe_tags = "robot"

        try:
            safe_title = ''.join(char for char in title if ord(char) < 128) if title else "Claude Code"
            safe_title = safe_title.strip()
            if not safe_title:
                safe_title = "Claude Code"
        except Exception:
            safe_title = "Claude Code"

        headers = {
            "Title": safe_title,
            "Priority": str(priority),
            "Tags": safe_tags,
        }

        with httpx.Client(timeout=10.0) as client:
            message_bytes = message.encode('utf-8') if isinstance(message, str) else message
            response = client.post(url, content=message_bytes, headers=headers)

            if response.status_code == 200:
                logger.info(f"Push notification sent successfully to {topic}")
                return True
            else:
                logger.error(f"Push notification failed: HTTP {response.status_code} - {response.text}")
                return False

    except ImportError as e:
        logger.error(f"httpx not available: {e}")
        return False

    except Exception as e:
        logger.error(f"Push notification failed: {e}")
        return False

def main() -> None:
    """Main function - reads Claude's JSON hook data and sends appropriate push notification."""
    parser = argparse.ArgumentParser(description='Voxhook push notification handler')
    parser.add_argument('--topic', required=True, help='ntfy.sh topic name')
    parser.add_argument('--server', default='https://ntfy.sh', help='ntfy.sh server URL')
    parser.add_argument('--priority', type=int, default=3, choices=range(1, 6), help='Notification priority (1-5)')
    parser.add_argument('--tags', default='robot', help='Tags for notification')
    parser.add_argument('--debug', action='store_true', help='Enable verbose debug logging')

    args = parser.parse_args()
    topic = args.topic
    server = args.server
    priority = args.priority
    tags = args.tags
    debug_mode = args.debug

    if debug_mode:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled - verbose logging active")

    logger.info(f"Push notification hook started for topic: {topic}, server: {server}, debug: {debug_mode}")

    try:
        input_data = json.load(sys.stdin)

        if debug_mode:
            logger.debug("=" * 60)
            logger.debug("HOOK DATA DUMP:")
            logger.debug(json.dumps(input_data, indent=2, default=str))
            logger.debug("=" * 60)

        hook_event_name = get_hook_event(input_data)
        tool_name = get_tool_name(input_data)
        tool_input = input_data.get(InputKey.TOOL_INPUT.value, {})

        if hook_event_name == HookEvent.NOTIFICATION:
            notification_message = input_data.get(InputKey.MESSAGE.value, "No message provided")
            logger.info(f"NOTIFICATION EVENT: {notification_message}")
            notification_type = categorize_notification_message(notification_message)
            logger.info(f"Notification type: {notification_type.name}")

        if hook_event_name == HookEvent.SUBAGENT_STOP:
            stop_hook_active = input_data.get(InputKey.STOP_HOOK_ACTIVE.value, False)
            logger.info(f"SUBAGENT STOP EVENT (stop_hook_active={stop_hook_active})")

        context_info = ""
        if tool_input:
            if InputKey.FILE_PATH.value in tool_input:
                context_info = f" -> {tool_input[InputKey.FILE_PATH.value]}"
            elif InputKey.COMMAND.value in tool_input:
                context_info = f" -> {tool_input[InputKey.COMMAND.value]}"
            elif InputKey.PATTERN.value in tool_input:
                context_info = f" -> searching '{tool_input[InputKey.PATTERN.value]}'"

        logger.info(f"Processing: {hook_event_name} + {tool_name or 'None'}{context_info}")

        if hook_event_name:
            notification_data = get_context_aware_notification(hook_event_name, tool_name, tool_input, input_data)
        else:
            logger.warning(f"Unknown hook event, using fallback notification")
            notification_data = {"title": "Claude Code", "message": "Task completed"}

        success = send_push_notification(
            topic=topic,
            title=notification_data["title"],
            message=notification_data["message"],
            server=server,
            priority=priority,
            tags=tags
        )

        if not success:
            logger.error("Failed to send push notification")
            sys.exit(1)

    except json.JSONDecodeError as e:
        default_notification = {"title": "Claude Code", "message": "Task completed"}
        logger.warning(f"No JSON input - using default notification, error: {e}")

        success = send_push_notification(
            topic=topic,
            title=default_notification["title"],
            message=default_notification["message"],
            server=server,
            priority=priority,
            tags=tags
        )

        if not success:
            sys.exit(1)

    except Exception as e:
        default_notification = {"title": "Claude Code", "message": "Task completed"}
        logger.error(f"Hook parsing error - using default notification, error: {e}")

        success = send_push_notification(
            topic=topic,
            title=default_notification["title"],
            message=default_notification["message"],
            server=server,
            priority=priority,
            tags=tags
        )

        if not success:
            sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    main()
