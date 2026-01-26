#!/usr/bin/env python3
"""
Script de mantenimiento completo para OpenVAS
Automatiza todas las tareas de mantenimiento: servicios, feeds, limpieza, optimización
"""

import subprocess
import json
import os
import shutil
import glob
import smtplib
import argparse
import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from gvm.connections import UnixSocketConnection
from gvm.protocols.gmp import Gmp
import xml.etree.ElementTree as ET

class MaintenanceReport:
    """Clase para generar reportes de mantenimiento"""
    def __init__(self):
        self.report = {
            'timestamp': datetime.datetime.now().isoformat(),
            'services': {},
            'feeds': {},
            'cleanup': {},
            'disk_space': {},
            'database': {},
            'certificates': {},
            'errors': [],
            'warnings': [],
            'summary': {}
        }
    
    def add_service_status(self, service, status, message=""):
        self.report['services'][service] = {'status': status, 'message': message}
    
    def add_feed_update(self, feed_type, status, message=""):
        self.report['feeds'][feed_type] = {'status': status, 'message': message}
    
    def add_cleanup(self, item_type, count, size_freed=0):
        if item_type not in self.report['cleanup']:
            self.report['cleanup'][item_type] = {'count': 0, 'size_freed_mb': 0}
        self.report['cleanup'][item_type]['count'] += count
        self.report['cleanup'][item_type]['size_freed_mb'] += size_freed
    
    def add_error(self, error):
        self.report['errors'].append(error)
    
    def add_warning(self, warning):
        self.report['warnings'].append(warning)
    
    def save(self, filepath):
        """Guarda el reporte en formato JSON"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(self.report, f, indent=2)
    
    def get_summary_text(self):
        """Genera un resumen en texto del reporte"""
        lines = []
        lines.append("=" * 60)
        lines.append("REPORTE DE MANTENIMIENTO OPENVAS")
        lines.append("=" * 60)
        lines.append(f"Fecha: {self.report['timestamp']}")
        lines.append("")
        
        # Servicios
        lines.append("SERVICIOS:")
        for service, info in self.report['services'].items():
            status_icon = "✓" if info['status'] == 'ok' else "✗"
            lines.append(f"  {status_icon} {service}: {info['status']}")
            if info['message']:
                lines.append(f"    {info['message']}")
        lines.append("")
        
        # Feeds
        lines.append("ACTUALIZACIÓN DE FEEDS:")
        for feed, info in self.report['feeds'].items():
            status_icon = "✓" if info['status'] == 'ok' else "✗"
            lines.append(f"  {status_icon} {feed}: {info['status']}")
        lines.append("")
        
        # Limpieza
        lines.append("LIMPIEZA:")
        total_freed = 0
        for item_type, info in self.report['cleanup'].items():
            lines.append(f"  {item_type}: {info['count']} elementos, {info['size_freed_mb']:.2f} MB liberados")
            total_freed += info['size_freed_mb']
        lines.append(f"  Total liberado: {total_freed:.2f} MB")
        lines.append("")
        
        # Errores y advertencias
        if self.report['errors']:
            lines.append("ERRORES:")
            for error in self.report['errors']:
                lines.append(f"  ✗ {error}")
            lines.append("")
        
        if self.report['warnings']:
            lines.append("ADVERTENCIAS:")
            for warning in self.report['warnings']:
                lines.append(f"  ⚠ {warning}")
            lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)


def leer_configuracion(config_path='/home/redteam/gvm/Config/config.json'):
    """Lee la configuración desde el archivo JSON"""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo de configuración: {config_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error al decodificar JSON: {e}")
        return None


def verificar_servicio(service_name, report):
    """Verifica el estado de un servicio systemd"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        is_active = result.stdout.strip() == 'active'
        
        if is_active:
            report.add_service_status(service_name, 'ok', 'Servicio activo')
            return True
        else:
            report.add_service_status(service_name, 'failed', f'Servicio no activo: {result.stdout.strip()}')
            report.add_error(f"Servicio {service_name} no está activo")
            return False
    except subprocess.TimeoutExpired:
        report.add_service_status(service_name, 'timeout', 'Timeout al verificar servicio')
        report.add_warning(f"Timeout al verificar servicio {service_name}")
        return False
    except Exception as e:
        report.add_service_status(service_name, 'error', str(e))
        report.add_error(f"Error al verificar servicio {service_name}: {e}")
        return False


