# MCP Tool Manager

A web-based tool for managing MCP (Model Control Protocol) tools in the macmcp server. This tool allows you to activate and deactivate specific AppleScript applications, helping to manage the number of tools available to Claude and prevent context window overflow.

## Features

- View active and inactive AppleScript applications
- Activate/deactivate individual applications
- Activate/deactivate all applications at once
- Persistent configuration storage
- Modern, responsive web interface

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Create the templates directory if it doesn't exist:
```bash
mkdir -p templates
```

3. Start the tool manager:
```bash
python tool_manager.py
```

4. Open your web browser and navigate to:
```
http://localhost:5000
```

## Usage

1. The web interface shows two columns:
   - Active Applications: Currently enabled applications
   - Inactive Applications: Currently disabled applications

2. For each application, you can:
   - Click "Activate" to enable the application's tools
   - Click "Deactivate" to disable the application's tools

3. Use the "Activate All" and "Deactivate All" buttons to manage all applications at once

4. Your configuration is automatically saved to `applescript_apis/tool_config.json`

## How it Works

- The tool manager uses Flask to provide a web interface
- It communicates with the macmcp server through command-line calls
- Configuration is stored in JSON format and persists between sessions
- The interface is built with Tailwind CSS for a modern look and feel

## Notes

- Changes take effect immediately
- The configuration file is created automatically when you first use the tool
- By default, all applications are active when first installed
