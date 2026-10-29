# Informations sur le serveur et le PC qui l'heberge, pour la page
# ADMINISTRATION (system_page.py) : adresses reseau, temps en ligne,
# processeur, memoire, disque, temperature.
#
# Temperature : Windows ne l'expose pas de facon standard. Sources essayees
# dans l'ordre : psutil (Linux/Mac), LibreHardwareMonitor / OpenHardwareMonitor
# (outils gratuits qui publient les capteurs une fois lances), puis le capteur
# ACPI de Windows (souvent absent ou reserve aux droits administrateur). La
# lecture (PowerShell, ~1 s) se fait hors de la boucle de l'interface et est
# mise en cache TEMPERATURE_CACHE_SECONDS.

import platform
import socket
import subprocess
import sys
import time
from datetime import datetime

import psutil

#heure de demarrage du serveur (module importe au lancement par main.py)
START_TIME = time.time()
TEMPERATURE_CACHE_SECONDS = 30.0

#premiere mesure "a vide" : psutil.cpu_percent(None) renvoie la charge depuis
#l'appel precedent
psutil.cpu_percent(interval=None)

_temperature: dict = {"value": None, "source": "", "checked_at": 0.0}

_TEMPERATURE_SCRIPT = r"""
$inv = [cultureinfo]::InvariantCulture
foreach ($n in @('root/LibreHardwareMonitor', 'root/OpenHardwareMonitor')) {
    try {
        $s = Get-CimInstance -Namespace $n -ClassName Sensor -ErrorAction Stop |
             Where-Object { $_.SensorType -eq 'Temperature' }
        if ($s) {
            $cpu = $s | Where-Object { $_.Name -like '*CPU*' -or $_.Name -like '*Package*' }
            if (-not $cpu) { $cpu = $s }
            $m = ($cpu | Measure-Object -Property Value -Maximum).Maximum
            Write-Output ($m.ToString($inv) + '|' + $n)
            exit
        }
    } catch {}
}
try {
    $t = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop |
         Select-Object -First 1
    Write-Output ((($t.CurrentTemperature / 10) - 273.15).ToString($inv) + '|ACPI Windows')
} catch { Write-Output 'none|' }
"""


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{days} j {text}" if days else text


def format_bytes(value: float) -> str:
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if value < 1024 or unit == "To":
            return f"{value:.1f} {unit}" if unit != "o" else f"{int(value)} o"
        value /= 1024
    return f"{value:.1f} To"


#adresse IPv4 utilisee pour sortir sur le reseau (aucun paquet n'est envoye :
#connect() en UDP choisit seulement l'interface)
def primary_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return probe.getsockname()[0]
    except OSError:
        addresses = local_ipv4s()
        return addresses[0][1] if addresses else "127.0.0.1"


#adresses IPv4 du PC [(interface, adresse)], hors boucle locale et APIPA
def local_ipv4s() -> list[tuple[str, str]]:
    result = []
    for interface, addresses in psutil.net_if_addrs().items():
        for address in addresses:
            if address.family == socket.AF_INET and not address.address.startswith(("127.", "169.254.")):
                result.append((interface, address.address))
    return result


def cpu_name() -> str:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def _read_temperature() -> tuple[float | None, str]:
    reader = getattr(psutil, "sensors_temperatures", None)
    if reader:
        try:
            sensors = reader()
            values = [entry.current for entries in sensors.values() for entry in entries if entry.current]
            if values:
                return max(values), "psutil"
        except (OSError, AttributeError):
            pass
    if sys.platform != "win32":
        return None, ""
    try:
        output = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _TEMPERATURE_SCRIPT],
            capture_output=True, text=True, timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip().splitlines()
        value, source = (output[-1] if output else "none|").split("|", 1)
        return (float(value), source) if value != "none" else (None, "")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None, ""


#temperature en cache : (valeur en degres C ou None, source) ; a appeler via
#run.io_bound (lecture potentiellement lente)
def refresh_temperature(force: bool = False) -> tuple[float | None, str]:
    if force or time.time() - _temperature["checked_at"] > TEMPERATURE_CACHE_SECONDS:
        _temperature["value"], _temperature["source"] = _read_temperature()
        _temperature["checked_at"] = time.time()
    return _temperature["value"], _temperature["source"]


def cached_temperature() -> tuple[float | None, str]:
    return _temperature["value"], _temperature["source"]


#mesures instantanees (rapides) du PC et du processus serveur
def snapshot(data_dir) -> dict:
    memory = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage(str(data_dir))
    except OSError:
        disk = None
    frequency = psutil.cpu_freq()
    process = psutil.Process()
    return {
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu_name": cpu_name(),
        "cpu_cores": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_freq_mhz": round(frequency.current) if frequency else None,
        "ram_total": memory.total,
        "ram_used": memory.total - memory.available,
        "ram_percent": memory.percent,
        "disk_total": disk.total if disk else None,
        "disk_used": disk.used if disk else None,
        "disk_percent": disk.percent if disk else None,
        "pc_uptime": time.time() - psutil.boot_time(),
        "server_uptime": time.time() - START_TIME,
        "server_started": datetime.fromtimestamp(START_TIME),
        "process_memory": process.memory_info().rss,
        "python": platform.python_version(),
    }
