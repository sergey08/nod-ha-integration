"""Select components belonging to the configured Nod repository."""
ROLES = {"Server": "nod_native_preflight", "Browser": "nod_browser_preflight", "Workspace": "nod_workspace_preflight"}

def inventory(apps, prefix):
    by_slug = {app["slug"]: app for app in apps}
    return {role: by_slug.get(f"{prefix}_{name}") for role, name in ROLES.items()}
