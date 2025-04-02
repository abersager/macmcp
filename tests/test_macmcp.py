import pytest
import json
import os
import sys
from unittest.mock import patch, MagicMock, mock_open

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import macmcp.macmcp
from macmcp.macmcp import (
    FastMCP,
    load_config,
    save_config,
    run_applescript_command,
    register_app_commands,
    initialize_server,
    get_active_apps,
    get_inactive_apps,
    activate_app,
    deactivate_app,
    activate_all_apps,
    deactivate_all_apps,
    list_applescript_apps,
    list_app_commands,
    get_command_info,
    CONFIG_FILE,
)

# Test data
SAMPLE_API_DATA = {
    "applicationName": "TestApp",
    "commands": [
        {
            "name": "test-command",
            "description": "Test command description",
            "parameters": [
                {
                    "name": "param1",
                    "description": "First parameter",
                    "required": True,
                },
                {
                    "name": "param2",
                    "description": "Second parameter",
                    "required": False,
                    "default": "default_value",
                },
            ],
        }
    ],
}


@pytest.fixture
def mock_mcp():
    """Create a mock MCP server"""
    with patch("macmcp.macmcp.FastMCP") as mock:
        mcp_instance = MagicMock()
        # Mock the internal tools dictionary
        mcp_instance.tools = {}

        # Mock the tool decorator behavior
        def mock_tool_decorator():
            def decorator(func):
                mcp_instance.tools[func.__name__] = func
                return func

            return decorator

        mcp_instance.tool = mock_tool_decorator
        # We don't mock active_apps here as the functions modify the global one
        mock.return_value = mcp_instance
        yield mcp_instance


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global state before each test"""
    original_registered_apps = macmcp.macmcp.registered_apps.copy()
    original_active_apps = macmcp.macmcp.active_apps.copy()
    original_globals = globals().copy()

    yield

    macmcp.macmcp.registered_apps = original_registered_apps
    macmcp.macmcp.active_apps = original_active_apps
    # Clean up functions added to globals by tests
    for key in list(globals().keys()):
        if key not in original_globals:
            del globals()[key]


@pytest.fixture
def mock_config_file(tmp_path):
    """Create a temporary config file"""
    config_file = tmp_path / "tool_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    return config_file


@pytest.fixture
def mock_applescript_apis(tmp_path):
    """Create a temporary applescript_apis directory with test data"""
    apis_dir = tmp_path / "applescript_apis"
    apis_dir.mkdir(parents=True)

    # Create test API file
    api_file = apis_dir / "TestApp.json"
    with open(api_file, "w") as f:
        json.dump(SAMPLE_API_DATA, f)

    return apis_dir


def test_load_config_empty(mock_config_file):
    """Test loading config when file doesn't exist"""
    with patch("macmcp.macmcp.CONFIG_FILE", str(mock_config_file)):
        config = load_config()
        assert isinstance(config, set)
        assert len(config) == 0


def test_load_config_with_data(mock_config_file):
    """Test loading config with existing data"""
    config_data = {"active_apps": ["TestApp1", "TestApp2"]}
    with open(mock_config_file, "w") as f:
        json.dump(config_data, f)

    with patch("macmcp.macmcp.CONFIG_FILE", str(mock_config_file)):
        config = load_config()
        assert config == {"TestApp1", "TestApp2"}


def test_save_config(mock_config_file):
    """Test saving config to file"""
    config_data = {"TestApp1", "TestApp2"}
    with patch("macmcp.macmcp.CONFIG_FILE", str(mock_config_file)):
        save_config(config_data)
        assert mock_config_file.exists()

        with open(mock_config_file) as f:
            saved_data = json.load(f)
            assert set(saved_data["active_apps"]) == config_data


@patch("subprocess.run")
def test_run_applescript_command(mock_run):
    """Test running an AppleScript command"""
    mock_run.return_value = MagicMock(returncode=0, stdout="Command result", stderr="")

    result = run_applescript_command("TestApp", "test-command", {"param1": "value1"})
    assert result == "Command result"

    # Verify subprocess.run was called with correct arguments
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "osascript"
    assert args[1] == "-e"
    assert 'tell application "TestApp"' in args[2]
    assert "test-command" in args[2]
    assert "param1" in args[2]


@patch("subprocess.run")
def test_run_applescript_command_error(mock_run):
    """Test running an AppleScript command with error"""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error message")

    result = run_applescript_command("TestApp", "test-command", {})
    assert result == "Error: Error message"


def test_register_app_commands(mock_mcp, mock_applescript_apis):
    """Test registering commands for an application"""
    # Ensure the global active_apps is patched
    with patch("macmcp.macmcp.active_apps", {"TestApp"}):
        # Patch the mcp instance used within the function
        with patch("macmcp.macmcp.mcp", mock_mcp):
            register_app_commands("TestApp", SAMPLE_API_DATA)
            # Check if the tool was added to the *mock* instance's tools dict
            assert "testapp_test_command" in mock_mcp.tools
            # Check global registered_apps state
            assert "TestApp" in macmcp.macmcp.registered_apps
            assert "test-command" in macmcp.macmcp.registered_apps["TestApp"]


def test_register_app_commands_inactive(mock_mcp, mock_applescript_apis):
    """Test that commands are not registered for inactive apps"""
    with patch("macmcp.macmcp.active_apps", set()):  # Empty active apps
        with patch("macmcp.macmcp.mcp", mock_mcp):
            register_app_commands("TestApp", SAMPLE_API_DATA)
            assert "testapp_test_command" not in mock_mcp.tools
            # App name might be added to registered_apps even if inactive initially
            # assert "TestApp" not in macmcp.macmcp.registered_apps


