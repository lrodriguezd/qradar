#!/bin/bash

## Funcionalidades
#El script realiza las siguientes verificaciones:
#
#1. **Resolución DNS**: Verifica que la IP del dominio de una consola coincida con una IP esperada.
#2. **Conectividad a Internet**: Realiza un ping a `ibm.com` para validar conectividad.
#3. **Obtención de IP pública**: Verifica la IP pública usando OpenDNS y `curl`.
#4. **Verificación de IP interna**: Obtiene y muestra la IP interna del sistema.
#5. **Espacio en disco**: Verifica el espacio disponible en el directorio `/store`.
#6. **Servicio OpenVPN**: Comprueba si el servicio `openvpn@client` está corriendo y revisa su estado.
#7. **Permisos de escritura en `/store`**: Verifica que el directorio `/store` tenga permisos de escritura.
#8. **Tiempo de actividad**: Muestra el tiempo que el sistema ha estado activo.
#9. **Interfaces y rutas de red**: Muestra las interfaces y rutas configuradas.
#10. **Versión de QRadar**: Verifica la versión instalada de QRadar.
#11. **Conectividad**: Comprueba la conectividad a través de `telnet`, `netcat` y `tcptraceroute`.
#12. **Certificados SSL**: Verifica los certificados SSL de los servicios.

## Requisitos Previos
#Antes de usar este script, asegúrate de cumplir con los siguientes requisitos:
##- **Ejecutar como root** o usando `sudo`.
#- **Herramientas instaladas**: El script utiliza las siguientes herramientas:
#  - `dig`
#  - `curl`
#  - `telnet`
#  - `netcat`
#  - `tcptraceroute`
#  - `openssl`

#rodiaz@mx1.ibm.com
#Fri Sep 27 12:54:16 CST 2024


- **Acceso a Internet** para probar la conectividad a servicios externos (por ejemplo, OpenDNS y `ibm.com`).
- **Configuración correcta de red y DNS** en el servidor.

# Verificar que el script esté siendo ejecutado como root
if [ "$EUID" -ne 0 ]; then
    echo "Este script debe ser ejecutado como root"
    exit 1
fi

# IPs para realizar pruebas a Consola y VPN
#Escribe la ip de la consola
IP1=0.0.0.0
#Escribe la ip del VPN
IP2=0.0.0.0
#Escribe la url de la consola
URL=console-000000.qradar.ibmcloud.com

# Archivo de salida con hostname y fecha de ejecución
HOSTNAME=$(hostname)
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
OUTPUT_FILE="${HOSTNAME}_${DATE}_Verificar_results.txt"

# Función para obtener la fecha y hora en formato RFC 5424
timestamp() {
    date +"%Y-%m-%dT%H:%M:%S%:z"
}

# Función para registrar tanto en pantalla como en el archivo
log() {
    echo -e "$(timestamp) | $1" | tee -a $OUTPUT_FILE
}

separator="============================================================"
log "$separator"
log "Inicio de las pruebas de conectividad y validaciones del sistema"
log "$separator"

# Verificación de la IP del dominio de la consola
log "Validando que la IP del dominio $URL coincida con la IP esperada..."
DOMAIN_IP=$(dig +short "$URL" | tail -n 1)

if [ "$DOMAIN_IP" == "$IP1" ]; then
    log "✅ La IP del dominio $URL ($DOMAIN_IP) coincide con la IP esperada ($IP1)."
else
    log "❌ Fallo: La IP del dominio $URL ($DOMAIN_IP) no coincide con la IP esperada ($IP1). Agregando en /etc/hosts."
    echo "$IP1  $URL" >> /etc/hosts
    log "✅ Se agregó $IP1  $URL en /etc/hosts."
fi

log "$separator"

# Verificación de conectividad a Internet (ping a ibm.com)
log "Comprobando conectividad a ibm.com mediante ping..."
ping -c 4 ibm.com > /dev/null 2>&1
if [ $? -eq 0 ]; then
    log "✅ Ping a ibm.com exitoso."
else
    log "❌ Fallo: No se pudo alcanzar ibm.com."
fi

log "$separator"

# Verificación de IP pública usando OpenDNS
log "Obteniendo la IP pública usando OpenDNS..."
PUBLIC_IP=$(dig +short myip.opendns.com @resolver1.opendns.com)

if [ -z "$PUBLIC_IP" ]; then
    log "❌ Fallo: No se pudo obtener la IP pública. Verifique la conectividad a Internet."
else
    log "✅ IP pública obtenida: $PUBLIC_IP"
fi

log "$separator"