def reiniciar_servicio(service_name, report, dry_run=False):
    """Reinicia un servicio si está fallando"""
    if dry_run:
        print(f"[DRY-RUN] Reiniciaría servicio: {service_name}")
        return True
    
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'restart', service_name],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            report.add_service_status(service_name, 'restarted', 'Servicio reiniciado exitosamente')
            return True
        else:
            report.add_error(f"Error al reiniciar {service_name}: {result.stderr}")
            return False
    except Exception as e:
        report.add_error(f"Excepción al reiniciar {service_name}: {e}")
        return False


def verificar_servicios(config, report, restart_failed=False, dry_run=False):
    """Verifica todos los servicios críticos de OpenVAS"""
    print("\n[1/7] Verificando servicios del sistema...")
    
    servicios_criticos = ['gvmd', 'ospd-openvas', 'gsad', 'notus-scanner']
    servicios_soporte = ['postgresql', 'redis-server@openvas', 'mosquitto']
    
    todos_servicios = servicios_criticos + servicios_soporte
    
    servicios_fallidos = []
    for servicio in todos_servicios:
        if not verificar_servicio(servicio, report):
            servicios_fallidos.append(servicio)
    
    # Reiniciar servicios fallidos si está configurado
    if restart_failed and servicios_fallidos and not dry_run:
        print(f"Reiniciando servicios fallidos: {', '.join(servicios_fallidos)}")
        for servicio in servicios_fallidos:
            reiniciar_servicio(servicio, report, dry_run)
    
    print(f"Servicios verificados: {len(todos_servicios)}, Fallidos: {len(servicios_fallidos)}")


def actualizar_feeds(config, report, dry_run=False):
    """Actualiza los feeds de vulnerabilidades de OpenVAS"""
    print("\n[2/7] Actualizando feeds de vulnerabilidades...")
    
    feeds = [
        ('NVT', 'greenbone-nvt-sync'),
        ('GVMD_DATA', 'greenbone-feed-sync --type GVMD_DATA'),
        ('SCAP', 'greenbone-feed-sync --type SCAP'),
        ('CERT', 'greenbone-feed-sync --type CERT')
    ]
    
    for feed_type, command in feeds:
        if dry_run:
            print(f"[DRY-RUN] Ejecutaría: sudo -u gvm {command}")
            report.add_feed_update(feed_type, 'simulated', 'Simulado en dry-run')
            continue
        
        try:
            cmd_parts = command.split()
            result = subprocess.run(
                ['sudo', '-u', 'gvm'] + cmd_parts,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hora máximo
            )
            
            if result.returncode == 0:
                report.add_feed_update(feed_type, 'ok', 'Actualización completada')
                print(f"  ✓ {feed_type} actualizado")
            else:
                report.add_feed_update(feed_type, 'error', result.stderr[:200])
                report.add_warning(f"Error al actualizar feed {feed_type}")
                print(f"  ✗ {feed_type} error: {result.stderr[:100]}")
        except subprocess.TimeoutExpired:
            report.add_feed_update(feed_type, 'timeout', 'Timeout en actualización')
            report.add_warning(f"Timeout al actualizar feed {feed_type}")
        except Exception as e:
            report.add_feed_update(feed_type, 'error', str(e))
            report.add_error(f"Excepción al actualizar {feed_type}: {e}")


