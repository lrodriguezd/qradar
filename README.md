# Scripts para gestión en QRadar

Colección de scripts y utilidades de **uso educativo** para administradores de IBM QRadar. Estas muestras se proporcionan **"tal cual"** y no tienen garantías de ningún tipo. Examínalos antes de ejecutarlos o pruébalos en un laboratorio antes de usarlos en producción. Cualquier problema descubierto utilizando estos ejemplos **no debe dirigirse a IBM Support**.

> **No oficial.** Este repositorio no tiene afiliación, soporte ni mantenimiento por parte de IBM Corporation.

---

## Proyectos derivados (recomendados)

Algunos scripts de este repo crecieron y se extrajeron a **proyectos independientes** con tests, CI, documentación y empaquetado adecuados. Si vas a usar uno de los siguientes, usa la versión nueva:

| Script aquí | Versión productiva | Estado |
|---|---|---|
| `qradar_expensive_rules.py` | **[qradar-rule-profiler](https://github.com/lrodriguezd/qradar-rule-profiler)** | Reescrito con pytest (86% cobertura), 4 formatos de salida (HTML/JSON/CSV/MD), CI gating, anonimización, XSS-safe |
| Auditoría de Windows / WinCollect NSA filter | **[windows-audit](https://github.com/lrodriguezd/windows-audit)** | v2.0.0 con GUIDs idioma-agnósticos, backup/rollback, PowerShell con -WhatIf |

El script `qradar_expensive_rules.py` que sigue aquí queda **archivado para referencia histórica**. Para uso real, instala el paquete:

```bash
pipx install git+https://github.com/lrodriguezd/qradar-rule-profiler.git
```

---

## Contenido del repositorio

### Scripts utilitarios (sueltos)

| Archivo | Propósito |
|---|---|
| `qradar_expensive_rules.py` | **Archivado** — usar [qradar-rule-profiler](https://github.com/lrodriguezd/qradar-rule-profiler) |
| `qradar_expensive_properties.py` | Analiza propiedades personalizadas costosas (regex CRE) |
| `script_nfs.sh` + `run-script_nfs.sh` | Configuración de NFS para QRadar |
| `verificar.sh` | Checks de salud del sistema |
| `extraer_ip_de_etc_host` | Helper para extraer IPs del `/etc/hosts` |

## Uso

1. Copia el script a `/storetmp` en la consola de QRadar.
2. Verifica los permisos: `chmod +x script.sh`.
3. Sigue las indicaciones internas de cada script.

## Requisitos

- Acceso `root` (o sudo) al sistema QRadar.
- Bash 4+ o Python 3.6+ (según el script).
- Permisos de ejecución en cada script (`chmod +x`).

## Notas importantes

- Estos scripts han sido diseñados para **QRadar 7.5**. Si tu sistema es diferente, posibles ajustes.
- Antes de ejecutar cualquier script, asegúrate de comprender su funcionamiento y cómo afectará a tu sistema.
- Realiza copias de seguridad de los archivos importantes antes de realizar cambios.
- Utiliza estos scripts bajo tu propio riesgo.

## Licencia

Este proyecto se distribuye bajo la [Licencia MIT](LICENSE).

## Proyectos relacionados del autor

- **[tls-syslog-pki](https://github.com/lrodriguezd/tls-syslog-pki)** — provisioning de Root CA + server + client certs para TLS Syslog en QRadar, con simulador end-to-end.
- **[windows-audit](https://github.com/lrodriguezd/windows-audit)** — habilita las subcategorías de auditoría avanzada de Windows requeridas por el filtro NSA de WinCollect.
- **[qradar-rule-profiler](https://github.com/lrodriguezd/qradar-rule-profiler)** — analiza el rendimiento del Custom Rule Engine y genera reportes con recomendaciones.
- **[qradar-dlc-diagnostico](https://github.com/lrodriguezd/qradar-dlc-diagnostico)** — diagnostico de sistema operativo para Disconnected Log Collector (DLC): deslinda SO, red, TLS/certificados, CRLs y configuracion, con informe HTML y evidencia por prueba.
