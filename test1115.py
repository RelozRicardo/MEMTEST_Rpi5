import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# Inicializar bus I2C
i2c = busio.I2C(board.SCL, board.SDA)

# Instanciar el ADS1115 en dirección 0x48
ads = ADS.ADS1115(i2c, address=0x48)

# Canal A0 (el pin 0 equivale a P0)
chan = AnalogIn(ads, 0)

print("--- Leyendo ADS1115 en 0x48 (Canal A0) ---")
try:
    while True:
        print(f"Valor digital: {chan.value:6d}  |  Tensión: {2*chan.voltage:6.4f} V")
        time.sleep(1)
except KeyboardInterrupt:
    print("\nLectura finalizada.")