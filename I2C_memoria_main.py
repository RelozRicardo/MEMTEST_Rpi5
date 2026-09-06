import sys
import os
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(BASE_DIR, "LIB")
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

from i2c_lib import (
    buscar_eeproms,
    write_byte,
    read_byte,
    autodetectar_tamano_eeprom,
    get_cpu_temp,
    BufferLoggerI2C
)

PATRON = 0xAA
eeproms_activas = {}

print("=== INICIANDO SERVICIO MONITOREO MEMORIAS I2C ===")

try:
    while True:
        detectadas = set(buscar_eeproms())
        conocidas = set(eeproms_activas.keys())
        
        nuevas = detectadas - conocidas
        desconectadas = conocidas - detectadas

        # Inicialización de EEPROM detectada
        for addr in nuevas:
            mem_size = autodetectar_tamano_eeprom(addr)
            kb_size = mem_size / 1024.0
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] EEPROM 0x{addr:02X} detectada. Tamanio: {kb_size:.0f} KB ({mem_size} Bytes)")
            
            logger = BufferLoggerI2C(i2c_addr=addr, intervalo_minutos=2)
            logger.agregar_evento(f"EEPROM CONECTADA EN DIRECCION 0x{addr:02X} | TAMANO: {kb_size:.0f} KB")
            logger.agregar_evento("Iniciando escritura de patron inicial 0xAA...")

            # Escritura usando el tamaño detectado
            for mem_addr in range(mem_size):
                write_byte(addr, mem_addr, PATRON)
                if mem_addr > 0 and mem_addr % 4096 == 0:
                    print(f"  -> 0x{addr:02X}: Escritos {mem_addr} / {mem_size} bytes")
            
            print(f"Escritura finalizada en 0x{addr:02X}. Iniciando monitoreo de SEU.")
            logger.agregar_evento("Escritura de patron completada con exito.")

            eeproms_activas[addr] = {
                "logger": logger,
                "mem_size": mem_size,
                "vueltas": 0,
                "errores_totales": 0,
                "errores_reportados": set(),
                "inicio": datetime.now()
            }

        # Desconexiones
        for addr in desconectadas:
            info = eeproms_activas[addr]
            logger = info["logger"]
            duracion = datetime.now() - info["inicio"]
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] EEPROM 0x{addr:02X} desconectada.")
            logger.agregar_evento(f"EEPROM DESCONECTADA 0x{addr:02X}")
            logger.agregar_evento(f"Resumen final -> Tiempo: {duracion} | Vueltas: {info['vueltas']} | SEUs: {info['errores_totales']}")
            
            logger.verificar_y_guardar(forzar=True)
            del eeproms_activas[addr]

        # Monitoreo y barrido ajustado a cada EEPROM
        for addr, info in list(eeproms_activas.items()):
            info["vueltas"] += 1
            logger = info["logger"]
            tamano_actual = info["mem_size"]

            for mem_addr in range(tamano_actual):
                dato = read_byte(addr, mem_addr)
                
                if dato != PATRON:
                    info["errores_totales"] += 1
                    
                    if mem_addr not in info["errores_reportados"]:
                        info["errores_reportados"].add(mem_addr)
                        msg_seu = (
                            f"SEU DETECTADO! Dir: 0x{mem_addr:04X} | "
                            f"Leido: 0x{dato:02X} | Esperado: 0x{PATRON:02X} | "
                            f"Vuelta #{info['vueltas']}"
                        )
                        print(f"[ALERT 0x{addr:02X}] {msg_seu}")
                        logger.agregar_evento(msg_seu)

            temp_cpu = get_cpu_temp()
            logger.agregar_evento(
                f"Vuelta #{info['vueltas']} completa | SEUs acumulados: {info['errores_totales']} | CPU: {temp_cpu:.1f}°C"
            )

            logger.verificar_y_guardar()

        time.sleep(1)

except KeyboardInterrupt:
    print("\nDeteniendo servicio I2C...")
    for addr, info in eeproms_activas.items():
        info["logger"].agregar_evento("SERVICIO DETENIDO MANUALMENTE (KeyboardInterrupt)")
        info["logger"].verificar_y_guardar(forzar=True)
    print("Buffer guardado y programa finalizado.")