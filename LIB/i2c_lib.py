import os
import time
from datetime import datetime
from smbus2 import SMBus, i2c_msg

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

def write_page_i2c(i2c_addr, mem_addr, data_bytes, bus_num=1):
  """Escribe una página de datos (hasta 64 bytes) en una EEPROM I2C (dirección de 16 bits)."""
  addr_msb = (mem_addr >> 8) & 0xFF
  addr_lsb = mem_addr & 0xFF

  payload = [addr_msb, addr_lsb] + list(data_bytes[:64])

  with SMBus(bus_num) as bus:
    msg = i2c_msg.write(i2c_addr, payload)
    bus.i2c_rdwr(msg)

  # Espera de tiempo interno de grabado EEPROM (tWR ~5ms)
  time.sleep(0.005)

def read_block_i2c(i2c_addr, mem_addr, length=128, bus_num=1):
  """Lee un bloque continuo de bytes usando lectura ráfaga I2C (dirección de 16 bits)."""
  addr_msb = (mem_addr >> 8) & 0xFF
  addr_lsb = mem_addr & 0xFF

  with SMBus(bus_num) as bus:
    # 1. Transmitir dirección a leer (2 bytes)
    write_cmd = i2c_msg.write(i2c_addr, [addr_msb, addr_lsb])
    # 2. Leer ráfaga de datos
    read_cmd = i2c_msg.read(i2c_addr, length)

    bus.i2c_rdwr(write_cmd, read_cmd)
    return list(read_cmd)

import time
from smbus2 import SMBus, i2c_msg

def write_byte_direct(i2c_addr, mem_addr, valor, bus_num=1):
    """Escribe un único byte en una dirección de 16 bits."""
    addr_msb = (mem_addr >> 8) & 0xFF
    addr_lsb = mem_addr & 0xFF
    with SMBus(bus_num) as bus:
        msg = i2c_msg.write(i2c_addr, [addr_msb, addr_lsb, valor & 0xFF])
        bus.i2c_rdwr(msg)
    time.sleep(0.005)  # Espera tWR (5ms)

def read_byte_direct(i2c_addr, mem_addr, bus_num=1):
    """Lee un único byte de una dirección de 16 bits."""
    addr_msb = (mem_addr >> 8) & 0xFF
    addr_lsb = mem_addr & 0xFF
    with SMBus(bus_num) as bus:
        write_cmd = i2c_msg.write(i2c_addr, [addr_msb, addr_lsb])
        read_cmd = i2c_msg.read(i2c_addr, 1)
        bus.i2c_rdwr(write_cmd, read_cmd)
        return list(read_cmd)[0]

def autodetectar_tamano_eeprom(i2c_addr=0x50, bus_num=1):
    """Detecta automáticamente el tamaño de la EEPROM probando wrap-around."""
    try:
        val_orig = read_byte_direct(i2c_addr, 0x0000, bus_num)
        
        # Escribir marcador en la dirección 0
        MARCADOR = 0xA5
        write_byte_direct(i2c_addr, 0x0000, MARCADOR, bus_num)
        
        # Probar límites exponenciales (4KB, 8KB, 16KB, 32KB, 64KB)
        capacidades_test = [4096, 8192, 16384, 32768, 65536]
        tamano_detectado = 32768  # Por defecto 32KB si no hay wrap-around en rangos bajos
        
        for cap in capacidades_test:
            write_byte_direct(i2c_addr, cap, 0x5A, bus_num)
            check_dir0 = read_byte_direct(i2c_addr, 0x0000, bus_num)
            
            if check_dir0 == 0x5A:
                tamano_detectado = cap
                break
        
        # Restaurar byte original
        write_byte_direct(i2c_addr, 0x0000, val_orig, bus_num)
        return tamano_detectado
    except Exception:
        # Fallback de seguridad en caso de error en bus: asume 32KB (K24C256)
        return 32768

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read()) / 1000.0
    except Exception:
        return 0.0

def autodetectar_tamano_eeprom(i2c_addr=0x50):
    """Detecta automáticamente la capacidad de la memoria I2C (en Bytes)

    probando desbordamientos de página desde 1KB hasta 128KB.
    """
    # Guardar valor original del byte 0
    val_orig = read_byte_direct(i2c_addr, 0x0000)

    # Marcador en la dirección 0x0000
    MARCADOR = 0xA5
    write_byte_direct(i2c_addr, 0x0000, MARCADOR)

    # Probar potencias de 2 (desde 1KB hasta 128KB)
    # 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072
    tamano_detectado = 1024
    capacidades_test = [1024 * (2**i) for i in range(8)]

    for cap in capacidades_test:
        if cap == 1024:
            continue

        # Escribir patrón diferente en el límite de prueba
        write_byte_direct(i2c_addr, cap, 0x5A)

        # Leer qué ocurrió en la dirección 0x0000
        check_dir0 = read_byte_direct(i2c_addr, 0x0000)

        # Si cambió el byte 0, la memoria hizo wrap-around -> alcanzamos el límite real
        if check_dir0 == 0x5A:
            tamano_detectado = cap
            break

    # Restaurar el byte original en la dirección 0x0000
    write_byte_direct(i2c_addr, 0x0000, val_orig)

    return tamano_detectado

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