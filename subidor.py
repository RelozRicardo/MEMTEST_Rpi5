import os
import sys
import threading
import time
from datetime import datetime
import requests

# Librerías hardware y ADC
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import board
import busio

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(BASE_DIR, "LIB")
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

from digipot_lib import X9C103S
from ina219_lib import INA219Monitor, get_cpu_temp

# --- CONFIGURACIÓN DE RUTAS Y SERVIDOR ---
SERVER_URL = "http://cifedegss.mooo.com:8890/lab_server/upload.php"
SUBIDA_DIR = os.path.join(BASE_DIR, "SUBIDA")
VCC_CONFIG_FILE = os.path.join(BASE_DIR, "nivel_VCC.txt")
nombre_carpeta = "RB0_V2"

# Variables globales para compartir estado entre hilos
NIVEL_POT_ACTUAL = 79
VCC_MEDIDO_ADS = 0.0  # Tensión real en Voltios medida por el ADS1115

# --- LÍMITES DE SEGURIDAD Y CONFIGURACIÓN VCC ---
VCC_MIN = 1.8
VCC_MAX = 3.55
POS_SEGURIDAD = 79      # Posición predeterminada (3.3V) ante fallo del ADS1115
DIGIPOT_MIN_STEP = 2    # Límite inferior seguro
DIGIPOT_MAX_STEP = 98   # Límite superior seguro
TOLERANCIA_V = 0.005     # Margen de error / Histéresis en Voltios (20 mV)
Periodo_Consumo = 5     # Cada cuanto imprime cada uno

# ==========================================
# HILO 1: MONITOREO Y REGISTRO DE INA219
# ==========================================
def hilo_ina219():
    global NIVEL_POT_ACTUAL
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [INA219] Iniciando servicio"" de monitoreo...")
    monitor = INA219Monitor(intervalo_minutos=2)

    while True:
        try:
            temp_cpu = get_cpu_temp()

            # Pasar NIVEL_POT_ACTUAL y VCC_MEDIDO_ADS a la librería
            monitor.registrar_lectura(nivel_pot=NIVEL_POT_ACTUAL,temp_cpu=temp_cpu,vcc_ads=VCC_MEDIDO_ADS,)
            monitor.verificar_y_guardar()

            time.sleep(Periodo_Consumo)
        except Exception as e:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [INA219 ERROR] {e}")
            time.sleep(5)

# ==========================================
# HILO 2: COLA DE SUBIDA Y LIMPIEZA DE BUFFER
# ==========================================
def enviar_archivo_servidor(file_path, relative_dir):
    try:
        with open(file_path, "rb") as f:
            files = {"file": f}
            data = {"dir": relative_dir}
            response = requests.post(
                SERVER_URL, files=files, data=data, timeout=15
            )

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
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] [SUBIDOR] Servicio de cola"
        " de envio activo..."
    )

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
                            rel_dir_remoto = os.path.join(
                                nombre_carpeta, rel_dir_local
                            )

                            hora_str = datetime.now().strftime("%H:%M:%S")
                            print(
                                f"\n[{hora_str}] [SUBIDOR] Enviando: {file} ->"
                                f" {rel_dir_remoto}"
                            )

                            exito = enviar_archivo_servidor(
                                file_path, rel_dir_remoto
                            )

                            if exito:
                                print(
                                    f"[{hora_str}] [SUBIDOR] OK 200. Eliminando"
                                    f" de buffer local: {file}"
                                )
                                os.remove(file_path)
                            else:
                                print(
                                    f"[{hora_str}] [SUBIDOR] Sin"
                                    " conexion/error servidor. Guardado en"
                                    " buffer."
                                )

                limpiar_directorios_vacios(SUBIDA_DIR)

            time.sleep(10)
        except Exception as e:
            print(
                f"\n[{datetime.now().strftime('%H:%M:%S')}] [SUBIDOR ERROR]"
                f" {e}"
            )
            time.sleep(10)


# ==========================================
# HILO 3: CONTROL DE FUENTE LDO POR REALIMENTACIÓN (ADS1115 + DIGIPOT)
# ==========================================
def conectar_ads(i2c):
    """Intenta inicializar la comunicación I2C con el ADS1115 en 0x48."""
    try:
        ads = ADS.ADS1115(i2c, address=0x48)
        chan = AnalogIn(ads, 0)
        return ads, chan, True
    except Exception:
        return None, None, False


