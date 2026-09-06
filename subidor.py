import sys
import os
import time
import requests
import threading
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(BASE_DIR, "LIB")
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

from ina219_lib import INA219Monitor, get_cpu_temp
from digipot_lib import X9C103S

SERVER_URL = "http://cifedegss.mooo.com:8890/lab_server/upload.php"
SUBIDA_DIR = os.path.join(BASE_DIR, "SUBIDA")
POT_CONFIG_FILE = os.path.join(BASE_DIR, "nivel_pot.txt")
nombre_carpeta = "RB0_V2"
# Variable global para comunicar el estado del DigiPot entre hilos
NIVEL_POT_ACTUAL = 1

# ==========================================
# HILO 1: MONITOREO Y REGISTRO DE INA219
# ==========================================
def hilo_ina219():
    global NIVEL_POT_ACTUAL
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [INA219] Iniciando servicio de monitoreo...")
    monitor = INA219Monitor(intervalo_minutos=2)
    
    while True:
        try:
            temp_cpu = get_cpu_temp()
            # Se pasan las variables de temperatura y potenciómetro
            monitor.registrar_lectura(nivel_pot=NIVEL_POT_ACTUAL, temp_cpu=temp_cpu)
            monitor.verificar_y_guardar()
            time.sleep(1)
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [INA219 ERROR] {e}")
            time.sleep(5)

# ==========================================
# HILO 2: COLA DE SUBIDA Y LIMPIEZA DE BUFFER
# ==========================================
def enviar_archivo_servidor(file_path, relative_dir):
    try:
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {'dir': relative_dir}
            response = requests.post(SERVER_URL, files=files, data=data, timeout=15)
        
        return response.status_code == 200
    except Exception:
        return False

def limpiar_directorios_vacios(path):
    for root, dirs, _ in os.walk(path, topdown=False):
        for d in dirs:
            folder_path = os.path.join(root, d)
            if not os.listdir(folder_path) and folder_path != SUBIDA_DIR:
                try:
                    os.rmdir(folder_path)
                except Exception:
                    pass

def hilo_subidor_archivos():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [SUBIDOR] Servicio de cola de envio activo...")
    
    while True:
        try:
            if os.path.exists(SUBIDA_DIR):
                for root, _, files in os.walk(SUBIDA_DIR):
                    for file in files:
                        if file.endswith(".txt"):
                            file_path = os.path.join(root, file)
                            
                            if os.path.getsize(file_path) == 0:
                                continue
                            
                            rel_dir_local = os.path.relpath(root, SUBIDA_DIR)
                            rel_dir_remoto = os.path.join(nombre_carpeta, rel_dir_local)
                            
                            hora_str = datetime.now().strftime('%H:%M:%S')
                            print(f"[{hora_str}] [SUBIDOR] Enviando: {file} -> {rel_dir_remoto}")
                            
                            exito = enviar_archivo_servidor(file_path, rel_dir_remoto)
                            
                            if exito:
                                print(f"[{hora_str}] [SUBIDOR] OK 200. Eliminando de buffer local: {file}")
                                os.remove(file_path)
                            else:
                                print(f"[{hora_str}] [SUBIDOR] Sin conexion/error servidor. Guardado en buffer.")
                
                limpiar_directorios_vacios(SUBIDA_DIR)
                                
            time.sleep(10)
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [SUBIDOR ERROR] {e}")
            time.sleep(10)

# ==========================================
# HILO 3: CONTROL REMOTO DE POTENCIÓMETRO
# ==========================================
def hilo_control_digipot():
    global NIVEL_POT_ACTUAL
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [DIGIPOT] Inicializando X9C103S...")
    
    pot = X9C103S()
    pot.resetear_a_cero()
    
    if not os.path.exists(POT_CONFIG_FILE):
        with open(POT_CONFIG_FILE, "w") as f:
            f.write("0\n")

    ultimo_nivel = -1

    while True:
        try:
            if os.path.exists(POT_CONFIG_FILE):
                with open(POT_CONFIG_FILE, "r") as f:
                    contenido = f.read().strip()
                
                if contenido.isdigit():
                    # Mapeo a rango válido 0 - 99
                    nivel_solicitado = int(contenido)
                    nivel_solicitado = max(0, min(99, nivel_solicitado))

                    if nivel_solicitado != ultimo_nivel:
                        hora_str = datetime.now().strftime('%H:%M:%S')
                        print(f"[{hora_str}] [DIGIPOT] Cambiando nivel de tensión a: {nivel_solicitado} / 99")
                        
                        # Cambia sin escribir en la EEPROM interna del chip
                        pot.set_nivel(nivel_solicitado, guardar_eeprom=False)
                        
                        ultimo_nivel = nivel_solicitado
                        NIVEL_POT_ACTUAL = nivel_solicitado
            
            time.sleep(1)
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [DIGIPOT ERROR] {e}")
            time.sleep(3)

# ==========================================
# ARRANQUE PRINCIPAL
# ==========================================
print("=== INICIANDO SERVICIO GENERAL SUBIDOR + INA219 + DIGIPOT ===")

t_ina = threading.Thread(target=hilo_ina219, daemon=True)
t_sub = threading.Thread(target=hilo_subidor_archivos, daemon=True)
t_pot = threading.Thread(target=hilo_control_digipot, daemon=True)

t_ina.start()
t_sub.start()
t_pot.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDeteniendo servicios...")