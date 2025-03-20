#!/usr/bin/env python3
"""
Script to collect AppleScript APIs from installed applications and store them as JSON.
"""

import os
import json
import plistlib
from pathlib import Path
import glob
import xml.etree.ElementTree as ET
import re
import html


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


def extract_description(element, debug=False):
    """
    Extract description from an element using multiple methods:
    1. Check for description attribute directly
    2. Look for documentation sub-element
    3. Look for description sub-element
    4. Check for comment attribute
    """
    if element is None:
        return ""

    # Method 1: Check description attribute
    if "description" in element.attrib:
        desc = element.attrib["description"].strip()
        if desc:
            return desc

    # Method 2: Look for documentation sub-element
    doc_elem = element.find("./documentation")
    if doc_elem is not None:
        # Extract text from the documentation element
        doc_text = get_text_content(doc_elem)
        if doc_text:
            return doc_text

    # Method 3: Look for description sub-element
    desc_elem = element.find("./description")
    if desc_elem is not None:
        desc_text = get_text_content(desc_elem)
        if desc_text:
            return desc_text

    # Method 4: Check for comment attribute
    if "comment" in element.attrib:
        comment = element.attrib["comment"].strip()
        if comment:
            return comment

    # Method 5: Check for a summary element
    summary_elem = element.find("./summary")
    if summary_elem is not None:
        summary_text = get_text_content(summary_elem)
        if summary_text:
            return summary_text

    return ""


def get_text_content(element, default=""):
    """Extract text content from an element, including nested elements."""
    if element is None:
        return default

    # Start with the element's direct text
    all_text = []
    if element.text and element.text.strip():
        all_text.append(element.text.strip())

    # Process all child elements
    for child in element:
        if child.tag in ["html", "cocoa", "p", "text"]:
            # For HTML content, try to extract it as plain text
            html_content = ET.tostring(child, encoding="unicode", method="html")
            # Basic HTML-to-text conversion
            html_content = html_content.replace("<br>", "\n").replace("<br/>", "\n")
            # Use the html module to unescape entities
            plain_text = html.unescape(re.sub(r"<[^>]+>", " ", html_content))
            plain_text = re.sub(r"\s+", " ", plain_text).strip()
            if plain_text:
                all_text.append(plain_text)
        else:
            # Recursively get text from other elements
            child_text = get_text_content(child)
            if child_text:
                all_text.append(child_text)

        # Also check if there's tail text
        if child.tail and child.tail.strip():
            all_text.append(child.tail.strip())

    result = " ".join(all_text)
    return result or default


def find_coercion_for_type(coercions, type_name):
    """Find coercion information for a specific type."""
    if not coercions:
        return None
    for coercion in coercions:
        if coercion.get("type") == type_name:
            return coercion
    return None


