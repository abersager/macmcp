from mcp.server.fastmcp import FastMCP
import json
import os
import subprocess
import keyword
import builtins
import sys
from typing import Any, Dict, List, Optional, Set
import time

# Create an MCP server
mcp = FastMCP("macmcp")

# Store registered commands for discovery
registered_apps = {}
active_apps: Set[str] = set()

# Store parameter maps for functions
param_maps = {}

# Configuration file path
CONFIG_FILE = "applescript_apis/tool_config.json"


def debug_print(message):
    """Print debug messages to stderr"""
    sys.stderr.write(str(message) + "\n")
    sys.stderr.flush()


def load_config() -> set:
    """Load active applications from config file"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                active_apps = set(config.get("active_apps", []))
                debug_print(f"Loaded configuration: {len(active_apps)} active apps")
                return active_apps
    except Exception as e:
        debug_print(f"Error loading config: {e}")
    return set()


def save_config(active_apps: set) -> None:
    """Save active applications to config file"""
    try:
        config = {"active_apps": list(active_apps)}
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        debug_print("Configuration saved")
    except Exception as e:
        debug_print(f"Error saving config: {e}")


# Add tools to manage active/inactive apps
@mcp.tool()
def get_active_apps() -> List[str]:
    """Get list of currently active applications"""
    return sorted(list(active_apps))


@mcp.tool()
def get_inactive_apps() -> List[str]:
    """Get list of currently inactive applications"""
    return sorted(list(set(registered_apps.keys()) - active_apps))


@mcp.tool()
def activate_app(app_name: str) -> str:
    """Activate an application's tools"""
    if app_name not in registered_apps:
        return f"Error: Application '{app_name}' not found"

    active_apps.add(app_name)
    save_config(active_apps)

    # Re-register all commands for this app
    debug_print(f"Re-registering commands for {app_name}")
    for api_file in os.listdir("applescript_apis"):
        if api_file.endswith(".json"):
            try:
                with open(os.path.join("applescript_apis", api_file), "r") as f:
                    api_data = json.load(f)
                    if api_data.get("applicationName") == app_name:
                        register_app_commands(app_name, api_data)
                        break
            except Exception as e:
                debug_print(f"Error loading API file {api_file}: {e}")

    # Register resource access functions for this app
    register_app_resources(app_name)

    return f"Activated {app_name}"


@mcp.tool()
def deactivate_app(app_name: str) -> str:
    """Deactivate an application's tools"""
    if app_name not in registered_apps:
        return f"Error: Application '{app_name}' not found"

    active_apps.discard(app_name)
    save_config(active_apps)

    # Remove all commands for this app from the MCP tools
    debug_print(f"Removing commands for {app_name}")
    for name in list(mcp.tools.keys()):
        if name.startswith(f"{app_name.lower()}_"):
            del mcp.tools[name]

    return f"Deactivated {app_name}"


@mcp.tool()
def activate_all_apps() -> str:
    """Activate all application tools"""
    global active_apps
    active_apps = set(registered_apps.keys())
    save_config(active_apps)
    return "Activated all applications"


@mcp.tool()
def deactivate_all_apps() -> str:
    """Deactivate all application tools"""
    global active_apps
    active_apps.clear()
    save_config(active_apps)
    return "Deactivated all applications"


@mcp.tool()
def list_applescript_apps() -> List[str]:
    """List all available applications with AppleScript commands"""
    return sorted(list(active_apps))


@mcp.tool()
def list_app_commands(app_name: str) -> List[str]:
    """List all available AppleScript commands for a specific application"""
    if app_name not in registered_apps:
        return [
            f"Error: Application '{app_name}' not found. Use list_applescript_apps() to see available apps."
        ]

    return sorted(registered_apps.get(app_name, []))


