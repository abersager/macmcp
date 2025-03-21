from mcp.server.fastmcp import FastMCP
import json
import os
import subprocess
import keyword
import builtins
import sys
from typing import Any, Dict, List, Optional
import time

# Create an MCP server
mcp = FastMCP("macmcp")

# Store registered commands for discovery
registered_apps = {}


# Add tools to discover available AppleScript applications and commands
@mcp.tool()
def list_applescript_apps() -> List[str]:
    """List all available applications with AppleScript commands"""
    return sorted(list(registered_apps.keys()))


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


@mcp.tool()
def run_amphetamine_command(
    command_name: str, parameters: Optional[Dict[str, Any]] = None
) -> Any:
    """Run an Amphetamine command with the specified parameters"""
    if not is_amphetamine_installed():
        return "Error: Amphetamine is not installed."

    if not is_amphetamine_running():
        try:
            # Try to start Amphetamine
            subprocess.run(
                ["open", "-a", "Amphetamine"],
                capture_output=True,
                text=True,
            )
            time.sleep(1)  # Give it a moment to start
        except Exception as e:
            return f"Error starting Amphetamine: {e}"

    return run_applescript_command("Amphetamine", command_name, parameters)


def debug_print(message):
    """Print debug messages to stderr so they don't interfere with the MCP protocol"""
    # Avoid using print(file=) as it might not be supported in all Python environments
    sys.stderr.write(str(message) + "\n")
    sys.stderr.flush()


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
                # Use builtins.open to ensure we're using the built-in open function
                with builtins.open(filepath, "r") as f:
                    api_data = json.load(f)

                app_name = api_data.get("applicationName")
                if not app_name:
                    continue

                try:
                    register_app_commands(app_name, api_data)
                except Exception as e:
                    debug_print(f"Error registering commands for {app_name}: {e}")
                    # Continue with other APIs even if one fails
                    continue
            except Exception as e:
                debug_print(f"Error loading {filepath}: {e}")


def register_app_commands(app_name: str, api_data: Dict[str, Any]):
    """Register commands from an application's API as MCP tools and resources"""
    debug_print(f"Registering commands for {app_name}")
    command_count = 0

    # Initialize command list for the app
    if app_name not in registered_apps:
        registered_apps[app_name] = []

    # Collect all errors instead of failing immediately
    errors = []

    for suite in api_data.get("suites", []):
        for command in suite.get("commands", []):
            cmd_name = command.get("name")
            cmd_code = command.get("code")
            cmd_desc = command.get("description", "")
            has_params = len(command.get("parameters", [])) > 0
            has_result = bool(command.get("result"))

            try:
                register_command(
                    app_name,
                    cmd_name,
                    cmd_code,
                    cmd_desc,
                    has_params,
                    has_result,
                    command.get("parameters", []),
                )
                command_count += 1
                registered_apps[app_name].append(cmd_name)
            except Exception as e:
                error_msg = f"Error registering command {cmd_name}: {e}"
                debug_print(error_msg)
                errors.append(error_msg)

    debug_print(f"Registered {command_count} commands for {app_name}")
    if errors:
        debug_print(
            f"Encountered {len(errors)} errors while registering commands for {app_name}"
        )


