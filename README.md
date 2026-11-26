# Nod for Home Assistant

Experimental integration for Home Assistant OS (amd64). Run the Nod agent in a Home Assistant sidebar panel, using separate Server, Browser and Workspace apps. The agent can use an existing ChatGPT sign-in through Nod's onboarding; an API key is not required for that sign-in method.

**Experimental software:** not a stable release. The app repository uses a development branch. Keep backups before updating.

## Installation

1. Install the Nod integration through HACS using this repository as a custom integration repository.
2. Restart Home Assistant, then open **Settings → Devices & services → Add integration → Nod**.
3. For a new installation, select **Install Nod**. The integration adds the experimental app repository, installs Server, Browser and Workspace, generates separate internal pairing keys, starts the apps and enables the sidebar entry.
4. Open Nod from the Home Assistant sidebar. Complete Nod's onboarding and select your preferred supported model or sign-in method.
5. For an existing installation, select the installed server instead. Its existing pairing and data are preserved.

The development app repository is [sergey08/homeassistant-addons](https://github.com/sergey08/homeassistant-addons/tree/feat/nod-home-assistant). Server, Browser and Workspace use prebuilt amd64 images on GHCR; anonymous image pulls have passed CI. A clean installation with the latest image metadata still needs real-host validation.

## Existing installations and recovery

- The integration exposes the installed component versions and a link to the server panel.
- Integration options can install or start missing workers when existing server pairing is available. Incompatible pairing is rejected rather than overwritten.
- If setup stops, check the installed apps and their logs in Supervisor before retrying. Do not remove apps or reset keys merely to retry.
- The sidebar uses authenticated Home Assistant Ingress. Separate public HTTPS access is optional and needs additional configuration.
- Automatic startup after host reboot, resource use under load and isolation between tasks still require validation. Do not treat this experimental deployment as production-ready.

## Español

Integración experimental para Home Assistant OS (amd64). Ejecuta el agente Nod en una pestaña lateral de Home Assistant con tres aplicaciones separadas: Server, Browser y Workspace. El alta de Nod admite el inicio de sesión con ChatGPT, sin necesidad de una clave API para ese método.

**Software experimental:** no es una versión estable. El repositorio de aplicaciones utiliza una rama de desarrollo. Conserva copias de seguridad antes de actualizar.

### Instalación

1. Instala la integración Nod mediante HACS, añadiendo este repositorio como repositorio personalizado de tipo integración.
2. Reinicia Home Assistant y entra en **Ajustes → Dispositivos y servicios → Añadir integración → Nod**.
3. En una instalación nueva, selecciona **Instalar Nod**. La integración añade el repositorio experimental, instala Server, Browser y Workspace, genera claves internas de emparejamiento independientes, arranca las aplicaciones y habilita la entrada lateral.
4. Abre Nod desde el menú lateral de Home Assistant. Completa el asistente inicial y selecciona el modelo o método de acceso compatible que prefieras.
5. Si Nod ya está instalado, selecciona el servidor existente. Se conservan su emparejamiento y sus datos.

El repositorio de aplicaciones es [sergey08/homeassistant-addons](https://github.com/sergey08/homeassistant-addons/tree/feat/nod-home-assistant). Server, Browser y Workspace utilizan imágenes amd64 precompiladas en GHCR; las descargas anónimas han superado CI. Falta validar una instalación limpia en un equipo real con los últimos metadatos de distribución.

### Instalaciones existentes y recuperación

- La integración muestra las versiones instaladas y un enlace al panel del servidor.
- Las opciones de la integración permiten instalar o arrancar componentes auxiliares si el servidor dispone del emparejamiento necesario. Se rechazan emparejamientos incompatibles en lugar de sobrescribirlos.
- Si la instalación se interrumpe, revisa las aplicaciones instaladas y sus registros en Supervisor antes de reintentar. No borres las aplicaciones ni restablezcas claves solo para repetir la instalación.
- El panel lateral utiliza Ingress autenticado de Home Assistant. El acceso HTTPS público independiente es opcional y requiere configuración adicional.
- Queda pendiente validar el arranque automático tras reiniciar el equipo, el consumo bajo carga y el aislamiento entre tareas. No consideres esta instalación experimental lista para producción.