@mcp.tool()
def get_command_info(app_name: str, command_name: str) -> Dict[str, Any]:
    """Get detailed information about a specific AppleScript command"""
    if app_name not in registered_apps:
        return {
            "error": f"Application '{app_name}' not found. Use list_applescript_apps() to see available apps."
        }

    if command_name not in registered_apps.get(app_name, []):
        return {
            "error": f"Command '{command_name}' not found for application '{app_name}'."
        }

    function_name = f"{app_name.lower().replace(' ', '_')}_{command_name.lower().replace(' ', '_').replace('-', '_')}"
    if function_name in globals():
        func = globals()[function_name]
        return {
            "app_name": app_name,
            "command_name": command_name,
            "description": func.__doc__,
            "function_name": function_name,
        }

    return {"error": f"Function for command '{command_name}' not found."}


def run_applescript_command(
    app_name: str,
    command: str,
    parameters: Optional[Dict[str, Any]] = None,
    param_map: Optional[Dict[str, str]] = None,
) -> Any:
    """Run an AppleScript command and return the result"""
    try:
        script_parts = [f'tell application "{app_name}"']

        if parameters and len(parameters) > 0:
            param_str_parts = []
            for py_name, value in parameters.items():
                if py_name == "self":  # Skip 'self' parameter if it exists
                    continue

                # Get the original AppleScript parameter name from the map
                original_name = (
                    param_map.get(py_name, py_name) if param_map else py_name
                )

                # In AppleScript, parameter names should NOT be quoted
                as_param_name = original_name

                # --- Value formatting (same as before) ---
                if isinstance(value, bool):
                    value_str = "true" if value else "false"
                elif isinstance(value, str):
                    # Basic escaping for quotes within strings
                    escaped_value = value.replace('"', '\\"')
                    value_str = f'"{escaped_value}"'
                elif isinstance(value, dict):
                    record_parts = []
                    for k, v in value.items():
                        if isinstance(v, bool):
                            v_str = "true" if v else "false"
                        elif isinstance(v, str):
                            escaped_v = v.replace('"', '\\"')
                            v_str = f'"{escaped_v}"'
                        else:
                            v_str = str(v)
                        record_parts.append(f"{k}:{v_str}")
                    value_str = "{{" + ", ".join(record_parts) + "}}"
                else:
                    value_str = str(value)
                # --- End Value Formatting ---

                # Use the correct AppleScript syntax:
                # If the parameter already starts with "with", don't add another "with"
                if as_param_name.startswith("with "):
                    param_str_parts.append(f" {as_param_name} {value_str}")
                else:
                    param_str_parts.append(f" with {as_param_name} {value_str}")

            param_str = "".join(param_str_parts)
            script_parts.append(f"{command}{param_str}")
        else:
            script_parts.append(command)

        script_parts.append("end tell")

        full_script = "\n".join(script_parts)

        # For debugging
        debug_print(f"Executing AppleScript:\n{full_script}")

        result = subprocess.run(
            ["osascript", "-e", full_script],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            debug_print(f"AppleScript error: {result.stderr}")
            return f"Error: {result.stderr.strip()}"

        return result.stdout.strip()
    except Exception as e:
        debug_print(f"Error executing AppleScript: {e}")
        return f"Error: {str(e)}"


def load_applescript_apis():
    """Load AppleScript APIs from JSON files in the applescript_apis directory"""
    apis_dir = "applescript_apis"

    if not os.path.exists(apis_dir):
        debug_print(f"Warning: {apis_dir} directory not found")
        return

    for filename in os.listdir(apis_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(apis_dir, filename)
            try:
                with builtins.open(filepath, "r") as f:
                    api_data = json.load(f)

                app_name = api_data.get("applicationName")
                if not app_name:
                    continue

                try:
                    register_app_commands(app_name, api_data)
                except Exception as e:
                    debug_print(f"Error registering commands for {app_name}: {e}")
                    continue
            except Exception as e:
                debug_print(f"Error loading {filepath}: {e}")


def register_app_commands(app_name: str, api_data: Dict[str, Any]):
    """Register commands for an application"""
    if app_name not in active_apps:
        debug_print(f"Skipping registration for inactive app: {app_name}")
        return

    debug_print(f"Registering commands for {app_name}")
    if app_name not in registered_apps:
        registered_apps[app_name] = []

    for suite in api_data.get("suites", []):
        for cmd in suite.get("commands", []):
            try:
                original_command_name = cmd["name"]
                if original_command_name not in registered_apps[app_name]:
                    registered_apps[app_name].append(original_command_name)

                func_name = f"{app_name.lower().replace(' ', '_')}_{original_command_name.lower().replace(' ', '_').replace('-', '_')}"

                # --- Parameter Handling ---
                python_params = []  # For function definition
                param_map_to_original = {}  # For mapping back in run_command
                for param in cmd.get("parameters", []):
                    original_name = param["name"]
                    sanitized_name = original_name.replace(" ", "_").replace("-", "_")
                    if keyword.iskeyword(sanitized_name):
                        sanitized_name = f"{sanitized_name}_"

                    param_map_to_original[sanitized_name] = original_name

                    if param.get("required", True):
                        python_params.append(sanitized_name)
                    else:
                        default_value = param.get("default", None)
                        if default_value is None:
                            default_value = "None"
                        elif isinstance(default_value, str):
                            # Ensure quotes within defaults are handled if needed, though exec might handle this
                            default_value = repr(default_value)
                        python_params.append(f"{sanitized_name}={default_value}")
                # --- End Parameter Handling ---

                func_def = f"def {func_name}({', '.join(python_params)}):"

                body = []
                body.append(
                    f'    """{cmd.get("description", "Execute AppleScript command")}"""'
                )
                body.append("    try:")
                # Use global param_maps instead of local variable
                body.append(f"        param_map = param_maps.get('{func_name}', {{}})")
                body.append(
                    "        local_params = {k: v for k, v in locals().items() if k != 'param_map'}"
                )
                body.append(
                    f"        return run_applescript_command('{app_name}', '{original_command_name}', local_params, param_map)"
                )
                body.append("    except Exception as e:")
                body.append("        return f'Error: {str(e)}'")

                # Create the function
                func_code = "\n".join([func_def] + body)

                if func_name not in globals():
                    debug_print(f"Creating function:\n{func_code}")
                    # Store parameter map in global param_maps dictionary
                    param_maps[func_name] = param_map_to_original
                    # Prepare context for exec with access to necessary globals
                    exec_globals = globals().copy()  # Use a copy of globals
                    exec(func_code, exec_globals)

                    # Copy the function from globals back to our context
                    func = exec_globals[func_name]

                    # Register the function as an MCP tool
                    mcp.tool()(func)
                    # Add to global namespace so it can be accessed by other code
                    globals()[func_name] = func

            except Exception as e:
                debug_print(
                    f"Error registering command {original_command_name} for {app_name} in suite {suite.get('name')}: {e}"
                )
                continue


@mcp.tool()
def initialize_server():
    """Initialize the MCP server by loading APIs and configuration"""
    global active_apps  # Declares intent to modify global

    debug_print("Loading configuration...")
    # Assigns the result of load_config() to the global active_apps
    active_apps = load_config()

    debug_print("Loading AppleScript APIs...")
    load_applescript_apis()  # Calls register_app_commands which reads global active_apps

    debug_print("Registering resource access tools...")
    # Register resource tools for all active apps
    for app_name in active_apps:
        register_app_resources(app_name)

    debug_print("MCP Server initialization complete.")
    active_count = len(active_apps)
    registered_count = sum(len(cmds) for cmds in registered_apps.values())
    debug_print(
        f"Successfully registered {active_count} applications with AppleScript commands"
    )
    debug_print(f"Total command count: {registered_count}")
    debug_print(f"Active applications: {active_count}")
    debug_print("Use list_applescript_apps() to discover available applications")


@mcp.tool()
def get_app_resource(app_name: str, resource_path: str) -> Any:
    """
    Get a resource or property from an application using AppleScript.

    Args:
        app_name: The name of the application to query
        resource_path: The resource path to retrieve (e.g. 'name of calendars', 'events of calendar "Work"')
                      or an AppleScript command to execute (e.g. 'make new event...')

    Returns:
        The value of the requested resource or result of the command
    """
    if app_name not in registered_apps and app_name not in active_apps:
        return f"Error: Application '{app_name}' not registered or activated"

    try:
        script = f"""
tell application "{app_name}"
    {resource_path}
end tell
"""
        debug_print(f"Executing AppleScript for resource retrieval:\n{script}")

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            debug_print(f"AppleScript error: {result.stderr}")
            error_msg = result.stderr.strip()

            # Provide more helpful information for common errors
            if "syntax error" in error_msg:
                if "date" in error_msg:
                    return f'Error: {error_msg}\n\nSuggestion: AppleScript date formats can be tricky. Try using one of these formats:\n- date "2023-04-15 14:30:00"\n- current date\n- (current date) + 30 * minutes'
                elif "Expected" in error_msg and "but found" in error_msg:
                    return f"Error: {error_msg}\n\nSuggestion: This appears to be an AppleScript syntax error. Check the command structure. For reference, use list_app_resources('{app_name}') to see example commands."
            elif "Invalid date" in error_msg:
                return f'Error: {error_msg}\n\nSuggestion: Try using the format date "YYYY-MM-DD HH:MM:SS" or current date.'
            elif "not found" in error_msg:
                return f"Error: {error_msg}\n\nSuggestion: The specified resource wasn't found. Check that the object exists."

            return f"Error: {error_msg}"

        return result.stdout.strip()
    except Exception as e:
        debug_print(f"Error executing AppleScript: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
def list_app_resources(app_name: str) -> Dict[str, Any]:
    """
    List available resources (objects, properties, and collections) for an application
    based on its AppleScript API definition file.

    This function helps discover what resources can be queried using get_app_resource.

    Args:
        app_name: The name of the application to introspect

    Returns:
        A dictionary containing available resource categories and examples
    """
    if app_name not in registered_apps and app_name not in active_apps:
        return {
            "error": f"Application '{app_name}' not registered or activated",
            "suggestion": "Use list_applescript_apps() to see available apps",
        }

    # Common basic properties that most apps have
    basic_properties = ["name", "version", "frontmost"]

    # AppleScript date format examples - important for working with dates
    date_format_info = {
        "current_date": "current date",
        "relative_date": "(current date) + 1 * days",
        "specific_date": 'date "2023-04-15 14:30:00"',
        "date_components": 'date "January 15, 2023 2:30:00 PM"',
        "note": "AppleScript date formats are locale-sensitive; the safest format is YYYY-MM-DD HH:MM:SS",
    }

    # First try to find the API definition file
    api_file_path = None
    api_data = None

    for file_name in os.listdir("applescript_apis"):
        if file_name.endswith(".json") and not file_name == "tool_config.json":
            try:
                with open(os.path.join("applescript_apis", file_name), "r") as f:
                    file_data = json.load(f)
                    if file_data.get("applicationName") == app_name:
                        api_file_path = os.path.join("applescript_apis", file_name)
                        api_data = file_data
                        break
            except Exception as e:
                debug_print(f"Error reading API file {file_name}: {e}")

    # If we found an API definition, extract resource information
    if api_data:
        classes = []
        collections = []
        class_properties = {}

        # Process all suites
        for suite in api_data.get("suites", []):
            # Extract classes from the suite
            for cls in suite.get("classes", []):
                class_name = cls.get("name", "").lower()
                if class_name and class_name not in classes:
                    classes.append(class_name)

                    # Store properties for this class
                    props = [prop.get("name") for prop in cls.get("properties", [])]
                    if props:
                        class_properties[class_name] = props

                    # Add plural form as a collection if it exists
                    plural = cls.get("plural")
                    if plural and plural not in collections:
                        collections.append(plural)
                    elif not plural and class_name not in collections:
                        # Use standard English pluralization rules if plural not specified
                        if class_name.endswith("s"):
                            plural_name = f"{class_name}es"
                        elif class_name.endswith("y"):
                            plural_name = f"{class_name[:-1]}ies"
                        else:
                            plural_name = f"{class_name}s"
                        collections.append(plural_name)

        # Generate examples based on the discovered classes and collections
        creation_examples = []
        query_examples = []
        modification_examples = []

        # Add query examples
        for collection in collections:
            query_examples.append(f"# Get all {collection}")
            query_examples.append(f"{collection}")
            query_examples.append(f"# Get names of {collection}")
            query_examples.append(f"name of {collection}")

            # Add example for filtering collection
            query_examples.append(f"# Find {collection} by name")
            query_examples.append(f'{collection} whose name contains "Example"')

        # Add creation examples for each class
        for cls in classes:
            # Find the corresponding collection
            collection = next((c for c in collections if c.startswith(cls)), None)
            if collection:
                creation_examples.append(f"# Create a new {cls}")

                # Generate properties based on available class properties
                property_examples = []
                if class_properties.get(cls):
                    # Get the first few properties that might be useful
                    useful_props = ["name", "title", "summary", "text", "content"]
                    prop = next(
                        (p for p in useful_props if p in class_properties.get(cls, [])),
                        None,
                    )

                    if prop:
                        property_examples.append(f'{prop}:"Example {cls.title()}"')

                        # Add date properties for date-related classes
                        if (
                            "date" in cls
                            or cls == "event"
                            or cls == "reminder"
                            or cls == "appointment"
                        ):
                            if "start date" in class_properties.get(cls, []):
                                property_examples.append(
                                    'start date:date "2023-04-15 14:30:00"'
                                )
                            if "end date" in class_properties.get(cls, []):
                                property_examples.append(
                                    'end date:date "2023-04-15 15:30:00"'
                                )
                            elif "due date" in class_properties.get(cls, []):
                                property_examples.append(
                                    'due date:date "2023-04-15 15:30:00"'
                                )

                # If no specific properties were found, add a generic name property
                if not property_examples:
                    property_examples.append(f'name:"Example {cls.title()}"')

                # Generate the full example with a generic approach
                properties_str = ", ".join(property_examples)

                # Generate creation example using the collection name as container
                creation_examples.append(
                    f"make new {cls} at end of {collection} with properties {{{properties_str}}}"
                )

            # Add modification example
            modification_examples.append(f"# Modify a {cls}")
            modification_examples.append(
                f'set name of first {cls} to "Modified {cls.title()}"'
            )

        # Return the extracted resource information
        return {
            "basic_properties": basic_properties,
            "classes": classes,
            "collections": collections,
            "class_properties": class_properties,
            "creation_examples": creation_examples,
            "query_examples": query_examples,
            "modification_examples": modification_examples,
            "date_formats": date_format_info,
            "source": f"Extracted from {api_file_path}",
        }

    # For apps we don't have an API definition for, provide generic information
    return {
        "basic_properties": basic_properties,
        "generic_notes": [
            "AppleScript follows a natural language syntax with some specific patterns:",
            "- To get properties: 'property of object'",
            "- To find objects: 'objects whose property is value'",
            "- To create objects: 'make new class at location with properties {prop1:value1, prop2:value2}'",
            "- To modify objects: 'set property of object to value'",
            "- To delete objects: 'delete object'",
        ],
        "generic_examples": [
            "# Get application properties",
            "properties",
            "# Get windows",
            "name of windows",
            "# Count objects",
            "count of windows",
        ],
        "query_examples": [
            "# Get basic app properties",
            "name",
            "version",
            "# Get all windows",
            "windows",
        ],
        "date_formats": date_format_info,
        "note": "No API definition found for this application. Using generic information.",
    }


def register_app_resources(app_name: str):
    """
    Register resource access tools for an application.
    This creates functions like app_get_resource_name() that directly access common resources.
    """
    if app_name not in active_apps:
        debug_print(f"Skipping resource registration for inactive app: {app_name}")
        return

    debug_print(f"Registering resource access tools for {app_name}")

    # Get information about the app's resources
    resources = list_app_resources(app_name)

    # Register collection access functions
    if "collections" in resources:
        for collection in resources["collections"]:
            # Sanitize collection name for function name (replace spaces with underscores)
            sanitized_collection = collection.replace(" ", "_")

            # Create function name: calendar_get_calendars, contacts_get_people, etc.
            func_name = (
                f"{app_name.lower().replace(' ', '_')}_get_{sanitized_collection}"
            )

            # Skip if function already exists
            if func_name in globals():
                continue

            # Create function code
            func_def = f"def {func_name}():"
            body = [
                f'    """Get all {collection} from {app_name}"""',
                "    try:",
                f'        return get_app_resource("{app_name}", "{collection}")',
                "    except Exception as e:",
                "        return f'Error: {str(e)}'",
            ]

            func_code = "\n".join([func_def] + body)

            # Create the function
            debug_print(f"Creating resource access function:\n{func_code}")
            exec_globals = globals().copy()
            exec(func_code, exec_globals)

            # Get the function and register it as a tool
            func = exec_globals[func_name]
            mcp.tool()(func)
            globals()[func_name] = func

            # Also create a function to get names of the collection
            name_func_name = (
                f"{app_name.lower().replace(' ', '_')}_get_{sanitized_collection}_names"
            )
            name_func_def = f"def {name_func_name}():"
            name_body = [
                f'    """Get names of all {collection} from {app_name}"""',
                "    try:",
                f'        return get_app_resource("{app_name}", "name of {collection}")',
                "    except Exception as e:",
                "        return f'Error: {str(e)}'",
            ]

            name_func_code = "\n".join([name_func_def] + name_body)

            # Create the name function
            debug_print(f"Creating resource name function:\n{name_func_code}")
            name_exec_globals = globals().copy()
            exec(name_func_code, name_exec_globals)

            # Get the function and register it as a tool
            name_func = name_exec_globals[name_func_name]
            mcp.tool()(name_func)
            globals()[name_func_name] = name_func

    # Register property access functions for basic properties
    if "basic_properties" in resources:
        for prop in resources["basic_properties"]:
            # Create function name: calendar_get_name, contacts_get_version, etc.
            func_name = f"{app_name.lower().replace(' ', '_')}_get_{prop}"

            # Skip if function already exists
            if func_name in globals():
                continue

            # Create function code
            func_def = f"def {func_name}():"
            body = [
                f'    """Get {prop} of {app_name}"""',
                "    try:",
                f'        return get_app_resource("{app_name}", "{prop}")',
                "    except Exception as e:",
                "        return f'Error: {str(e)}'",
            ]

            func_code = "\n".join([func_def] + body)

            # Create the function
            debug_print(f"Creating property function:\n{func_code}")
            exec_globals = globals().copy()
            exec(func_code, exec_globals)

            # Get the function and register it as a tool
            func = exec_globals[func_name]
            mcp.tool()(func)
            globals()[func_name] = func


if __name__ == "__main__":
    # Initialize the server once
    initialize_server()

    # Check if we're running in command-line mode
    if len(sys.argv) > 1 and sys.argv[1] == "mcp":
        debug_print("Running in command-line mode...")
        debug_print(f"Registered apps: {list(registered_apps.keys())}")
        debug_print(f"Active apps: {list(active_apps)}")

        # Read commands from stdin
        while True:
            try:
                # Read a line from stdin
                line = sys.stdin.readline()
                if not line:
                    break

                # Parse the command
                command = line.strip()
                if not command:
                    continue

                # Remove the "mcp " prefix if present
                if command.startswith("mcp "):
                    command = command[4:]

                # Execute the command
                try:
                    result = eval(command)
                    print(f"result:{result}")
                except Exception as e:
                    print(f"error:{str(e)}")

            except Exception as e:
                print(f"error:{str(e)}")
                break
    else:
        # Run as a regular MCP server
        mcp.run(transport="stdio")
