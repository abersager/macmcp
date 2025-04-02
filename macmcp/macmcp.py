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
    app_name: str, command: str, parameters: Optional[Dict[str, Any]] = None
) -> Any:
    """Run an AppleScript command and return the result"""
    try:
        script_parts = [f'tell application "{app_name}"']

        if parameters and len(parameters) > 0:
            param_str = ""
            for key, value in parameters.items():
                if key == "self":  # Skip 'self' parameter if it exists
                    continue

                # Handle the case where we added an underscore to a reserved keyword
                orig_key = key
                if key.endswith("_") and key[:-1] in keyword.kwlist:
                    orig_key = key[:-1]

                if isinstance(value, bool):
                    value_str = "true" if value else "false"
                elif isinstance(value, str):
                    value_str = f'"{value}"'
                elif isinstance(value, dict):
                    # Handle record type parameters
                    record_parts = []
                    for k, v in value.items():
                        if isinstance(v, bool):
                            v_str = "true" if v else "false"
                        elif isinstance(v, str):
                            v_str = f'"{v}"'
                        else:
                            v_str = str(v)
                        record_parts.append(f"{k}:{v_str}")
                    value_str = "{{" + ", ".join(record_parts) + "}}"
                else:
                    value_str = str(value)

                param_str += f" with {orig_key} {value_str}"

            script_parts.append(f"{command}{param_str}")
        else:
            script_parts.append(command)

        script_parts.append("end tell")

        full_script = "\n".join(script_parts)

        # For debugging
        debug_print(f"Executing AppleScript:\n{full_script}")

        result = subprocess.run(
            ["osascript", "-e", full_script], capture_output=True, text=True
        )

        if result.returncode != 0:
            debug_print(f"AppleScript error: {result.stderr}")
            return f"Error: {result.stderr}"

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
    registered_apps[app_name] = []

    for cmd in api_data.get("commands", []):
        try:
            command_name = cmd["name"]
            registered_apps[app_name].append(command_name)

            # Create a unique function name by prefixing with app name
            func_name = f"{app_name.lower().replace(' ', '_')}_{command_name.lower().replace(' ', '_').replace('-', '_')}"

            # Build parameter definitions
            params = []
            for param in cmd.get("parameters", []):
                param_name = param["name"]
                # Handle Python reserved keywords
                if param_name in keyword.kwlist:
                    param_name = f"_{param_name}"

                if param.get("required", True):
                    params.append(param_name)
                else:
                    default_value = param.get("default", None)
                    if default_value is None:
                        default_value = "None"
                    elif isinstance(default_value, str):
                        default_value = f"'{default_value}'"
                    params.append(f"{param_name}={default_value}")

            # Create the function definition
            func_def = f"def {func_name}({', '.join(params)}):"

            # Build the function body
            body = []
            body.append(
                '    """'
                + cmd.get("description", "Execute AppleScript command")
                + '"""'
            )
            body.append("    try:")
            body.append("        return run_applescript_command(")
            body.append(f"            '{app_name}',")
            body.append(f"            '{command_name}',")
            body.append("            locals()")
            body.append("        )")
            body.append("    except Exception as e:")
            body.append("        return f'Error: {str(e)}'")

            # Create the function
            func_code = "\n".join([func_def] + body)
            debug_print(f"Creating function:\n{func_code}")

            # Add the function to the global namespace
            exec(func_code, globals())

            # Register the function as an MCP tool
            func = globals()[func_name]
            mcp.tool()(func)

        except Exception as e:
            debug_print(f"Error registering command {command_name} for {app_name}: {e}")
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

    debug_print("MCP Server initialization complete.")
    active_count = len(active_apps)
    registered_count = sum(len(cmds) for cmds in registered_apps.values())
    debug_print(
        f"Successfully registered {active_count} applications with AppleScript commands"
    )
    debug_print(f"Total command count: {registered_count}")
    debug_print(f"Active applications: {active_count}")
    debug_print("Use list_applescript_apps() to discover available applications")


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
