"""Provision the experimental Nod apps on a supervised host."""
import logging
import secrets

from aiohasupervisor.models.addons import AddonsOptions, StoreAddRepository
from homeassistant.components.hassio.addon_manager import AddonError, AddonManager, AddonState
from homeassistant.components.hassio.handler import get_supervisor_client

from .inventory import ROLES
from .release import SOURCE

async def provision(hass, progress):
    progress['stage'] = 'Supervisor / repository'
    client = get_supervisor_client(hass)
    store = client.store
    repos = await store.repositories_list()
    if not any(r.source == SOURCE for r in repos):
        await store.add_repository(StoreAddRepository(repository=SOURCE))
        repos = await store.repositories_list()
    repo = next((r for r in repos if r.source == SOURCE), None)
    if repo is None:
        raise AddonError("Nod repository unavailable")

    managers = {role: AddonManager(hass, logging.getLogger(__name__), role,
                                  f"{repo.slug}_{suffix}") for role, suffix in ROLES.items()}
    infos = {}
    # A cancelled worker installation must not appear as an adoptable server.
    for role in ("Workspace", "Browser", "Server"):
        manager = managers[role]
        progress['stage'] = f'inspect / {role}'
        info = await manager.async_get_addon_info()
        if info.state is AddonState.NOT_INSTALLED:
            if not info.available:
                raise AddonError("Unsupported app")
            progress['stage'] = f'install / {role}'
            await manager.async_install_addon()
            info = await manager.async_get_addon_info()
        if info.state not in (AddonState.NOT_RUNNING, AddonState.RUNNING):
            raise AddonError("App installation has not completed")
        infos[role] = info
    progress["stage"] = "pairing"
    server = infos["Server"]
    options = dict(server.options)
    if not server.hostname or any(not info.hostname for info in infos.values()):
        raise AddonError("Missing internal hostname")
    worker_options = {}
    for role in ("Browser", "Workspace"):
        worker = infos[role]
        name = role.lower()
        saved = options.get(f"{name}_key")
        current = worker.options.get("remote_key")
        if saved and current and saved != current:
            raise AddonError("Incompatible existing pairing")
        key = saved or current or secrets.token_hex(32)
        options.update({f"{name}_host":worker.hostname, f"{name}_key":key})
        config = dict(worker.options)
        config.update(remote_enabled=True, remote_key=key, server_host=server.hostname)
        if role == "Workspace":
            config["command_enabled"] = True
        worker_options[role] = config
    options.update(browser_enabled=True, workspace_runtime_enabled=True)
    if "ingress_chat" in options and not options.get("https_enabled"):
        options["ingress_chat"] = True
    desired = {"Server": options, **worker_options}
    for role, config in desired.items():
        if infos[role].options != config and infos[role].state is not AddonState.NOT_RUNNING:
            raise AddonError("Cannot change an active installation")
    for role, config in desired.items():
        if infos[role].options != config:
            progress['stage'] = f'configure / {role}'
            await managers[role].async_set_addon_options(config)
    for role in ("Workspace", "Browser", "Server"):
        if infos[role].state is AddonState.NOT_RUNNING:
            progress['stage'] = f'start / {role}'
            await managers[role].async_start_addon()
        if (await managers[role].async_get_addon_info()).state is not AddonState.RUNNING:
            raise AddonError("App has not started")
    progress["stage"] = "show server in sidebar"
    await client.addons.set_addon_options(
        f"{repo.slug}_{ROLES['Server']}", AddonsOptions(ingress_panel=True)
    )
    return repo.slug
