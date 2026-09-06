import sys
import os
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(BASE_DIR, "LIB")
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

from spi_lib import (
    buscar_memorias_spi,
    write_byte_spi,
    read_byte_spi,
    get_cpu_temp,
    BufferLoggerSPI
)

MEM_SIZE = 32768  # Ajuste base de tamaño de la memoria SPI (32 KB)
PATRON = 0xAA
memorias_activas = {}

print("=== INICIANDO SERVICIO MONITOREO MEMORIAS SPI ===")

try:
    while True:
        detectadas = set(buscar_memorias_spi())
        conocidas = set(memorias_activas.keys())
        
        nuevas = detectadas - conocidas
        desconectadas = conocidas - detectadas

        # Inicialización de Canales SPI Detectados
        for dev_id in nuevas:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Memoria SPI detectada en Canal CS{dev_id}")
            
            logger = BufferLoggerSPI(device_id=dev_id, intervalo_minutos=2)
            logger.agregar_evento(f"MEMORIA SPI CONECTADA EN CANAL CS{dev_id}")
            logger.agregar_evento("Iniciando escritura de patron inicial 0xAA...")

            # Escritura inicial del patrón
            for mem_addr in range(MEM_SIZE):
                write_byte_spi(dev_id, mem_addr, PATRON)
                if mem_addr > 0 and mem_addr % 8192 == 0:
                    print(f"  -> CS{dev_id}: Escritos {mem_addr} / {MEM_SIZE} bytes")
            
            print(f"Escritura finalizada en Canal CS{dev_id}. Iniciando monitoreo de SEU.")
            logger.agregar_evento("Escritura de patron completada con exito.")

            memorias_activas[dev_id] = {
                "logger": logger,
                "vueltas": 0,
                "errores_totales": 0,
                "errores_reportados": set(),
                "inicio": datetime.now()
            }

        # Manejo de Desconexiones
        for dev_id in desconectadas:
            info = memorias_activas[dev_id]
            logger = info["logger"]
            duracion = datetime.now() - info["inicio"]
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Memoria SPI CS{dev_id} desconectada.")
            logger.agregar_evento(f"MEMORIA SPI DESCONECTADA CANAL CS{dev_id}")
            logger.agregar_evento(f"Resumen final -> Tiempo: {duracion} | Vueltas: {info['vueltas']} | SEUs: {info['errores_totales']}")
            
            logger.verificar_y_guardar(forzar=True)
            del memorias_activas[dev_id]

        # Monitoreo continuo
        for dev_id, info in list(memorias_activas.items()):
            info["vueltas"] += 1
            logger = info["logger"]

            for mem_addr in range(MEM_SIZE):
                dato = read_byte_spi(dev_id, mem_addr)
                
                if dato != PATRON:
                    info["errores_totales"] += 1
                    
                    if mem_addr not in info["errores_reportados"]:
                        info["errores_reportados"].add(mem_addr)
                        
                        hora_pantalla = datetime.now().strftime('%H:%M:%S')
                        msg_seu = (
                            f"SEU DETECTADO! Dir: 0x{mem_addr:04X} | "
                            f"Leido: 0x{dato:02X} | Esperado: 0x{PATRON:02X} | "
                            f"Vuelta #{info['vueltas']}"
                        )
                        print(f"[{hora_pantalla}] [ALERT CS{dev_id}] {msg_seu}")
                        logger.agregar_evento(msg_seu)

            temp_cpu = get_cpu_temp()
            hora_pantalla = datetime.now().strftime('%H:%M:%S')
            msg_resumen = (
                f"Vuelta #{info['vueltas']} completa | "
                f"SEUs acumulados: {info['errores_totales']} | CPU: {temp_cpu:.1f}°C"
            )
            print(f"[{hora_pantalla}] [INFO CS{dev_id}] {msg_resumen}")
            logger.agregar_evento(msg_resumen)

            logger.verificar_y_guardar()

        time.sleep(1)

except KeyboardInterrupt:
    print("\nDeteniendo servicio SPI...")
    for dev_id, info in memorias_activas.items():
        info["logger"].agregar_evento("SERVICIO DETENIDO MANUALMENTE (KeyboardInterrupt)")
        info["logger"].verificar_y_guardar(forzar=True)
    print("Buffer guardado y programa finalizado.")