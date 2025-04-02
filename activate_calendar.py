#!/usr/bin/env python3
"""
Script to activate the Calendar app for integration testing.
"""

from macmcp.macmcp import (
    initialize_server,
    activate_app,
    save_config,
    active_apps,
    CONFIG_FILE,
)
import json
import os


def main():
    print("Initializing MacMCP server...")
    initialize_server()

    print(f"Activating Calendar app...")
    if "Calendar" not in active_apps:
        result = activate_app("Calendar")
        print(result)
    else:
        print("Calendar app is already active")

    print(f"Current active apps: {active_apps}")
    print(f"Configuration saved to {os.path.abspath(CONFIG_FILE)}")
    print("")
    print("You can now run the integration test with:")
    print("pytest tests/test_macmcp.py::test_calendar_list_calendars_integration -v")


if __name__ == "__main__":
    main()
