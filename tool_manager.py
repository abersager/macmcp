from flask import Flask, render_template, jsonify, request
import json
import os
import sys

app = Flask(__name__)

# Configuration file path
CONFIG_FILE = "applescript_apis/tool_config.json"


def debug_print(message):
    """Print debug messages to stderr"""
    sys.stderr.write(str(message) + "\n")
    sys.stderr.flush()


def load_config():
    """Load tool configuration from file"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                return set(config.get("active_apps", []))
        return set()
    except Exception as e:
        debug_print(f"Error loading config: {e}")
        return set()


def save_config(active_apps):
    """Save tool configuration to file"""
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump({"active_apps": list(active_apps)}, f, indent=2)
        debug_print("Configuration saved")
    except Exception as e:
        debug_print(f"Error saving config: {e}")


def get_all_apps():
    """Get list of all available applications from JSON files"""
    apps = set()
    try:
        for api_file in os.listdir("applescript_apis"):
            if api_file.endswith(".json"):
                with open(os.path.join("applescript_apis", api_file), "r") as f:
                    api_data = json.load(f)
                    if "applicationName" in api_data:
                        apps.add(api_data["applicationName"])
    except Exception as e:
        debug_print(f"Error getting apps: {e}")
    return sorted(list(apps))


@app.route("/")
def index():
    """Render the main page"""
    return render_template("index.html")


@app.route("/api/active-apps")
def get_active_apps():
    """Get list of active applications"""
    debug_print("Fetching active apps...")
    active_apps = load_config()
    debug_print(f"Active apps: {active_apps}")
    return jsonify(sorted(list(active_apps)))


@app.route("/api/inactive-apps")
def get_inactive_apps():
    """Get list of inactive applications"""
    debug_print("Fetching inactive apps...")
    active_apps = load_config()
    all_apps = set(get_all_apps())
    inactive_apps = all_apps - active_apps
    debug_print(f"Inactive apps: {inactive_apps}")
    return jsonify(sorted(list(inactive_apps)))


@app.route("/api/activate/<app_name>")
def activate_app(app_name):
    """Activate an application"""
    debug_print(f"Activating app: {app_name}")
    active_apps = load_config()
    active_apps.add(app_name)
    save_config(active_apps)
    return jsonify({"result": f"Activated {app_name}"})


@app.route("/api/deactivate/<app_name>")
def deactivate_app(app_name):
    """Deactivate an application"""
    debug_print(f"Deactivating app: {app_name}")
    active_apps = load_config()
    active_apps.discard(app_name)
    save_config(active_apps)
    return jsonify({"result": f"Deactivated {app_name}"})


@app.route("/api/activate-all")
def activate_all():
    """Activate all applications"""
    debug_print("Activating all apps...")
    all_apps = set(get_all_apps())
    save_config(all_apps)
    return jsonify({"result": "Activated all applications"})


@app.route("/api/deactivate-all")
def deactivate_all():
    """Deactivate all applications"""
    debug_print("Deactivating all apps...")
    save_config(set())
    return jsonify({"result": "Deactivated all applications"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
