# Automatic OpenVAS Installation and Configuration

Este proyecto automatiza la instalación y configuración de OpenVAS, así como la gestión de tareas y objetivos. A continuación se detallan los pasos necesarios para instalar y configurar el sistema.

## Instalación

```bash
# Clonar el repositorio desde GitHub:
git clone https://github.com/cybervaca/automatic-openvas

# Renombrar la carpeta a "gvm":
mv automatic-openvas gvm

# Ingresar al directorio "gvm" y configurar el entorno virtual:
cd gvm
python3 -m venv gvm
source gvm/bin/activate

# Si no existe `python3.10-venv`, instalar según la versión:
sudo apt install python3.10-venv

# Instalar dependencias:
pip3 install -r requirements.txt

# Ingresar al directorio "install" y ejecutar los scripts de instalacion:
cd install
python3 get-versionesonline.py #para obtener las ultimas versiones
chmod +x pre-install.sh #para actualizar cmake y obtener la ruta de pkgconfig
./pre-install.sh
chmod +x install.sh
./install.sh

```
Si despues de la instalación, el servicio gsad.service da error, modificar el fichero
/etc/systemd/system/multi-user.target.wants/gsad.service
Y borrar de ExecStart:
```
-f --drop-privileges=gvm
```
Y ejecutamos:
```
sudo systemctl daemon-reload
sudo service gsad restart
```
#### Para cambiar la contraseña de gvmd:
```
gvmd --user=admin --new-password=
```
## Configuración
Si existieran tasks o targets anteriores, borrarlos.
#### Config
en la carpeta Config, copiar el fichero config_example.json a config.json.
Modificar los valores con los correspondientes de la ubicacion
#### Cron
En la carpeta Cron, dar permisos de ejecución:
```
cd Cron
chmod +x *.sh
```
Copiar actualiza_gvm y cron-update a /usr/bin

Añadir redteam a sudoers

```
sudo su
echo 'redteam ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

```
#### Configuración de Targets y Tasks
En Targets_Tasks existe una plantilla para la importación de los targets y su correspondiente task.
Una vez rellenado, obtenemos los puertos:
```
python3 get-ports.py
```

#### Script de Mantenimiento
El proyecto incluye un script de mantenimiento completo que automatiza todas las tareas de mantenimiento de OpenVAS.

**Configuración:**
En `Config/config.json`, asegúrate de tener la sección `maintenance` configurada:
```json
"maintenance": {
    "report_retention_days": 90,
    "log_retention_days": 30,
    "min_disk_space_gb": 10,
    "clean_old_targets": false,
    "restart_failed_services": false,
    "email_on_errors": true
}
```

**Ejecución manual:**
```bash
cd Maintenance
python3 maintenance.py
```

**Ejecución con opciones:**
```bash
# Modo simulación (no hace cambios reales)
python3 maintenance.py --dry-run

# Modo verbose (más detalles)
python3 maintenance.py --verbose

# Sin enviar email
python3 maintenance.py --no-email
```

**Ejecución desde cron (mensual):**
```bash
# Agregar a crontab (ejecutar el primer día de cada mes a las 2:00 AM)
0 2 1 * * /home/redteam/gvm/Cron/maintenance.sh
```

**Tareas que realiza el script:**
1. Verificación de servicios (gvmd, ospd-openvas, gsad, notus-scanner, postgresql, redis, mosquitto)
2. Actualización de feeds de vulnerabilidades (NVT, GVMD_DATA, SCAP, CERT)
3. Limpieza de reportes antiguos (configurable por días)
4. Limpieza de archivos temporales y logs antiguos
5. Verificación de espacio en disco
6. Optimización de base de datos PostgreSQL (VACUUM, REINDEX)
7. Verificación de certificados SSL/TLS
8. Generación de reporte detallado en `/home/redteam/gvm/logs/maintenance/`
9. Envío de email con resumen (opcional)

Los reportes se guardan en formato JSON y texto en `/home/redteam/gvm/logs/maintenance/`.
