import os
import time
import serial
from datetime import datetime

# Mapeo de puertos UART en Raspberry Pi 5
UART_DEVICES = {
    "UART0": "/dev/ttyAMA0",
    "UART4": "/dev/ttyAMA4"
}

BAUDRATE = 115200

# ==========================================
# LECTURA DE SISTEMA
# ==========================================
def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read()) / 1000.0
    except Exception:
        return 0.0

# ==========================================
# BUFFER LOGGER PARA UART
# ==========================================
class BufferLoggerUART:
    def __init__(self, uart_name, intervalo_minutos=2):
        self.uart_name = uart_name
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
                        "UART",
                        self.uart_name,
                        fecha
                    )
                    os.makedirs(folder_path, exist_ok=True)
                    file_path = os.path.join(folder_path, filename)
                    with open(file_path, "w") as f:
                        f.writelines(self.buffer)

                self.buffer.clear()
            self.inicio_bloque = tiempo_actual