def leer_consigna_vcc():
    """Lee nivel_VCC.txt.

    Satura entre 1.8V y 3.5V. Retorna 3.3V ante error.
    """
    if not os.path.exists(VCC_CONFIG_FILE):
        try:
            with open(VCC_CONFIG_FILE, "w") as f:
                f.write("3.30\n")
        except Exception:
            pass
        return 3.30

    try:
        with open(VCC_CONFIG_FILE, "r") as f:
            contenido = f.read().strip().replace(",", ".")

        if not contenido:
            return 3.30

        val = float(contenido)

        if val < VCC_MIN:
            val = VCC_MIN
        elif val > VCC_MAX:
            val = VCC_MAX

        return val
    except Exception:
        return 3.30


def hilo_control_digipot():
    global NIVEL_POT_ACTUAL, VCC_MEDIDO_ADS
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] [DIGIPOT] Inicializando"
        " X9C103S..."
    )

    pot = X9C103S()
    pot.resetear_a_cero()

    # Inicialización del bus I2C
    i2c = busio.I2C(board.SCL, board.SDA)
    ads, chan, ads_conectado = conectar_ads(i2c)

    # Establecer posición inicial de referencia
    if not ads_conectado:
        hora_str = datetime.now().strftime("%H:%M:%S")
        print(
            f"[{hora_str}] [DIGIPOT WARN] ADS1115 no detectado. Modo"
            f" seguridad en paso #{POS_SEGURIDAD} (3.3V)..."
        )
        pot.set_nivel(POS_SEGURIDAD, guardar_eeprom=False)
        NIVEL_POT_ACTUAL = POS_SEGURIDAD
    else:
        pot.set_nivel(POS_SEGURIDAD, guardar_eeprom=False)
        NIVEL_POT_ACTUAL = POS_SEGURIDAD

    ultimo_nivel = pot.posicion_actual

    while True:
        try:
            vcc_objetivo = leer_consigna_vcc()

            if not ads_conectado:
                ads, chan, ads_conectado = conectar_ads(i2c)

            if ads_conectado:
                try:
                    # Medición real (divisor 2x)
                    vcc_real = 2.0 * chan.voltage
                    VCC_MEDIDO_ADS = vcc_real

                    pos_actual = pot.posicion_actual
                    error_v = vcc_objetivo - vcc_real

                    # --- LÓGICA INVERTIDA ---
                    # error_v > 0 (V_real es menor que el objetivo) -> Bajar posición para SUBIR Vcc
                    # error_v < 0 (V_real es mayor que el objetivo) -> Subir posición para BAJAR Vcc
                    nivel_solicitado = pos_actual
                    if abs(error_v) > TOLERANCIA_V:
                        if error_v > 0 and pos_actual > DIGIPOT_MIN_STEP:
                            nivel_solicitado = pos_actual - 1
                        elif error_v < 0 and pos_actual < DIGIPOT_MAX_STEP:
                            nivel_solicitado = pos_actual + 1

                    nivel_seguro = max(
                        DIGIPOT_MIN_STEP,
                        min(DIGIPOT_MAX_STEP, nivel_solicitado),
                    )

                    # Aplicar paso si hubo cambios respecto al estado anterior
                    if nivel_seguro != ultimo_nivel:
                        hora_str = datetime.now().strftime("%H:%M:%S")

                        diferencia_pasos = abs(
                            nivel_seguro - pot.posicion_actual
                        )
                        if diferencia_pasos > 20:
                            print(
                                f"\n[{hora_str}] [DIGIPOT] Salto grande"
                                f" ({diferencia_pasos} pasos). Re-calibrando"
                                " a cero..."
                            )
                            pot.resetear_a_cero()
                            time.sleep(0.010)

                        pot.set_nivel(nivel_seguro, guardar_eeprom=False)
                        time.sleep(0.100)

                        ultimo_nivel = nivel_seguro
                        NIVEL_POT_ACTUAL = nivel_seguro

                except Exception as e:
                    ads_conectado = False
                    VCC_MEDIDO_ADS = 0.0
                    hora_str = datetime.now().strftime("%H:%M:%S")
                    print(
                        f"\n[{hora_str}] [DIGIPOT ERROR] Fallo I2C ADS1115:"
                        f" {e}. Caída a seguridad #{POS_SEGURIDAD} (3.3V)"
                    )
                    pot.set_nivel(POS_SEGURIDAD, guardar_eeprom=False)
                    NIVEL_POT_ACTUAL = POS_SEGURIDAD
                    ultimo_nivel = POS_SEGURIDAD
            else:
                VCC_MEDIDO_ADS = 0.0
                if pot.posicion_actual != POS_SEGURIDAD:
                    pot.set_nivel(POS_SEGURIDAD, guardar_eeprom=False)
                    NIVEL_POT_ACTUAL = POS_SEGURIDAD
                    ultimo_nivel = POS_SEGURIDAD

            time.sleep(0.5)

        except Exception as e:
            hora_str = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{hora_str}] [DIGIPOT ERROR] {e}")
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