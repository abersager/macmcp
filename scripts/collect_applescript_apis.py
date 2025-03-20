#!/usr/bin/env python3
"""
Script to collect AppleScript APIs from installed applications and store them as JSON.
"""

import os
import json
import plistlib
from pathlib import Path
import re
import glob
import xml.etree.ElementTree as ET


def get_applications():
    """Get a list of application paths on the system."""
    common_app_dirs = [
        "/Applications",
        "/System/Applications",
        os.path.expanduser("~/Applications"),
    ]

    applications = []
    for app_dir in common_app_dirs:
        if os.path.exists(app_dir):
            for item in os.listdir(app_dir):
                if item.endswith(".app"):
                    app_path = os.path.join(app_dir, item)
                    applications.append(app_path)

    return applications


def find_sdef_file(app_path):
    """Find SDEF file within the application bundle without launching the app."""
    # Common SDEF file locations
    sdef_paths = [
        os.path.join(app_path, "Contents/Resources/Scripts/sdef"),
        os.path.join(app_path, "Contents/Resources/sdef"),
    ]

    # Check specific paths first
    for path in sdef_paths:
        if os.path.exists(path) and os.path.isfile(path):
            return path

    # Search for any .sdef files in Resources
    resource_dir = os.path.join(app_path, "Contents/Resources")
    if os.path.exists(resource_dir):
        sdef_files = glob.glob(os.path.join(resource_dir, "*.sdef"))
        if sdef_files:
            return sdef_files[0]  # Return the first .sdef file found

    # Check Info.plist for SDEF file reference
    plist_path = os.path.join(app_path, "Contents/Info.plist")
    if os.path.exists(plist_path):
        try:
            with open(plist_path, "rb") as f:
                plist_data = plistlib.load(f)

            # Check for OSAScriptingDefinition
            if "OSAScriptingDefinition" in plist_data:
                sdef_name = plist_data["OSAScriptingDefinition"]
                sdef_path = os.path.join(app_path, "Contents/Resources", sdef_name)
                if os.path.exists(sdef_path):
                    return sdef_path
        except Exception:
            pass

    return None


def has_applescript_support(app_path):
    """Check if an application has AppleScript support without launching it."""
    # Method 1: Check for SDEF file
    if find_sdef_file(app_path):
        return True

    # Method 2: Check Info.plist for AppleScript capabilities
    plist_path = os.path.join(app_path, "Contents/Info.plist")
    if os.path.exists(plist_path):
        try:
            with open(plist_path, "rb") as f:
                plist_data = plistlib.load(f)

            # Check for NSAppleScriptEnabled
            if plist_data.get("NSAppleScriptEnabled", False):
                return True

            # Some apps declare scripting support in other ways
            for key in ["OSAScriptingDefinition", "NSServices"]:
                if key in plist_data:
                    return True
        except Exception:
            pass

    # Look for compiled script files
    script_dirs = [
        os.path.join(app_path, "Contents/Resources/Scripts"),
        os.path.join(app_path, "Contents/Scripts"),
    ]
    for script_dir in script_dirs:
        if os.path.exists(script_dir):
            script_files = glob.glob(os.path.join(script_dir, "*.scpt"))
            if script_files:
                return True

    return False