def register_command(
    app_name: str,
    cmd_name: str,
    cmd_code: str,
    cmd_desc: str,
    has_params: bool,
    has_result: bool,
    parameters: List[Dict[str, Any]],
):
    """Register a single command as an MCP tool or resource"""
    # Convert space-separated command name to snake_case
    function_name = cmd_name.lower().replace(" ", "_").replace("-", "_")

    # Avoid name conflicts by appending app_name to function_name
    function_name = f"{app_name.lower().replace(' ', '_')}_{function_name}"

    # Split parameters into required and optional
    required_params = []
    optional_params = []
    param_map = {}

    for param in parameters:
        original_name = param.get("name", "").replace(" ", "_").replace(":", "")
        param_name = original_name

        # Check if parameter name is a Python keyword
        if keyword.iskeyword(param_name) or param_name in ("self", "cls"):
            param_name = f"{param_name}_"
            param_map[param_name] = original_name

        param_type = param.get("type", "Any")
        is_optional = param.get("optional", False)

        if param_type == "record":
            param_type = "Dict[str, Any]"
        elif param_type == "boolean":
            param_type = "bool"
        elif param_type == "text":
            param_type = "str"
        elif param_type == "integer":
            param_type = "int"
        else:
            param_type = "Any"

        # Sort parameters into required and optional
        if is_optional:
            optional_params.append((param_name, param_type))
        else:
            required_params.append((param_name, param_type))

    # Build parameter definitions list - required first, optional after
    param_defs = []
    for name, type_name in required_params:
        param_defs.append(f"{name}: {type_name}")

    for name, type_name in optional_params:
        param_defs.append(f"{name}: Optional[{type_name}] = None")

    # Determine return type
    if has_result:
        return_type = "Any"
    else:
        return_type = "None"

    # Register all commands as tools instead of resources to avoid URL validation issues
    # Create tool function
    param_str = ", ".join(param_defs)

    # Generate the tool function with dynamic parameters
    # Include code to map renamed parameters back to their original names
    param_remap_code = ""
    if param_map:
        for new_name, orig_name in param_map.items():
            param_remap_code += f"\n    # Map Python keyword parameter\n    if '{new_name}' in local_vars:\n        params['{orig_name}'] = local_vars['{new_name}']\n"

    code = f"""
@mcp.tool()
def {function_name}({param_str}) -> {return_type}:
    \"\"\"
    {cmd_desc}

    AppleScript command for {app_name}: {cmd_name}
    \"\"\"
    params = {{}}
    local_vars = locals(){param_remap_code}
    for key in local_vars:
        if key != 'self' and not key.endswith('_') and local_vars[key] is not None:
            params[key] = local_vars[key]

    command = "{cmd_name}"
    return run_applescript_command("{app_name}", command, params)
"""
    try:
        # Execute the generated code to define the function
        exec(code, globals())
    except SyntaxError as e:
        debug_print(f"Syntax error in generated code for {cmd_name}: {e}")
        debug_print(f"Generated code:\n{code}")
        raise


# Check if Amphetamine is installed (not just running)
def is_amphetamine_installed():
    try:
        # Check if Amphetamine.app exists in the Applications folder
        app_paths = [
            "/Applications/Amphetamine.app",
            os.path.expanduser("~/Applications/Amphetamine.app"),
        ]
        for path in app_paths:
            if os.path.exists(path):
                debug_print(f"Found Amphetamine at {path}")
                return True

        # Try to check with AppleScript if the application exists
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "Finder" to exists application "Amphetamine"',
            ],
            capture_output=True,
            text=True,
        )
        if result.stdout.strip().lower() == "true":
            debug_print("Amphetamine is installed (found via AppleScript)")
            return True

        debug_print("Amphetamine is not installed")
        return False
    except Exception as e:
        debug_print(f"Error checking if Amphetamine is installed: {e}")
        # Default to true in case of error to allow loading the API
        return True


# Test if Amphetamine is running
def is_amphetamine_running():
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to (name of processes) contains "Amphetamine"',
            ],
            capture_output=True,
            text=True,
        )
        running = result.stdout.strip().lower() == "true"
        if running:
            debug_print("Amphetamine is running")
        else:
            debug_print("Amphetamine is not running")
        return running
    except Exception as e:
        debug_print(f"Error checking if Amphetamine is running: {e}")
        # Default to true in case of error to allow loading the API
        return True


try:
    # Load the APIs regardless of installation status
    # If Amphetamine is not installed, the commands will gracefully return error messages
    debug_print("Loading AppleScript APIs...")
    load_applescript_apis()

    # Informational check only - doesn't affect loading
    is_installed = is_amphetamine_installed()
    is_running = is_amphetamine_running()

    if is_installed:
        if is_running:
            debug_print(
                "Amphetamine is installed and running. Commands should work normally."
            )
        else:
            debug_print(
                "Amphetamine is installed but not running. Start Amphetamine for commands to work properly."
            )
    else:
        debug_print(
            "Amphetamine doesn't appear to be installed, but APIs are loaded. Commands will return errors if used."
        )
except Exception as e:
    debug_print(f"Error during initialization: {e}")
    # Continue running even if there are initialization errors
    pass

debug_print("MCP Server initialization complete.")
debug_print(
    f"Successfully registered {len(registered_apps)} applications with AppleScript commands"
)
debug_print(
    f"Total command count: {sum(len(cmds) for cmds in registered_apps.values())}"
)
debug_print("Use list_applescript_apps() to discover available applications")

# The server will continue running until manually stopped


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="stdio")