def limpiar_reportes_antiguos(config, report, dry_run=False):
    """Limpia reportes antiguos de OpenVAS"""
    print("\n[3/7] Limpiando reportes antiguos...")
    
    retention_days = config.get('maintenance', {}).get('report_retention_days', 90)
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=retention_days)
    
    try:
        path = '/run/gvmd/gvmd.sock'
        connection = UnixSocketConnection(path=path)
        
        with Gmp(connection=connection) as gmp:
            user = config.get('user', 'admin')
            password = config.get('password', 'admin')
            gmp.authenticate(user, password)
            
            # Obtener todos los reportes
            response = gmp.get_reports(filter_string='rows=-1')
            root = ET.fromstring(response)
            reports = root.findall(".//report")
            
            deleted_count = 0
            for report_elem in reports:
                report_id = report_elem.get('id')
                timestamp_elem = report_elem.find('.//timestamp')
                
                if timestamp_elem is not None:
                    timestamp_str = timestamp_elem.text
                    try:
                        # Formato: 2024-01-15T10:30:00Z
                        report_date = datetime.datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        if report_date < cutoff_date:
                            if not dry_run:
                                gmp.delete_report(report_id)
                            deleted_count += 1
                    except (ValueError, AttributeError):
                        # Si no se puede parsear la fecha, saltar
                        continue
            
            report.add_cleanup('reports', deleted_count)
            print(f"  Reportes eliminados: {deleted_count}")
            
    except Exception as e:
        report.add_error(f"Error al limpiar reportes: {e}")
        print(f"  Error: {e}")


def limpiar_archivos_temporales(config, report, dry_run=False):
    """Limpia archivos CSV y logs temporales"""
    print("\n[4/7] Limpiando archivos temporales...")
    
    # Limpiar CSVs en Reports/exports
    csv_dir = '/home/redteam/gvm/Reports/exports/'
    csv_count = 0
    csv_size = 0
    
    if os.path.exists(csv_dir):
        csv_files = glob.glob(os.path.join(csv_dir, '*.csv'))
        for csv_file in csv_files:
            try:
                size = os.path.getsize(csv_file)
                if not dry_run:
                    os.remove(csv_file)
                csv_count += 1
                csv_size += size
            except Exception as e:
                report.add_warning(f"Error al eliminar {csv_file}: {e}")
    
    report.add_cleanup('csv_files', csv_count, csv_size / (1024 * 1024))
    
    # Limpiar logs antiguos
    log_retention_days = config.get('maintenance', {}).get('log_retention_days', 30)
    log_cutoff = datetime.datetime.now() - datetime.timedelta(days=log_retention_days)
    
    log_dirs = [
        '/var/log/gvm/',
        '/home/redteam/gvm/'
    ]
    
    log_count = 0
    log_size = 0
    
    for log_dir in log_dirs:
        if os.path.exists(log_dir):
            for log_file in glob.glob(os.path.join(log_dir, '*.log')):
                try:
                    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(log_file))
                    if mtime < log_cutoff:
                        size = os.path.getsize(log_file)
                        if not dry_run:
                            os.remove(log_file)
                        log_count += 1
                        log_size += size
                except Exception as e:
                    report.add_warning(f"Error al eliminar log {log_file}: {e}")
    
    report.add_cleanup('log_files', log_count, log_size / (1024 * 1024))
    
    # Limpiar archivos temporales específicos
    temp_files = [
        '/home/redteam/gvm/tasksend.txt',
        '/home/redteam/gvm/taskslog.txt',
        '/home/redteam/gvm/logbalbix.txt'
    ]
    
    temp_count = 0
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            try:
                if not dry_run:
                    os.remove(temp_file)
                temp_count += 1
            except Exception as e:
                report.add_warning(f"Error al eliminar {temp_file}: {e}")
    
    report.add_cleanup('temp_files', temp_count)
    print(f"  Archivos CSV eliminados: {csv_count}")
    print(f"  Archivos log eliminados: {log_count}")
    print(f"  Archivos temporales eliminados: {temp_count}")


