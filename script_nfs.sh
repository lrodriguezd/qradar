#!/bin/bash
# Creado por Luis Rodriguez
#Version 15 Fri Sep 15 16:52:51 CST 2023
# Definicion del servidor NFS a agregar
nfs_server="192.168.1.1"
nfs_port="2049"
export_path="/nfs"
fstab="/etc/fstab"
hafstab="/opt/qradar/ha/fstab.back"
mount_point="/store/backup"
options="rw,soft,intr,noac 0 0"
store_local="/store/backup.local"
export TERM=xterm



# Función para mostrar el avance
mostrar_avance() {
    local duration=5  # Duración total en segundos
    local start_time=$(date +%s)

    while true; do
        local current_time=$(date +%s)
        local elapsed_time=$((current_time - start_time))

        if [ $elapsed_time -ge $duration ]; then
            break
        fi

        local progress=$((elapsed_time * 100 / duration))
        local bars=$((progress / 2))  # Ancho de la barra de progreso
        local spaces=$((50 - bars))   # Espacios restantes

        # Construir la barra de progreso animada
        local progress_bar="["
        for ((i = 0; i < bars; i++)); do
            progress_bar+="="
        done
        for ((i = 0; i < spaces; i++)); do
            progress_bar+=" "
        done
        progress_bar+="]"

        # Imprimir la barra de progreso y el porcentaje
        printf "\r%s %d%%" "$progress_bar" "$progress"

        # Esperar un breve momento antes de la próxima actualización
        sleep 0.1
    done
    # Limpiar la línea de salida después de la animación
    printf "\r%*s\r" "$(tput cols)" ""
}

