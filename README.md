# Nod for Home Assistant

Experimental integration for an existing Nod installation on Home Assistant OS. Add Nod in Devices & services to see the installed versions and open the existing server panel. Requires the native server app. Browser and Workspace are optional.

### Coordinated update

In the Nod integration's options, select **Update Nod**. Review the three installed and target versions and confirm. The first supported upgrade is Server dev.34 and both workers dev.6 to Server dev.35 and both workers dev.7 (Nod 0.10.3). The Nod catalog supplies the approved migrations through its upstream manifest on GitHub. Supervisor must offer the exact target for each of the three adopted apps. When a future release adds a validated transition, the integration can offer it with the same update button.

Supervisor stops the apps and creates a local partial backup before changing any version. The integration verifies that the local backup contains all three installed versions and uses the Home Assistant backup password if local protection is configured. It updates and starts the workers before Server and restores the previous running states. On an interruption after a version change, reopen **Update Nod** to review the current versions and resume with the original backup. The result shows the backup ID. To revert, restore those three apps from that backup in Supervisor. Keep the local backup private.

## Español

Integración experimental para una instalación existente de Nod en Home Assistant OS. Añade Nod en Dispositivos y servicios para consultar las versiones y abrir el panel del servidor existente. Requiere la aplicación del servidor nativo. Browser y Workspace son opcionales.

### Actualización coordinada

En las opciones de la integración Nod, elige **Actualizar Nod**, revisa las tres versiones instaladas y de destino y confirma. La primera migración compatible va de Server dev.34 y los dos workers dev.6 a Server dev.35 y los dos workers dev.7 (Nod 0.10.3). El catálogo de Nod publica en GitHub las migraciones verificadas en el manifiesto upstream. Supervisor debe ofrecer la versión de destino exacta para cada una de las tres aplicaciones adoptadas. Cuando una versión futura incorpore una transición validada, la integración podrá ofrecerla con el mismo botón.

Supervisor detiene las aplicaciones y hace una copia parcial local antes de cambiar ninguna versión. La integración verifica que la copia local contiene las tres versiones instaladas y usa la contraseña de copias de Home Assistant si la protección local está configurada. Actualiza y arranca los workers antes que Server y recupera sus estados de ejecución anteriores. Si se interrumpe tras un cambio de versión, vuelve a **Actualizar Nod** para revisar las versiones y reanudar con la copia original. El resultado muestra el ID de la copia. Para volver atrás, restaura esas tres aplicaciones desde esa copia en Supervisor. Mantén en privado la copia local.
