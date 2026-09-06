import time
import RPi.GPIO as GPIO

PIN_UD = 17   # UP/DOWN
PIN_INC = 27  # INCREMENT
PIN_CS = 22   # CHIP SELECT

class X9C103S:
    def __init__(self, pin_ud=PIN_UD, pin_inc=PIN_INC, pin_cs=PIN_CS):
        self.pin_ud = pin_ud
        self.pin_inc = pin_inc
        self.pin_cs = pin_cs
        self.posicion_actual = 0  # Rango absoluto: 0 a 99 (100 posiciones)

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.pin_ud, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(self.pin_inc, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(self.pin_cs, GPIO.OUT, initial=GPIO.HIGH)

    def _pulso_inc(self):
        GPIO.output(self.pin_inc, GPIO.LOW)
        time.sleep(0.002)  # 2 ms asegura complimiento holgado del datasheet
        GPIO.output(self.pin_inc, GPIO.HIGH)
        time.sleep(0.002)

    def resetear_a_cero(self):
        """Baja el potenciómetro al tope mínimo (100 pasos hacia abajo)."""
        GPIO.output(self.pin_cs, GPIO.LOW)
        GPIO.output(self.pin_ud, GPIO.LOW)
        time.sleep(0.001)  # Setup time para U/D

        for _ in range(100):
            self._pulso_inc()

        # Desactivar CS sin guardar en EEPROM para no desgastar ciclos
        GPIO.output(self.pin_inc, GPIO.LOW)
        GPIO.output(self.pin_cs, GPIO.HIGH)
        GPIO.output(self.pin_inc, GPIO.HIGH)
        
        self.posicion_actual = 0

    def set_nivel(self, objetivo, guardar_eeprom=False):
        """Ajusta el nivel del pot entre 0 y 99."""
        objetivo = max(0, min(99, objetivo))
        
        if objetivo == self.posicion_actual:
            return

        GPIO.output(self.pin_cs, GPIO.LOW)
        
        if objetivo > self.posicion_actual:
            GPIO.output(self.pin_ud, GPIO.HIGH)  # Incrementar
            pasos = objetivo - self.posicion_actual
        else:
            GPIO.output(self.pin_ud, GPIO.LOW)   # Decrementar
            pasos = self.posicion_actual - objetivo

        time.sleep(0.001)  # Setup time U/D -> INC

        for _ in range(pasos):
            self._pulso_inc()

        if guardar_eeprom:
            # CS sube con INC en HIGH -> Guarda posición en memoria no volátil
            GPIO.output(self.pin_inc, GPIO.HIGH)
            GPIO.output(self.pin_cs, GPIO.HIGH)
            time.sleep(0.020)  # Espera t_WC (20 ms para ciclo completo de escritura EEPROM)
        else:
            # CS sube con INC en LOW -> NO guarda en EEPROM (ahorra desgaste)
            GPIO.output(self.pin_inc, GPIO.LOW)
            GPIO.output(self.pin_cs, GPIO.HIGH)
            GPIO.output(self.pin_inc, GPIO.HIGH)

        self.posicion_actual = objetivo

    def cleanup(self):
        GPIO.cleanup([self.pin_ud, self.pin_inc, self.pin_cs])