def test_initialize_server(mock_mcp, mock_applescript_apis, mock_config_file):
    """Test server initialization"""
    # The actual API file name expected by the patched listdir
    api_filename = "test_app_api.json"
    api_file = mock_applescript_apis / api_filename
    api_file.write_text(json.dumps(SAMPLE_API_DATA))

    config_data = {"active_apps": ["TestApp"]}
    mock_config_file.write_text(json.dumps(config_data))

    # Mock os functions within the macmcp.macmcp module's scope
    # to redirect file loading to the temp directory.
    with patch("macmcp.macmcp.CONFIG_FILE", str(mock_config_file)):
        # Patch listdir to return our dummy filename when called with 'applescript_apis'
        with patch(
            "macmcp.macmcp.os.listdir", return_value=[api_filename]
        ) as mock_listdir:
            # Patch os.path.join to return the full path to the dummy file
            with patch(
                "macmcp.macmcp.os.path.join", return_value=str(api_file)
            ) as mock_join:
                # Patch the MCP instance
                with patch("macmcp.macmcp.mcp", mock_mcp):
                    initialize_server()
                    # Assert listdir was called with the hardcoded path
                    mock_listdir.assert_called_with("applescript_apis")
                    # Assert join was called correctly
                    mock_join.assert_called_with("applescript_apis", api_filename)
                    # Check if the command from the active app was registered
                    assert "testapp_test_command" in mock_mcp.tools
                    assert "TestApp" in macmcp.macmcp.registered_apps
                    assert "TestApp" in macmcp.macmcp.active_apps


def test_get_active_apps(mock_mcp):
    """Test getting active applications"""
    with patch("macmcp.macmcp.active_apps", {"TestApp1", "TestApp2"}):
        result = get_active_apps()
        assert result == ["TestApp1", "TestApp2"]


def test_get_inactive_apps(mock_mcp):
    """Test getting inactive applications"""
    with patch(
        "macmcp.macmcp.registered_apps",
        {"TestApp1": [], "TestApp2": [], "TestApp3": []},
    ):
        with patch("macmcp.macmcp.active_apps", {"TestApp1"}):
            result = get_inactive_apps()
            assert result == ["TestApp2", "TestApp3"]


def test_activate_app(mock_mcp):
    """Test activating an application"""
    app_name = "TestApp"
    # Setup initial state: App registered but inactive
    macmcp.macmcp.registered_apps = {app_name: ["test-command"]}
    macmcp.macmcp.active_apps = set()

    # Mock the API data loading within activate_app
    with patch("macmcp.macmcp.os.listdir", return_value=["test_app_api.json"]):
        with patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_API_DATA))):
            # Patch the mcp instance used within the function
            with patch("macmcp.macmcp.mcp", mock_mcp):
                with patch("macmcp.macmcp.save_config") as mock_save:
                    result = activate_app(app_name)
                    assert result == f"Activated {app_name}"
                    # Check that the app is now in the *global* active_apps set
                    assert app_name in macmcp.macmcp.active_apps
                    # Check that the command was re-registered on the mock
                    assert "testapp_test_command" in mock_mcp.tools
                    mock_save.assert_called_once_with(macmcp.macmcp.active_apps)


def test_activate_app_not_found(mock_mcp):
    """Test activating an application that isn't registered"""
    macmcp.macmcp.registered_apps = {}
    macmcp.macmcp.active_apps = set()
    with patch("macmcp.macmcp.mcp", mock_mcp):
        result = activate_app("NotFoundApp")
        assert "not found" in result
        assert "NotFoundApp" not in macmcp.macmcp.active_apps


def test_deactivate_app(mock_mcp):
    """Test deactivating an application"""
    app_name = "TestApp"
    # Setup initial state: App registered and active
    macmcp.macmcp.registered_apps = {app_name: ["test-command"]}
    macmcp.macmcp.active_apps = {app_name}
    # Add the command to the mock MCP instance's tools
    mock_mcp.tools = {"testapp_test_command": MagicMock()}

    # Patch the mcp instance used within the function
    with patch("macmcp.macmcp.mcp", mock_mcp):
        with patch("macmcp.macmcp.save_config") as mock_save:
            result = deactivate_app(app_name)
            assert result == f"Deactivated {app_name}"
            # Check it was removed from the global active set
            assert app_name not in macmcp.macmcp.active_apps
            # Check it was removed from the mock MCP's tools
            assert "testapp_test_command" not in mock_mcp.tools
            mock_save.assert_called_once_with(macmcp.macmcp.active_apps)


def test_list_app_commands(mock_mcp):
    """Test listing commands for an application"""
    with patch("macmcp.macmcp.registered_apps", {"TestApp": ["command1", "command2"]}):
        result = list_app_commands("TestApp")
        assert result == ["command1", "command2"]


def test_get_command_info(mock_mcp):
    """Test getting command information"""

    def mock_function():
        """Test command description"""
        pass

    mock_mcp.tools = {"testapp_test_command": mock_function}
    with patch("macmcp.macmcp.registered_apps", {"TestApp": ["test-command"]}):
        result = get_command_info("TestApp", "test-command")
        assert result["app_name"] == "TestApp"
        assert result["command_name"] == "test-command"
        assert result["description"] == "Test command description"
        assert result["function_name"] == "testapp_test_command"
