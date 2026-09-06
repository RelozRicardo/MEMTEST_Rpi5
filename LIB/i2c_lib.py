import os
import time
from datetime import datetime
from smbus2 import SMBus

BUS_I2C = 1
bus = None

def init_bus():
    global bus
    if bus is None:
        bus = SMBus(BUS_I2C)

def buscar_eeproms():
    init_bus()
    encontradas = []
    for addr in range(0x50, 0x58):
        try:
            bus.read_byte(addr)
            encontradas.append(addr)
        except Exception:
            pass
    return encontradas

def write_byte(i2c_addr, mem_addr, data):
    init_bus()
    high = (mem_addr >> 8) & 0xFF
    low = mem_addr & 0xFF
    bus.write_i2c_block_data(i2c_addr, high, [low, data])
    time.sleep(0.005)

def read_byte(i2c_addr, mem_addr):
    init_bus()
    high = (mem_addr >> 8) & 0xFF
    low = mem_addr & 0xFF
    bus.write_i2c_block_data(i2c_addr, high, [low])
    return bus.read_byte(i2c_addr)

def autodetectar_tamano_eeprom(i2c_addr):
    """
    Sondea direcciones limite de memorias I2C tipicas (24C32, 24C64, 24C128, 24C256, 24C512).
    Devuelve la capacidad utilizable en Bytes.
    """
    tamanos = [4096, 8192, 16384, 32768, 65536]
    tamano_ok = 4096
    for size in tamanos:
        try:
            read_byte(i2c_addr, size - 1)
            tamano_ok = size
        except Exception:
            break
    return tamano_ok

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read()) / 1000.0
    except Exception:
        return 0.0

class BufferLoggerI2C:
    def __init__(self, i2c_addr, intervalo_minutos=2):
        self.i2c_addr = i2c_addr
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
                        "I2C",
                        f"EEPROM_0x{self.i2c_addr:02X}",
                        fecha
                    )
                    os.makedirs(folder_path, exist_ok=True)
                    file_path = os.path.join(folder_path, filename)
                    with open(file_path, "w") as f:
                        f.writelines(self.buffer)

                self.buffer.clear()
            self.inicio_bloque = tiempo_actual