# Verificación de IP pública con curl
log "Obteniendo la IP pública usando curl..."
PUBLIC_IP_CURL=$(curl -s -k https://ifconfig.me)

if [ -z "$PUBLIC_IP_CURL" ]; then
    log "❌ Fallo: No se pudo obtener la IP pública usando curl. Verifique la conectividad a Internet."
else
    log "✅ IP pública obtenida con curl: $PUBLIC_IP_CURL"
fi

log "$separator"

# Verificación de IP interna del host
log "Obteniendo la IP interna del host..."
HOST_IP=$(hostname -I)

if [ -z "$HOST_IP" ]; then
    log "❌ Fallo: No se pudo obtener la IP interna. Posible problema de conectividad o falta de configuración."
else
    log "✅ IP interna obtenida: $HOST_IP"
fi

log "$separator"

# Verificación de espacio en disco en /store (umbral del 90%)
log "Verificando espacio en disco en /store..."
DISK_USAGE=$(df -Th /store | awk 'NR==2 {print $6}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 90 ]; then
    log "✅ Espacio en disco suficiente: Uso actual $DISK_USAGE%."
else
    log "❌ Fallo: Espacio en disco insuficiente. Uso actual $DISK_USAGE%."
fi

log "$separator"

# Verificación de si el proceso openvpn@client está en ejecución
log "Comprobando si el servicio openvpn@client está corriendo..."
ps aux | grep -v grep | grep openvpn@client > /dev/null
if [ $? -eq 0 ]; then
    log "✅ El servicio openvpn@client está corriendo."
else
    log "❌ Fallo: El servicio openvpn@client NO está corriendo."
fi

log "$separator"

# Verificación de estado del servicio OpenVPN
log "Revisando el estado del servicio OpenVPN..."
systemctl status openvpn@client | tee -a $OUTPUT_FILE

log "$separator"

# Verificación de permisos de escritura en /store
log "Comprobando permisos de escritura en /store..."
if [ -w /store ]; then
    log "✅ Permiso de escritura en /store correcto."
else
    log "❌ Fallo: No se puede escribir en /store."
fi

log "$separator"

# Verificación del tiempo de actividad del sistema
log "Obteniendo el tiempo de actividad del sistema..."
UPTIME=$(uptime -p)
log "✅ El sistema ha estado activo por: $UPTIME."

log "$separator"

# Verificación de interfaces de red
log "Listando las interfaces de red disponibles..."
ip a | tee -a $OUTPUT_FILE

log "$separator"

# Verificación de rutas de red
log "Listando las rutas de red configuradas..."
route -n | tee -a $OUTPUT_FILE

log "$separator"

# Verificación de la versión de QRadar
log "Obteniendo la versión de QRadar..."
/opt/qradar/bin/myver -v | tee -a $OUTPUT_FILE

log "$separator"

# Verificación de conectividad con Telnet a las IPs de QRadar y VPN
log "Probando conectividad con Telnet a $IP1 (consola QRadar)..."
timeout 5 telnet $IP1 443 | tee -a $OUTPUT_FILE

log "Probando conectividad con Telnet a $IP2 (VPN)..."
timeout 5 telnet $IP2 443 | tee -a $OUTPUT_FILE

log "$separator"

# Verificación de conectividad con nc
log "Verificando conectividad con netcat (nc) a $URL..."
nc -zv $URL 443 | tee -a $OUTPUT_FILE

log "Verificando conectividad con netcat (nc) a $IP1..."
nc -zv $IP1 443 | tee -a $OUTPUT_FILE

log "Verificando conectividad con netcat (nc) a $IP2..."
nc -zv $IP2 443 | tee -a $OUTPUT_FILE

log "$separator"

# Verificación de tcptraceroute
log "Verificando conectividad con tcptraceroute a $IP1..."
tcptraceroute $IP1 443 | tee -a $OUTPUT_FILE

log "Verificando conectividad con tcptraceroute a $IP2..."
tcptraceroute $IP2 443 | tee -a $OUTPUT_FILE

log "$separator"

# Verificación de certificados con OpenSSL
log "Verificando certificados SSL en $URL..."
openssl s_client -connect $URL:443 -showcerts | tee -a $OUTPUT_FILE

log "Verificando certificados SSL en $URL con SNI..."
openssl s_client -connect $URL:443 -servername $URL -showcerts | tee -a $OUTPUT_FILE

log "$separator"

# Verificación de errores en los logs de OpenVPN
log "Revisando conexiones reiniciadas en los logs de OpenVPN..."
cat /var/log/openvpn.log | grep -i 'Connection reset' | wc -l | tee -a $OUTPUT_FILE

log "$separator"
log "Pruebas finalizadas. Resultados guardados en $OUTPUT_FILE."
log "$separator"
