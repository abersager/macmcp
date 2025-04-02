#!/usr/bin/env python3
"""
Script to manually register and activate the Calendar app for integration testing.
"""

import json
import os
from macmcp.macmcp import (
    initialize_server,
    activate_app,
    registered_apps,
    active_apps,
    CONFIG_FILE,
    register_app_commands,
)


def main():
    print("Initializing MacMCP server...")
    initialize_server()

    # Check if Calendar is registered
    if "Calendar" not in registered_apps:
        print("Manually registering Calendar app...")
        # Add Calendar to registered_apps even though it's not active yet
        registered_apps["Calendar"] = []

        # Load the Calendar API data
        try:
            with open("applescript_apis/Calendar.json", "r") as f:
                calendar_api = json.load(f)
                print(f"Loaded Calendar API data")
        except Exception as e:
            print(f"Error loading Calendar API: {e}")
            return
    else:
        print("Calendar already registered")

    # Now activate the Calendar app (this should work since it's in registered_apps)
    print("Activating Calendar app...")
    result = activate_app("Calendar")
    print(result)

    # Load again to register commands (should work now since Calendar is active)
    if "Calendar" in active_apps:
        print("Loading Calendar commands...")
        # Load the Calendar API again to register commands
        with open("applescript_apis/Calendar.json", "r") as f:
            calendar_api = json.load(f)
            register_app_commands("Calendar", calendar_api)

    print(f"Current active apps: {active_apps}")
    print(f"Registered commands for Calendar: {registered_apps.get('Calendar', [])}")
    print("")
    print("You can now run the integration test with:")
    print("pytest tests/test_macmcp.py::test_calendar_list_calendars_integration -v")


if __name__ == "__main__":
    main()