# Funcion para verificar la conectividad al servidor NFS
check_nfs_connectivity() {
    # Verificar la conectividad al servidor NFS en el puerto 2049
    echo "Verificar la conexion hacia el servidor $nfs_server en el puerto $nfs_port..."
    mostrar_avance
    echo -e '\a'
    nc -z -w 5 $nfs_server $nfs_port
    if [ $? -eq 0 ]; then
        echo -e '\a'
        echo "Conexión exitosa a $nfs_server en el puerto $nfs_port..."
        echo -e '\a'
        else
            echo -e '\a'
            echo "Error: No se pudo conectar a $nfs_server en el puerto $nfs_port..."
            echo -e '\a'
            exit 1
    fi
}
# Funcion para configurar el montaje NFS
configure_nfs_mount() {
    echo -e '\a'
    echo "Habilitar e iniciar los servicios NFS"
    mostrar_avance
    echo -e '\a'
    systemctl enable rpcbind
    mostrar_avance
    systemctl start rpcbind
    echo -e '\a'
    systemctl status rpcbind
    echo -e '\a'
     # Modo Cluster, continuar
        if [ -e "$hafstab" ]; then
            echo -e '\a'
            echo "Modo cluster detectado, modificando $hafstab y $fstab..."
            mostrar_avance
            echo -e '\a'
            limpiar_hafstab
            echo -e '\a'
            echo "Creando respaldo de $fstab y $hafstab..."
            mostrar_avance
            cp $fstab /root/fstab-$(date +%F_%R)
            cp $hafstab /root/hafstab-$(date +%F_%R)
            echo "Respaldo de $fstab y $hafstab guardado en /root..."
            mostrar_avance
            echo "$nfs_server:$export_path $mount_point nfs $options" >> "$hafstab"
            echo -e '\a'
            echo "Modificacion de $hafstab completado..."
            echo -e '\a'
            echo "#HA $nfs_server:$export_path $mount_point nfs $options" >> "$fstab"
            echo -e '\a'
            echo "Modificacion de $hafstab y $fstab completado..."
            echo -e '\a'
        else
            # Modo Standalone, continuar
            echo -e '\a'
            echo "Modo standalone detectado, modificando $fstab..."
            mostrar_avance
            echo -e '\a'
            clean_fstab
            echo -e '\a'
            echo "Creando respaldo de $fstab..."
            mostrar_avance
            cp $fstab /root/fstab-$(date +%F_%R)
            echo "Respaldo de $fstab y $hafstab guardado en /root..."
            mostrar_avance
            echo "$nfs_server:$export_path $mount_point nfs $options" >> "$fstab"
            echo -e '\a'
            echo "Modificacion de $fstab completado..."
        fi

    # Mover los archivos de respaldo existentes al store local
    echo -e '\a'
    echo "Creando $store_local..."
    mostrar_avance
    echo -e '\a'
    mkdir $store_local
    echo -e '\a'
    echo "Moviendo respaldos existentes ..."
    mostrar_avance
    mv -f $mount_point/* $store_local
    echo -e '\a'
    echo "El contenido de backup fue movido de $mount_point hacia $store_local..."
    echo -e '\a'

    # Crear un nuevo directorio de respaldo
    echo "Creando $mount_point..."
    mostrar_avance
    echo -e '\a'
    mkdir $mount_point
    echo -e '\a'

    # Establecer permisos en el volumen NFS
    echo "Estableciendo permisos $mount_point..."
    mostrar_avance
    chown nobody:nobody $mount_point
    echo -e '\a'

    # Montar el volumen NFS
    echo "Realizando el montaje de volumen $nfs_server:$export_path $mount_point completado..."
    mostrar_avance
    mount -t nfs -o nfsvers=4 $nfs_server:$export_path $mount_point
    echo -e '\a'
    echo "Montaje de volumen $nfs_server:$export_path $mount_point completado..."
    mostrar_avance
    echo -e '\a'

    # Verificar si se montó correctamente
    df -h | grep "$nfs_server:$export_path"
    if [ $? -eq 0 ]; then
        echo -e '\a'
        echo "Montaje $nfs_server:$export_path exitoso..."
        echo -e '\a'
    else
        echo -e '\a'
        echo "Error: No se pudo montar el volumen NFS..."
        echo -e '\a'
        exit 1
    fi

    echo -e '\a'
    echo "Configuración y montaje NFS completados con éxito..."
    echo -e '\a'
}
# Funcion Verificar si la entrada ya existe en /etc/fstab
clean_fstab(){
    if grep -q "^$nfs_server:$export_path $mount_point" $fstab; then
        echo "La entrada en $fstab ya existe..."
        mostrar_avance
        echo -e '\a'
        echo "Desmontar $mount_point en caso que este utilizado..."
        mostrar_avance
        umount $mount_point
        echo -e '\a'
        echo "Creando respaldo de $fstab ..."
        mostrar_avance
        cp $fstab /root/fstab-$(date +%F_%R)
        echo "Respaldo de $fstab guardado en /root..."
        mostrar_avance
        echo "Elimine manualmente entradas duplicadas en $fstab..."
        grep $nfs_server $fstab
        else
        echo -e '\a'
        echo "El archivo $fstab esta preparado..."
        echo -e '\a'
    fi
}
# Funcion Verificar si la entrada ya existe en /opt/qradar/ha/fstab.back
limpiar_hafstab(){
    if grep -q "^$nfs_server:$export_path $mount_point" $hafstab; then
        echo "La entrada en $hafstab ya existe.  Eliminando la entrada existente..."
        mostrar_avance
        echo -e '\a'
        echo "Desmontar $mount_point si esta utilizada..."
        mostrar_avance
        umount $mount_point
        echo -e '\a'
        echo "Creando respaldo de $fstab y $hafstab..."
        mostrar_avance
        cp $fstab /root/fstab-$(date +%F_%R)
        cp $hafstab /root/hafstab-$(date +%F_%R)
        echo "Respaldo de $fstab y $hafstab guardado en /root..."
        mostrar_avance
        echo "Elimine manualmente entradas duplicadas en $hafstab..."
        grep $nfs_server $hafstab
        else
        echo -e '\a'
        echo "El archivo $hafstab esta preparado..."
        echo -e '\a'
    fi
}

# Main Script
# Verificar la conectividad al servidor NFS
check_nfs_connectivity
# Configurar el montaje NFS
configure_nfs_mount
exit 0
