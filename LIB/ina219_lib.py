import os
import time
from datetime import datetime
from ina219 import INA219

INA219_ADDR = 0x40
BUS_I2C = 1

def get_cpu_temp():
    """Lee la temperatura actual del SoC de la Raspberry Pi 5."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read()) / 1000.0
    except Exception:
        return 0.0

class INA219Monitor:
    def __init__(self, i2c_addr=INA219_ADDR, busnum=BUS_I2C, intervalo_minutos=2):
        self.intervalo = intervalo_minutos
        self.buffer = []
        self.inicio_bloque = time.time()
        self.ina = None
        
        try:
            self.ina = INA219(
                shunt_ohms=0.1, 
                max_expected_amps=2.0, 
                address=i2c_addr, 
                busnum=busnum
            )
            self.ina.configure(self.ina.RANGE_16V)
            print(f"[INA219] Inicializado con éxito en Bus {busnum}, Dirección 0x{i2c_addr:02X}")
        except Exception as e:
            print(f"[INA219] Error al inicializar en 0x{i2c_addr:02X}: {e}")

    def leer_consumo(self):
        if self.ina is None:
            return 0.0, 0.0, 0.0
        try:
            v_bus = self.ina.voltage()
            i_ma = self.ina.current()
            p_mw = self.ina.power()
            return v_bus, i_ma, p_mw
        except Exception:
            return 0.0, 0.0, 0.0

    def registrar_lectura(self, nivel_pot=1, temp_cpu=0.0):
        v, i, p = self.leer_consumo()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hora_pantalla = datetime.now().strftime("%H:%M:%S")
        
        # Formato ampliado con DigiPot y CPU Temp
        linea = (
            f"[{timestamp}] [INA219] I={i:.2f}mA | "
            f"POT={nivel_pot}/100 | CPU={temp_cpu:.1f} °C\n"
        )
        self.buffer.append(linea)
        
        # Muestra la lectura actual completa por terminal
        print(
            f"[{hora_pantalla}] [INA219] I: {i:.2f}mA | "
            f"POT: {nivel_pot}/100 | CPU: {temp_cpu:.1f} °C"
        )

    def verificar_y_guardar(self, forzar=False):
        tiempo_actual = time.time()
        if (tiempo_actual - self.inicio_bloque >= self.intervalo * 60) or (forzar and self.buffer):
            if self.buffer:
                ahora = datetime.now()
                fecha = ahora.strftime("%Y-%m-%d")
                filename = f"log_{ahora.strftime('%H_%M_%S')}.txt"

                for base_folder in ["DATOS", "SUBIDA"]:
                    folder_path = os.path.join(base_folder, "INA219", fecha)
                    os.makedirs(folder_path, exist_ok=True)
                    file_path = os.path.join(folder_path, filename)
                    with open(file_path, "w") as f:
                        f.writelines(self.buffer)

                self.buffer.clear()
            self.inicio_bloque = time.time()