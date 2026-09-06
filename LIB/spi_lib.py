import os
import time
from datetime import datetime
import spidev
import RPi.GPIO as GPIO

# ==========================================
# CONFIGURACIÓN DE PINES SPI Y CS MANUAL
# ==========================================
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Mapeo de canales SPI
# Canal 0: CE0 (Hardware - GPIO 8)
# Canal 1: CE1 (Hardware - GPIO 7)
# Canal 2: CS2 (Manual - GPIO 5)
PIN_CS2 = 5
GPIO.setup(PIN_CS2, GPIO.OUT, initial=GPIO.HIGH)

# Instancia SPI principal (Bus 0)
spi = spidev.SpiDev()

def init_spi(device_id=0, max_speed_hz=1000000):
    """Inicializa la comunicación SPI en el Bus 0 con el canal indicado (0, 1 o 2)."""
    global spi
    try:
        spi.close()
    except Exception:
        pass

    if device_id in [0, 1]:
        spi.open(0, device_id)
    elif device_id == 2:
        # Para el CS manual (GPIO 5), abrimos el bus en modo 'no CS' o usando canal 0
        spi.open(0, 0)
        spi.no_cs = True  # Desactiva el control automatico de hardware para controlar GPIO 5 manualmente
        
    spi.max_speed_hz = max_speed_hz
    spi.mode = 0b00  # SPI Mode 0 (CPOL=0, CPHA=0)

def seleccionar_cs(device_id, enable=True):
    """Maneja la línea CS2 manual si corresponde."""
    if device_id == 2:
        # CS activo en LOW
        GPIO.output(PIN_CS2, GPIO.LOW if enable else GPIO.HIGH)

# ==========================================
# LECTURA / ESCRITURA SPI (Comandos Estándar 25xxx)
# ==========================================
# Comandos tipicos EEPROM/Flash SPI:
# 0x06 = Write Enable (WREN)
# 0x02 = Write (WRITE)
# 0x03 = Read (READ)

def write_byte_spi(device_id, mem_addr, data):
    """Escribe un byte en la memoria SPI dada."""
    init_spi(device_id)
    
    # 1. Enviar comando WRITE ENABLE (0x06)
    seleccionar_cs(device_id, True)
    spi.xfer2([0x06])
    seleccionar_cs(device_id, False)
    
    time.sleep(0.001)

    # 2. Enviar comando WRITE (0x02) + Dirección 16-bit + Dato
    high = (mem_addr >> 8) & 0xFF
    low = mem_addr & 0xFF
    
    seleccionar_cs(device_id, True)
    spi.xfer2([0x02, high, low, data])
    seleccionar_cs(device_id, False)
    
    time.sleep(0.005)  # Tiempo de escritura física (tWR)

def read_byte_spi(device_id, mem_addr):
    """Lee un byte de la memoria SPI dada."""
    init_spi(device_id)
    
    high = (mem_addr >> 8) & 0xFF
    low = mem_addr & 0xFF
    
    seleccionar_cs(device_id, True)
    # Mandamos 0x03 (READ), Dirección High, Dirección Low, y un dummy byte (0x00) para recibir la respuesta
    respuesta = spi.xfer2([0x03, high, low, 0x00])
    seleccionar_cs(device_id, False)
    
    return respuesta[3]

def buscar_memorias_spi():
    """Prueba comunicación en los 3 canales SPI (CE0, CE1, CS2) intentando leer la dirección 0."""
    encontradas = []
    for dev_id in [0, 1, 2]:
        try:
            read_byte_spi(dev_id, 0)
            encontradas.append(dev_id)
        except Exception:
            pass
    return encontradas

# ==========================================
# LECTURA DE TEMPERATURA
# ==========================================
def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read()) / 1000.0
    except Exception:
        return 0.0

# ==========================================
# BUFFER LOGGER PARA SPI
# ==========================================
class BufferLoggerSPI:
    def __init__(self, device_id, intervalo_minutos=2):
        self.device_id = device_id
        self.intervalo = intervalo_minutos
        self.buffer = []
        self.inicio_bloque = time.time()

    def agregar_evento(self, texto):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.buffer.append(f"[{timestamp}] {texto}\n")

    def verificar_y_guardar(self, forzar=False):
        tiempo_actual = time.time()
        if (tiempo_actual - self.inicio_bloque >= self.intervalo * 60) or (forzar and self.buffer):
            if self.buffer:
                ahora = datetime.now()
                fecha = ahora.strftime("%Y-%m-%d")
                filename = f"log_{ahora.strftime('%H_%M_%S')}.txt"

                for base_folder in ["DATOS", "SUBIDA"]:
                    folder_path = os.path.join(
                        base_folder,
                        "SPI",
                        f"CANAL_CS{self.device_id}",
                        fecha
                    )
                    os.makedirs(folder_path, exist_ok=True)
                    file_path = os.path.join(folder_path, filename)
                    with open(file_path, "w") as f:
                        f.writelines(self.buffer)

                self.buffer.clear()
            self.inicio_bloque = tiempo_actual