def read_sdef_file(sdef_path):
    """Read SDEF file contents safely."""
    try:
        with open(sdef_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        # Try with different encodings if UTF-8 fails
        try:
            with open(sdef_path, "r", encoding="latin-1") as f:
                return f.read()
        except Exception as e:
            print(f"  Error reading SDEF file with latin-1 encoding: {e}")
    except Exception as e:
        print(f"  Error reading SDEF file: {e}")

    return None


def parse_sdef_to_json(sdef_content, app_name):
    """Parse SDEF XML content to a structured JSON representation."""
    if not sdef_content:
        return {
            "applicationName": app_name,
            "classes": [],
            "commands": [],
            "enumerations": [],
        }

    try:
        # Try to use ElementTree for more reliable XML parsing
        root = ET.fromstring(sdef_content)

        parsed_data = {
            "applicationName": app_name,
            "classes": [],
            "commands": [],
            "enumerations": [],
        }

        # Parse classes
        for class_elem in root.findall(".//class"):
            class_data = {"name": class_elem.get("name", ""), "properties": []}

            # Parse properties
            for prop in class_elem.findall(".//property"):
                class_data["properties"].append(
                    {"name": prop.get("name", ""), "type": prop.get("type", "")}
                )

            parsed_data["classes"].append(class_data)

        # Parse commands
        for cmd_elem in root.findall(".//command"):
            cmd_data = {"name": cmd_elem.get("name", ""), "parameters": []}

            # Parse parameters
            for param in cmd_elem.findall(".//parameter"):
                cmd_data["parameters"].append(
                    {"name": param.get("name", ""), "type": param.get("type", "")}
                )

            parsed_data["commands"].append(cmd_data)

        # Parse enumerations
        for enum_elem in root.findall(".//enumeration"):
            enum_data = {"name": enum_elem.get("name", ""), "enumerators": []}

            # Parse enumerators
            for enumerator in enum_elem.findall(".//enumerator"):
                enum_data["enumerators"].append(
                    {
                        "name": enumerator.get("name", ""),
                        "code": enumerator.get("code", ""),
                    }
                )

            parsed_data["enumerations"].append(enum_data)

        return parsed_data

    except Exception as e:
        print(f"  Error parsing XML with ElementTree: {e}")
        # Fall back to regex-based parsing if ElementTree fails
        return fallback_parse_sdef(sdef_content, app_name)


def fallback_parse_sdef(sdef_content, app_name):
    """Fallback method using regex to parse SDEF when XML parsing fails."""
    parsed_data = {
        "applicationName": app_name,
        "classes": [],
        "commands": [],
        "enumerations": [],
    }

    # Extract class definitions
    class_matches = re.finditer(
        r'<class name="([^"]+)"[^>]*>.*?</class>', sdef_content, re.DOTALL
    )
    for match in class_matches:
        class_name = match.group(1)
        class_content = match.group(0)

        # Extract properties
        properties = []
        prop_matches = re.finditer(
            r'<property name="([^"]+)"[^>]*?type="([^"]+)"', class_content
        )
        for prop_match in prop_matches:
            properties.append(
                {"name": prop_match.group(1), "type": prop_match.group(2)}
            )

        parsed_data["classes"].append({"name": class_name, "properties": properties})

    # Extract command definitions
    cmd_matches = re.finditer(
        r'<command name="([^"]+)"[^>]*>.*?</command>', sdef_content, re.DOTALL
    )
    for match in cmd_matches:
        cmd_name = match.group(1)
        cmd_content = match.group(0)

        # Extract parameters
        parameters = []
        param_matches = re.finditer(
            r'<parameter name="([^"]+)"[^>]*?type="([^"]+)"', cmd_content
        )
        for param_match in param_matches:
            parameters.append(
                {"name": param_match.group(1), "type": param_match.group(2)}
            )

        parsed_data["commands"].append({"name": cmd_name, "parameters": parameters})

    # Extract enumerations
    enum_matches = re.finditer(
        r'<enumeration name="([^"]+)"[^>]*>.*?</enumeration>', sdef_content, re.DOTALL
    )
    for match in enum_matches:
        enum_name = match.group(1)
        enum_content = match.group(0)

        # Extract enumerators
        enumerators = []
        enumerator_matches = re.finditer(
            r'<enumerator name="([^"]+)"[^>]*?code="([^"]+)"', enum_content
        )
        for enum_match in enumerator_matches:
            enumerators.append(
                {"name": enum_match.group(1), "code": enum_match.group(2)}
            )

        parsed_data["enumerations"].append(
            {"name": enum_name, "enumerators": enumerators}
        )

    return parsed_data


def main():
    # Create output directory
    output_dir = Path("applescript_apis")
    output_dir.mkdir(exist_ok=True)

    # Get all applications
    applications = get_applications()
    print(f"Found {len(applications)} applications")

    # First pass: identify apps with AppleScript support
    scriptable_apps = []
    for app in applications:
        app_name = os.path.basename(app).replace(".app", "")
        print(f"Checking {app_name}...", end="", flush=True)

        if has_applescript_support(app):
            sdef_file = find_sdef_file(app)
            if sdef_file:
                print(f" Supports AppleScript (SDEF: {os.path.basename(sdef_file)})")
                scriptable_apps.append((app_name, app, sdef_file))
            else:
                print(" Supports AppleScript (but no accessible SDEF file)")
        else:
            print(" No AppleScript support")

    print(
        f"\nFound {len(scriptable_apps)} applications with accessible AppleScript definitions"
    )

    # Second pass: process only apps with accessible SDEF files
    for app_name, app_path, sdef_file in scriptable_apps:
        print(f"Processing {app_name}...")
        sdef_content = read_sdef_file(sdef_file)

        if sdef_content:
            # Parse SDEF to structured data
            api_data = parse_sdef_to_json(sdef_content, app_name)

            # Save to JSON file
            safe_name = re.sub(r"[^\w\-\.]", "_", app_name)
            json_path = output_dir / f"{safe_name}.json"

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(api_data, f, indent=2)

            print(f"  Saved API definition to {json_path}")
        else:
            print(f"  Could not read SDEF file for {app_name}")

    print(
        "\nProcess completed. AppleScript APIs have been saved to the 'applescript_apis' directory."
    )


if __name__ == "__main__":
    main()
