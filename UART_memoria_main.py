import sys
import os
import time
import serial
import threading
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(BASE_DIR, "LIB")
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

from uart_lib import (
    UART_DEVICES,
    BAUDRATE,
    get_cpu_temp,
    BufferLoggerUART
)

def hilo_listener_uart(uart_name, port_path):
    """Hilo independiente de monitoreo para cada puerto UART."""
    logger = BufferLoggerUART(uart_name=uart_name, intervalo_minutos=2)
    logger.agregar_evento(f"INICIANDO SERVICIO DE LECTURA EN {uart_name} ({port_path})")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Escuchando en {uart_name} en {port_path} @ {BAUDRATE} baud...")

    try:
        ser = serial.Serial(port_path, BAUDRATE, timeout=1)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: No se pudo abrir {uart_name} en {port_path}: {e}")
        logger.agregar_evento(f"ERROR AL ABRIR PUERTO: {e}")
        logger.verificar_y_guardar(forzar=True)
        return

    vector_acumulado = ""

    while True:
        try:
            if ser.in_waiting > 0:
                # Leer caracteres entrantes
                caracteres = ser.read(ser.in_waiting).decode('ascii', errors='replace')
                
                for char in caracteres:
                    # Detectar el ENTER (\n o \r) como flag de fin de paquete
                    if char in ['\n', '\r']:
                        vector_limpio = vector_acumulado.strip()
                        
                        if vector_limpio:
                            hora_pantalla = datetime.now().strftime('%H:%M:%S')
                            temp_cpu = get_cpu_temp()
                            
                            msg_log = f"RX={vector_limpio} | CPU={temp_cpu:.1f}C"
                            
                            # Imprimir evento en consola
                            print(f"[{hora_pantalla}] [{uart_name}] {msg_log}")
                            
                            # Cargar al buffer
                            logger.agregar_evento(msg_log)
                        
                        # Reiniciar buffer de caracteres para la siguiente trama
                        vector_acumulado = ""
                    else:
                        vector_acumulado += char

            # Revisar si corresponde volcar datos a disco cada 2 minutos
            logger.verificar_y_guardar()
            time.sleep(0.01)

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR en hilo {uart_name}: {e}")
            logger.agregar_evento(f"ERROR DE LECTURA: {e}")
            time.sleep(1)

print("=== INICIANDO SERVICIO MULTI-UART (UART0 Y UART4) ===")

hilos = []

# Crear y lanzar un hilo independiente por puerto UART configurado
for name, path in UART_DEVICES.items():
    t = threading.Thread(target=hilo_listener_uart, args=(name, path), daemon=True)
    t.start()
    hilos.append(t)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDeteniendo servicio UART...")