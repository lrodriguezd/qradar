# Scripts para Gestión de Montaje NFS en QRadar

Este repositorio contiene scripts de Bash para configurar y gestionar el montaje de sistemas de archivos NFS en QRadar . Los scripts realizan varias tareas, incluida la comprobación de la conectividad al servidor NFS, la configuración del montaje NFS y la eliminación de entradas duplicadas en el archivo `/etc/fstab`.

## Contenido

1. [Configuración](#configuración)
2. [Uso](#uso)
3. [Requisitos](#requisitos)
4. [Notas Importantes](#notas-importantes)
5. [Licencia](#licencia)

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
