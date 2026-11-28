# Nod for Home Assistant

Release 1.0.0 of the Home Assistant integration works with Nod upstream 0.10.3. The verified app set is Server `0.1.0-dev.35`, Browser `0.1.0-dev.7` and Workspace `0.1.0-dev.7`. Add Nod in **Settings → Devices & services**. The integration can install and pair the three apps on a fresh setup or adopt an existing Nod Server.

<!-- ha-marketplace:exclude-start -->
[![Open in Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=sergey08&repository=nod-ha-integration&category=integration)
<!-- ha-marketplace:exclude-end -->

### Requirements and setup

Use Home Assistant OS with Supervisor on an amd64 host. The integration declares Home Assistant 2026.9 or later as its minimum. Home Assistant Marketplace is available from 2026.11. On earlier supported versions, add this repository as a custom integration in HACS.

1. Install **Nod** from Marketplace or HACS. Restart Home Assistant if prompted.
2. Open **Settings → Devices & services → Add integration → Nod**. On a fresh installation, confirm the prompt to install and pair Server, Browser and Workspace. If Nod is already installed, select the existing server.
3. Open **Settings → Apps → Nod native preflight → Open Web UI** to access Nod via Home Assistant Ingress. Sign in to any model provider or connector you want to use from Nod.

The three apps come from the separate [app repository](https://github.com/sergey08/homeassistant-addons/tree/feat/nod-home-assistant) and currently carry Home Assistant's experimental label. Standard Ingress setup requires no additional published port.

### Start Nod automatically

In Home Assistant, go to **Settings → Apps**. Open the **Info** tab for each Nod app (Server, Browser and Workspace) and turn on **Start on boot** so all three start after a restart. An app can be running now with this switch off. If two sets are installed, enable it on the set you use regularly.

### Coordinated update

In the Nod integration's options, select **Update Nod**. Review the three installed and target versions and confirm. The first supported upgrade is Server dev.34 and both workers dev.6 to Server dev.35 and both workers dev.7 (Nod 0.10.3). The Nod catalog supplies the approved migrations through its upstream manifest on GitHub. Supervisor must offer the exact target for each of the three adopted apps. When a future release adds a validated transition, the integration can offer it with the same update button.

Supervisor stops the apps and creates a local partial backup before changing any version. The integration verifies that the local backup contains all three installed versions and uses the Home Assistant backup password if local protection is configured. It updates and starts the workers before Server and restores the previous running states. On an interruption after a version change, reopen **Update Nod** to review the current versions and resume with the original backup. The result shows the backup ID. To revert, restore those three apps from that backup in Supervisor. Keep the local backup private.

### Support and licensing

Report integration issues in the [issue tracker](https://github.com/sergey08/nod-ha-integration/issues). This independent Home Assistant integration is distributed under the [MIT License](LICENSE). [Nod upstream](https://github.com/n8n-io/nod) is a separate project by n8n and retains its [Apache 2.0 license](https://github.com/n8n-io/nod/blob/nod-v0.10.3/LICENSE).

## Español

La versión 1.0.0 de la integración de Home Assistant funciona con Nod upstream 0.10.3. Las versiones verificadas de las aplicaciones son Server `0.1.0-dev.35`, Browser `0.1.0-dev.7` y Workspace `0.1.0-dev.7`. Añade Nod en **Configuración → Dispositivos y servicios**. La integración puede instalar y emparejar las tres aplicaciones en una instalación nueva o adoptar un servidor Nod existente.

<!-- ha-marketplace:exclude-start -->
[![Abrir en Marketplace de Home Assistant](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=sergey08&repository=nod-ha-integration&category=integration)
<!-- ha-marketplace:exclude-end -->

### Requisitos e instalación

Usa Home Assistant OS con Supervisor en un equipo amd64. La integración declara Home Assistant 2026.9 como versión mínima. Marketplace está disponible a partir de Home Assistant 2026.11. En versiones compatibles anteriores, añade este repositorio como integración personalizada en HACS.

1. Instala **Nod** desde Marketplace o HACS. Reinicia Home Assistant si te lo solicita.
2. Abre **Configuración → Dispositivos y servicios → Añadir integración → Nod**. En una instalación nueva, confirma la instalación y el emparejamiento de Server, Browser y Workspace. Si Nod ya está instalado, selecciona el servidor existente.
3. Abre **Configuración → Aplicaciones → Nod native preflight → Open Web UI** para acceder mediante Ingress de Home Assistant. Inicia sesión en los proveedores de modelos o conectores que quieras usar desde Nod.

Las tres aplicaciones proceden del [repositorio de aplicaciones](https://github.com/sergey08/homeassistant-addons/tree/feat/nod-home-assistant) y llevan la etiqueta experimental de Home Assistant. La configuración normal mediante Ingress funciona sin publicar puertos adicionales.

### Iniciar Nod automáticamente

En Home Assistant, ve a **Configuración → Aplicaciones**. Abre la pestaña **Información** de cada aplicación de Nod (Server, Browser y Workspace) y activa **Iniciar en el arranque** para que las tres se inicien tras reiniciar. Una aplicación puede estar en ejecución con ese interruptor desactivado. Si tienes dos conjuntos instalados, actívalo en el que usas habitualmente.

### Actualización coordinada

En las opciones de la integración Nod, elige **Actualizar Nod**, revisa las tres versiones instaladas y de destino y confirma. La primera migración compatible va de Server dev.34 y los dos workers dev.6 a Server dev.35 y los dos workers dev.7 (Nod 0.10.3). El catálogo de Nod publica en GitHub las migraciones verificadas en el manifiesto upstream. Supervisor debe ofrecer la versión de destino exacta para cada una de las tres aplicaciones adoptadas. Cuando una versión futura incorpore una transición validada, la integración podrá ofrecerla con el mismo botón.

Supervisor detiene las aplicaciones y hace una copia parcial local antes de cambiar ninguna versión. La integración verifica que la copia local contiene las tres versiones instaladas y usa la contraseña de copias de Home Assistant si la protección local está configurada. Actualiza y arranca los workers antes que Server y recupera sus estados de ejecución anteriores. Si se interrumpe tras un cambio de versión, vuelve a **Actualizar Nod** para revisar las versiones y reanudar con la copia original. El resultado muestra el ID de la copia. Para volver atrás, restaura esas tres aplicaciones desde esa copia en Supervisor. Mantén en privado la copia local.

### Soporte y licencias

Comunica los problemas de la integración en el [registro de incidencias](https://github.com/sergey08/nod-ha-integration/issues). Esta integración independiente para Home Assistant se distribuye bajo la [licencia MIT](LICENSE). [Nod upstream](https://github.com/n8n-io/nod) es un proyecto independiente de n8n y conserva su [licencia Apache 2.0](https://github.com/n8n-io/nod/blob/nod-v0.10.3/LICENSE).
