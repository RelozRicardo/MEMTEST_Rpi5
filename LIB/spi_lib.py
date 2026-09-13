import os
import time
from datetime import datetime
import spidev

# Instancia SPI principal (Bus 0)
spi = spidev.SpiDev()


def init_spi(device_id=0, max_speed_hz=1000000):
    """Inicializa el Bus 0 para el canal de hardware correspondiente (0 = CE0, 1 = CE1)."""
    global spi
    try:
        spi.close()
    except Exception:
        pass

    spi.open(0, device_id)
    spi.max_speed_hz = max_speed_hz
    spi.mode = 0b00  # Mode 0 (CPOL=0, CPHA=0)


def esperar_listo(device_id):
    """Lee el Status Register 1 (0x05) hasta que el bit BUSY (bit 0) sea 0."""
    init_spi(device_id)
    while True:
        resp = spi.xfer2([0x05, 0x00])
        if not (resp[1] & 0x01):
            break
        time.sleep(0.001)


def obtener_capacidad_spi(device_id):
    """Lee el JEDEC ID (0x9F) para determinar el tamaño físico de la memoria en bytes."""
    init_spi(device_id)
    resp = spi.xfer2([0x9F, 0x00, 0x00, 0x00])

    fabricante = resp[1]
    tipo_memoria = resp[2]
    capacidad_code = resp[3]

    # Descarta lecturas flotantes/basura si no hay memoria conectada (0xFF o 0x00)
    if fabricante in [0xFF, 0x00] or tipo_memoria in [0xFF, 0x00]:
        return 0

    # Rango de capacidad para memorias SPI NOR Flash (0x10 = 1MB hasta 0x19 = 32MB)
    if 0x10 <= capacidad_code <= 0x19:
        return 1 << capacidad_code
    else:
        return 0


def chip_erase_spi(device_id):
    """Ejecuta un borrado completo de la memoria (Chip Erase 0xC7)."""
    esperar_listo(device_id)

    # 1. Write Enable
    spi.xfer2([0x06])

    # 2. Command Chip Erase
    spi.xfer2([0xC7])

    # 3. Esperar a que finalice el borrado
    esperar_listo(device_id)

def esperar_listo(device_id):
    """Lee el Status Register 1 (0x05) en bucle hasta que el bit BUSY (bit 0) sea 0."""
    init_spi(device_id)
    while True:
        # Comando 0x05 + 1 dummy byte para recibir la respuesta
        resp = spi.xfer2([0x05, 0x00])
        status = resp[1]
        
        # El bit 0 es BUSY (1 = Ocupado programando/borrando, 0 = Listo)
        if not (status & 0x01):
            break
        
        time.sleep(0.001)  # Pausa de 1ms para no saturar la CPU de la Pi

def write_page_spi(device_id, mem_addr, data_bytes):
    """Escribe un bloque de datos (hasta 128 bytes) asegurando alineación de página."""
    # Asegura que el bloque nunca supere los 128 bytes
    data_bytes = data_bytes[:128]

    esperar_listo(device_id)

    # 1. Write Enable (0x06)
    spi.xfer2([0x06])

    # 2. Page Program (0x02) + Dirección de 24 bits + Datos (128 bytes)
    addr_h = (mem_addr >> 16) & 0xFF
    addr_m = (mem_addr >> 8) & 0xFF
    addr_l = mem_addr & 0xFF

    spi.xfer2([0x02, addr_h, addr_m, addr_l] + list(data_bytes))

    # 3. Esperar que la memoria grabe las celdas en el silicio
    esperar_listo(device_id)

def read_byte_spi(device_id, mem_addr):
    """Lee un byte en direccionamiento de 24-bit."""
    init_spi(device_id)

    addr_h = (mem_addr >> 16) & 0xFF
    addr_m = (mem_addr >> 8) & 0xFF
    addr_l = mem_addr & 0xFF

    respuesta = spi.xfer2([0x03, addr_h, addr_m, addr_l, 0x00])
    return respuesta[4]

def read_block_spi(device_id, mem_addr, length=128):
    """Lee un bloque continuo de bytes (por defecto 128 bytes)."""
    init_spi(device_id)

    addr_h = (mem_addr >> 16) & 0xFF
    addr_m = (mem_addr >> 8) & 0xFF
    addr_l = mem_addr & 0xFF

    # Comando READ (0x03) + Dirección (3 bytes) + 128 bytes dummy
    cmd = [0x03, addr_h, addr_m, addr_l] + [0x00] * length
    respuesta = spi.xfer2(cmd)

    # Retorna únicamente los 128 bytes leídos
    return respuesta[4:]

def buscar_memorias_spi():
    """Busca memorias únicamente en los canales hardware CS0 (CE0) y CS1 (CE1)."""
    encontradas = []
    for dev_id in [0, 1]:
        try:
            tamano = obtener_capacidad_spi(dev_id)
            if tamano > 0:
                encontradas.append(dev_id)
        except Exception:
            pass
    return encontradas


def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read()) / 1000.0
    except Exception:
        return 0.0


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
                        fecha,
                    )
                    os.makedirs(folder_path, exist_ok=True)
                    file_path = os.path.join(folder_path, filename)
                    with open(file_path, "w") as f:
                        f.writelines(self.buffer)

                self.buffer.clear()
            self.inicio_bloque = tiempo_actual