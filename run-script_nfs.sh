#!/bin/bash

# Ruta al archivo /etc/hosts
hosts_file="/etc/hosts"

# Nombre del script que deseas ejecutar en los servidores remotos
remote_script="script_nfs.sh"

# Leer el archivo /etc/hosts y ejecutar el script en servidores adecuados
while IFS= read -r line; do
    # Obtener la dirección IP y el nombre del servidor desde la línea
    ip_address=$(echo "$line" | awk '{print $1}')
    server_name=$(echo "$line" | awk '{print $2}')

    # Verificar si la línea no contiene localhost ni direcciones IPv6
#   if [[ ! "$ip_address" =~ ^localhost|::1|fe80:|0.0.0.0 ]]; then
    if [[ "$ip_address" != "::"* && "$ip_address" != "127.0.0.1" && "$ip_address" != "0.0.0.0" && ! -z "$server_name" ]]; then

        echo "Ejecutando $remote_script en $server_name ($ip_address)..."

        # Utiliza SSH para ejecutar el script en el servidor remoto
        ssh -o StrictHostKeyChecking=no "$server_name" "bash -s" < "$remote_script"

        echo "Script ejecutado en $server_name."
        echo ""
    fi
done < "$hosts_file"