def verificar_espacio_disco(config, report):
    """Verifica el espacio disponible en disco"""
    print("\n[5/7] Verificando espacio en disco...")
    
    min_space_gb = config.get('maintenance', {}).get('min_disk_space_gb', 10)
    
    try:
        result = subprocess.run(
            ['df', '-h', '/'],
            capture_output=True,
            text=True
        )
        
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            parts = lines[1].split()
            if len(parts) >= 4:
                # parts[3] es el espacio disponible
                available = parts[3]
                # Convertir a GB
                if 'G' in available:
                    available_gb = float(available.replace('G', ''))
                elif 'M' in available:
                    available_gb = float(available.replace('M', '')) / 1024
                else:
                    available_gb = 0
                
                report.report['disk_space'] = {
                    'available_gb': available_gb,
                    'min_required_gb': min_space_gb,
                    'status': 'ok' if available_gb >= min_space_gb else 'warning'
                }
                
                if available_gb < min_space_gb:
                    report.add_warning(f"Espacio en disco bajo: {available_gb:.2f} GB disponible (mínimo: {min_space_gb} GB)")
                else:
                    print(f"  Espacio disponible: {available_gb:.2f} GB")
    except Exception as e:
        report.add_error(f"Error al verificar espacio en disco: {e}")


def optimizar_base_datos(config, report, dry_run=False):
    """Optimiza la base de datos PostgreSQL"""
    print("\n[6/7] Optimizando base de datos PostgreSQL...")
    
    if dry_run:
        print("[DRY-RUN] Ejecutaría VACUUM FULL, ANALYZE y REINDEX en base de datos gvmd")
        report.report['database'] = {'status': 'simulated'}
        return
    
    try:
        # Obtener tamaño de la base de datos antes
        result_before = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-c', 
             "SELECT pg_size_pretty(pg_database_size('gvmd'));"],
            capture_output=True,
            text=True
        )
        
        size_before = result_before.stdout.strip() if result_before.returncode == 0 else "N/A"
        
        # Ejecutar VACUUM FULL (bloquea la BD pero recupera más espacio)
        result_vacuum = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-c', 'VACUUM FULL;'],
            capture_output=True,
            text=True,
            timeout=3600
        )
        
        if result_vacuum.returncode == 0:
            print("  ✓ VACUUM FULL completado")
        else:
            report.add_warning(f"VACUUM FULL completado con advertencias: {result_vacuum.stderr[:200]}")
        
        # Ejecutar ANALYZE para actualizar estadísticas del optimizador
        result_analyze = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-c', 'ANALYZE;'],
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutos máximo para ANALYZE
        )
        
        if result_analyze.returncode == 0:
            print("  ✓ ANALYZE completado")
        else:
            report.add_warning(f"ANALYZE completado con advertencias: {result_analyze.stderr[:200]}")
        
        # Ejecutar REINDEX
        result_reindex = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-c', 'REINDEX DATABASE gvmd;'],
            capture_output=True,
            text=True,
            timeout=3600
        )
        
        if result_reindex.returncode == 0:
            print("  ✓ REINDEX completado")
        else:
            report.add_warning(f"REINDEX completado con advertencias: {result_reindex.stderr[:200]}")
        
        # Obtener tamaño después
        result_after = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-c', 
             "SELECT pg_size_pretty(pg_database_size('gvmd'));"],
            capture_output=True,
            text=True
        )
        
        size_after = result_after.stdout.strip() if result_after.returncode == 0 else "N/A"
        
        report.report['database'] = {
            'status': 'ok',
            'size_before': size_before,
            'size_after': size_after
        }
        
    except subprocess.TimeoutExpired:
        report.add_error("Timeout al optimizar base de datos")
    except Exception as e:
        report.add_error(f"Error al optimizar base de datos: {e}")