def parse_sdef_to_comprehensive_json(sdef_content, app_name):
    """Parse SDEF XML content to a comprehensive JSON representation including descriptions."""
    if not sdef_content:
        return {"applicationName": app_name, "suites": []}

    try:
        # Parse XML
        root = ET.fromstring(sdef_content)

        # Create the base structure
        parsed_data = {"applicationName": app_name, "suites": [], "coercions": []}

        # Get dictionary description if available
        dictionary = root.find(".//dictionary")
        if dictionary is not None:
            parsed_data["description"] = extract_description(dictionary)
            # Check for application version
            dictionary_version = dictionary.get("version", "")
            if dictionary_version:
                parsed_data["version"] = dictionary_version
            else:
                version_elem = dictionary.find('.//documentation[@key="version"]')
                if version_elem is not None:
                    parsed_data["version"] = get_text_content(version_elem)

        # Process coercions (type conversions)
        for coercion in root.findall(".//coercion"):
            coercion_data = {
                "from": coercion.get("from", ""),
                "to": coercion.get("to", ""),
                "description": extract_description(coercion),
            }
            parsed_data["coercions"].append(coercion_data)

        # Process each suite
        for suite in root.findall(".//suite"):
            suite_name = suite.get("name", "")
            print(f"  Processing suite: {suite_name}")

            suite_data = {
                "name": suite_name,
                "code": suite.get("code", ""),
                "description": extract_description(suite),
                "classes": [],
                "commands": [],
                "events": [],
                "enumerations": [],
            }

            # Process classes
            for cls in suite.findall("./class"):
                cls_name = cls.get("name", "")
                print(f"    Processing class: {cls_name}")

                cls_data = {
                    "name": cls_name,
                    "code": cls.get("code", ""),
                    "inherits": cls.get("inherits", ""),
                    "plural": cls.get("plural", ""),
                    "description": extract_description(cls),
                    "properties": [],
                    "elements": [],
                    "responds_to": [],
                    "contents": [],
                }

                # Process contents (what this class contains)
                contents_elem = cls.find("./contents")
                if contents_elem is not None:
                    for content_type in contents_elem.findall("./*"):
                        cls_data["contents"].append(
                            {
                                "type": content_type.tag,
                                "name": content_type.get("name", ""),
                                "description": extract_description(content_type),
                            }
                        )

                # Process properties
                for prop in cls.findall("./property"):
                    prop_name = prop.get("name", "")
                    print(f"      Processing property: {prop_name}")

                    prop_data = {
                        "name": prop_name,
                        "code": prop.get("code", ""),
                        "type": prop.get("type", ""),
                        "access": prop.get("access", ""),  # r/o, w/o, or r/w
                        "description": extract_description(prop),
                    }
                    cls_data["properties"].append(prop_data)

                # Process elements (contained by this class)
                for elem in cls.findall("./element"):
                    elem_data = {
                        "type": elem.get("type", ""),
                        "access": elem.get("access", ""),
                        "description": extract_description(elem),
                    }
                    cls_data["elements"].append(elem_data)

                # Process responds-to section
                responds_to = cls.find("./responds-to")
                if responds_to is not None:
                    for cmd in responds_to.findall("./command"):
                        cls_data["responds_to"].append(cmd.get("name", ""))

                suite_data["classes"].append(cls_data)

            # Process commands
            for cmd in suite.findall("./command"):
                cmd_name = cmd.get("name", "")
                print(f"    Processing command: {cmd_name}")

                cmd_data = {
                    "name": cmd_name,
                    "code": cmd.get("code", ""),
                    "description": extract_description(cmd),
                    "parameters": [],
                    "result": {},
                }

                # Process direct parameter (if any)
                direct_param = cmd.find("./direct-parameter")
                if direct_param is not None:
                    cmd_data["direct_parameter"] = {
                        "type": direct_param.get("type", ""),
                        "description": extract_description(direct_param),
                        "optional": direct_param.get("optional", "no") == "yes",
                    }

                # Process parameters
                for param in cmd.findall("./parameter"):
                    param_data = {
                        "name": param.get("name", ""),
                        "code": param.get("code", ""),
                        "type": param.get("type", ""),
                        "description": extract_description(param),
                        "optional": param.get("optional", "no") == "yes",
                    }
                    cmd_data["parameters"].append(param_data)

                # Process result
                result = cmd.find("./result")
                if result is not None:
                    cmd_data["result"] = {
                        "type": result.get("type", ""),
                        "description": extract_description(result),
                    }

                suite_data["commands"].append(cmd_data)

            # Process events
            for event in suite.findall("./event"):
                event_data = {
                    "name": event.get("name", ""),
                    "code": event.get("code", ""),
                    "description": extract_description(event),
                    "parameters": [],
                    "result": {},
                }

                # Process parameters
                for param in event.findall("./parameter"):
                    param_data = {
                        "name": param.get("name", ""),
                        "code": param.get("code", ""),
                        "type": param.get("type", ""),
                        "description": extract_description(param),
                        "optional": param.get("optional", "no") == "yes",
                    }
                    event_data["parameters"].append(param_data)

                # Process result
                result = event.find("./result")
                if result is not None:
                    event_data["result"] = {
                        "type": result.get("type", ""),
                        "description": extract_description(result),
                    }

                suite_data["events"].append(event_data)

            # Process enumerations
            for enum in suite.findall("./enumeration"):
                enum_data = {
                    "name": enum.get("name", ""),
                    "code": enum.get("code", ""),
                    "description": extract_description(enum),
                    "enumerators": [],
                }

                # Process enumerators
                for enumerator in enum.findall("./enumerator"):
                    enumerator_data = {
                        "name": enumerator.get("name", ""),
                        "code": enumerator.get("code", ""),
                        "description": extract_description(enumerator),
                    }
                    enum_data["enumerators"].append(enumerator_data)

                suite_data["enumerations"].append(enum_data)

            parsed_data["suites"].append(suite_data)

        # Process relationships between classes
        for suite in parsed_data["suites"]:
            for cls in suite["classes"]:
                # Add "contained by" information by looking for elements that reference this class
                contained_by = []
                for s in parsed_data["suites"]:
                    for c in s["classes"]:
                        for elem in c["elements"]:
                            if elem["type"] == cls["name"]:
                                contained_by.append(
                                    {"class": c["name"], "suite": s["name"]}
                                )

                if contained_by:
                    cls["contained_by"] = contained_by

        return parsed_data

    except Exception as e:
        print(f"  Error parsing XML: {e}")
        import traceback

        traceback.print_exc()
        return {"applicationName": app_name, "suites": [], "error": str(e)}


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
