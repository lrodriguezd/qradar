# Scripts para Gestión de Montaje NFS en QRadar

Este repositorio contiene ejemplos de scripts y herramientas que los administradores tengan una referencia con uso educativo. Estas muestras se proporcionan "tal cual" y no tienen garantías de ningún tipo.
Alentamos a los administradores a examinar estos scripts antes de ejecutarlos o probar estas herramientas en un entorno de laboratorio antes de utilizarlas en producción.
Cualquier problema descubierto utilizando estos ejemplos no debe dirigirse al soporte de QRadar.
Los scripts realizan varias tareas, incluida la comprobación de la conectividad al servidor NFS, la configuración del montaje NFS.
Los procedimientos estan basados en las instrucciones provistas en la documentacion oficial disponible en los siguientes sitios web
[https://www.ibm.com/docs/en/qsip/7.4?topic=device-moving-backups-nfs#t_offboard_nfs_console](https://www.ibm.com/docs/en/qsip/7.5?topic=device-moving-backups-nfs)

## Contenido

1. [Configuración](#configuración)
2. [Uso](#uso)
3. [
4. Requisitos](#requisitos)
5. [Notas Importantes](#notas-importantes)
6. [Licencia](#licencia)

## Configuración

Antes de utilizar los scripts, asegúrate de configurar los siguientes valores en el script correspondiente:

- `nfs_server`: La dirección IP o el nombre de host del servidor NFS.
- `export_path`: La ruta de exportación ofrecida por el servidor NFS.
- `mount_point`: El punto de montaje local para el sistema de archivos NFS.
- `options`: Las opciones de montaje NFS.
- `store_local`: La ubicación local donde se almacenan los archivos de respaldo antes de montar el sistema de archivos NFS.

## Uso

1. Ejecuta el script desde /storetmp en la consola de QRadar.
2. Sigue las indicaciones en el script para completar las tareas de montaje NFS y configuración.

## Requisitos

Asegúrate de cumplir con los siguientes requisitos antes de ejecutar los scripts:

- Acceso SSH sin contraseña configurado en los QRadar NFS.
- Permisos de ejecución en el script de Bash (`chmod +x script.sh`).

## Notas Importantes

- Estos scripts han sido diseñados para QRadar 7.5. Si tu sistema es diferente, es posible que debas realizar ajustes.
- Antes de ejecutar cualquier script, asegúrate de comprender su funcionamiento y cómo afectará a tu sistema.
- Realiza copias de seguridad de los archivos importantes antes de realizar cambios en el sistema.
- Utiliza estos scripts bajo tu propio riesgo.

## Licencia

Este proyecto se distribuye bajo la [Licencia MIT](LICENSE).

¡Esperamos que estos scripts te sean útiles para configurar y gestionar sistemas de archivos NFS en tu QRadar Platform!