def verificar_certificados(config, report):
    """Verifica la validez de los certificados SSL/TLS"""
    print("\n[7/7] Verificando certificados SSL/TLS...")
    
    cert_paths = [
        '/var/lib/gvm/CA/cacert.pem',
        '/var/lib/gvm/CA/servercert.pem'
    ]
    
    cert_status = {}
    for cert_path in cert_paths:
        if os.path.exists(cert_path):
            try:
                result = subprocess.run(
                    ['openssl', 'x509', '-in', cert_path, '-noout', '-enddate'],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    # Parsear fecha de expiración
                    expiry_line = result.stdout.strip()
                    cert_status[cert_path] = {'status': 'ok', 'expiry': expiry_line}
                else:
                    cert_status[cert_path] = {'status': 'error', 'message': result.stderr}
            except Exception as e:
                cert_status[cert_path] = {'status': 'error', 'message': str(e)}
        else:
            cert_status[cert_path] = {'status': 'not_found'}
    
    report.report['certificates'] = cert_status
    print(f"  Certificados verificados: {len(cert_paths)}")


def enviar_email_reporte(config, report):
    """Envía el reporte por email"""
    email_on_errors = config.get('maintenance', {}).get('email_on_errors', True)
    
    # Solo enviar si hay errores o está configurado para enviar siempre
    if not email_on_errors and not report.report['errors']:
        return
    
    try:
        smtp_server = config.get('mailserver')
        smtp_user = config.get('smtp_user')
        smtp_pass = config.get('smtp_pass')
        smtp_port = 587
        from_address = config.get('from')
        to_address = config.get('to')
        site = config.get('site', '')
        pais = config.get('pais', '')
        
        subject = f'[{pais}-{site}] Reporte de Mantenimiento OpenVAS'
        
        summary_text = report.get_summary_text()
        message_html = f'''<html>
        <head></head>
        <body>
        <pre>{summary_text}</pre>
        </body>
        </html>
        '''
        
        msg = MIMEMultipart()
        msg['From'] = from_address
        msg['To'] = to_address
        msg['Subject'] = subject
        msg.attach(MIMEText(message_html, 'html'))
        
        smtp = smtplib.SMTP(smtp_server, smtp_port)
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(smtp_user, smtp_pass)
        smtp.sendmail(from_address, to_address, msg.as_string())
        smtp.quit()
        
        print("\nReporte enviado por email exitosamente")
    except Exception as e:
        print(f"\nError al enviar email: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Script de mantenimiento completo para OpenVAS'
    )
    parser.add_argument(
        '--config',
        default='/home/redteam/gvm/Config/config.json',
        help='Ruta al archivo de configuración'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simular ejecución sin hacer cambios reales'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Mostrar información detallada'
    )
    parser.add_argument(
        '--no-email',
        action='store_true',
        help='No enviar email con el reporte'
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("=" * 60)
        print("MODO DRY-RUN: No se realizarán cambios reales")
        print("=" * 60)
    
    # Leer configuración
    config = leer_configuracion(args.config)
    if not config:
        print("Error: No se pudo cargar la configuración")
        return 1
    
    # Crear reporte
    report = MaintenanceReport()
    
    # Ejecutar tareas de mantenimiento
    restart_failed = config.get('maintenance', {}).get('restart_failed_services', False)
    verificar_servicios(config, report, restart_failed, args.dry_run)
    actualizar_feeds(config, report, args.dry_run)
    limpiar_reportes_antiguos(config, report, args.dry_run)
    limpiar_archivos_temporales(config, report, args.dry_run)
    verificar_espacio_disco(config, report)
    optimizar_base_datos(config, report, args.dry_run)
    verificar_certificados(config, report)
    
    # Generar resumen
    print("\n" + "=" * 60)
    print("RESUMEN DE MANTENIMIENTO")
    print("=" * 60)
    summary = report.get_summary_text()
    print(summary)
    
    # Guardar reporte
    log_dir = '/home/redteam/gvm/logs/maintenance/'
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = os.path.join(log_dir, f'maintenance_report_{timestamp}.json')
    report.save(report_file)
    print(f"\nReporte guardado en: {report_file}")
    
    # Guardar también en texto
    text_file = os.path.join(log_dir, f'maintenance_report_{timestamp}.txt')
    with open(text_file, 'w') as f:
        f.write(summary)
    
    # Enviar email si está configurado
    if not args.no_email:
        enviar_email_reporte(config, report)
    
    # Retornar código de salida basado en errores
    return 1 if report.report['errors'] else 0


if __name__ == "__main__":
    exit(main())
