import os
import sys
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(BASE_DIR, "LIB")
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

from i2c_lib import (
    BufferLoggerI2C,
    autodetectar_tamano_eeprom,
    buscar_eeproms,
    get_cpu_temp,
    read_block_i2c,
    write_page_i2c,
)

PATRON = 0xAA
CHUNK_PAGE = 64     # Tamaño de página para EEPROM (K24C256 / 24Cxx)
CHUNK_READ = 128    # Lectura secuencial rápida por bloques
PAUSA_ENTRE_VUELTAS = 1  # Tiempo de descanso entre vueltas completas

eeproms_activas = {}

print("=== INICIANDO SERVICIO MONITOREO MEMORIAS I2C (DATOS / SUBIDA) ===")

try:
    while True:
        hora_act = datetime.now().strftime("%H:%M:%S")
        print(
            f"\r\033[K[{hora_act}] Monitoreando bus I2C (Activas:"
            f" {[hex(a) for a in eeproms_activas.keys()]})...",
            end="",
            flush=True,
        )

        detectadas = set(buscar_eeproms())
        conocidas = set(eeproms_activas.keys())

        nuevas = detectadas - conocidas
        desconectadas = conocidas - detectadas

        # ---------------------------------------------------------
        # Inicialización de Nuevas Memorias I2C Detectadas
        # ---------------------------------------------------------
        for addr in nuevas:
            print()  # Salto de línea para limpiar la barra de escaneo
            mem_size = autodetectar_tamano_eeprom(addr)
            kb_size = mem_size / 1024.0

            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] ¡NUEVA EEPROM"
                f" DETECTADA! Dirección: 0x{addr:02X} | Tamaño: {kb_size:.0f} KB"
                f" ({mem_size} Bytes)"
            )

            # Instanciar el logger que administra la estructura DATOS y SUBIDA
            logger = BufferLoggerI2C(i2c_addr=addr, intervalo_minutos=2)
            logger.agregar_evento(
                f"EEPROM CONECTADA EN DIRECCION 0x{addr:02X} | CAPACIDAD:"
                f" {kb_size:.0f} KB ({mem_size} Bytes)"
            )

            # Carga del patrón inicial 0xAA por páginas
            print(
                f"  -> 0x{addr:02X}: Cargando patrón 0xAA en bloques de"
                f" {CHUNK_PAGE}B..."
            )
            logger.agregar_evento("Iniciando escritura de patrón inicial 0xAA...")

            patron_bloque = [PATRON] * CHUNK_PAGE
            for mem_addr in range(0, mem_size, CHUNK_PAGE):
                write_page_i2c(addr, mem_addr, patron_bloque)

                if mem_addr > 0 and mem_addr % 4096 == 0:
                    print(
                        f"  -> 0x{addr:02X}: Escritos {mem_addr} / {mem_size}"
                        " bytes"
                    )

            print(
                f"  -> 0x{addr:02X}: Escritura completada. Sumada al monitoreo."
            )
            logger.agregar_evento("Escritura de patrón completada con éxito.")

            eeproms_activas[addr] = {
                "logger": logger,
                "mem_size": mem_size,
                "vueltas": 0,
                "errores_totales": 0,
                "errores_reportados": set(),
                "inicio": datetime.now(),
            }

        # ---------------------------------------------------------
        # Manejo de Desconexiones
        # ---------------------------------------------------------
        for addr in desconectadas:
            info = eeproms_activas[addr]
            logger = info["logger"]
            duracion = datetime.now() - info["inicio"]

            print(
                f"\n[{datetime.now().strftime('%H:%M:%S')}] EEPROM"
                f" 0x{addr:02X} desconectada."
            )
            logger.agregar_evento(f"EEPROM DESCONECTADA 0x{addr:02X}")
            logger.agregar_evento(
                f"Resumen final -> Tiempo: {duracion} | Vueltas:"
                f" {info['vueltas']} | SEUs: {info['errores_totales']}"
            )

            # Forzar el guardado inmediato y vaciado hacia la carpeta SUBIDA
            logger.verificar_y_guardar(forzar=True)
            del eeproms_activas[addr]

        # ---------------------------------------------------------
        # Monitoreo Continuo (1 Vuelta completa por memoria activa)
        # ---------------------------------------------------------
        for addr, info in list(eeproms_activas.items()):
            info["vueltas"] += 1
            logger = info["logger"]
            tamano_actual = info["mem_size"]

            for mem_addr in range(0, tamano_actual, CHUNK_READ):
                bloque = read_block_i2c(addr, mem_addr, CHUNK_READ)

                for offset, dato in enumerate(bloque):
                    if dato != PATRON:
                        dir_exacta = mem_addr + offset
                        info["errores_totales"] += 1

                        if dir_exacta not in info["errores_reportados"]:
                            info["errores_reportados"].add(dir_exacta)

                            hora_pantalla = datetime.now().strftime("%H:%M:%S")
                            msg_seu = (
                                f"SEU DETECTADO! Dir: 0x{dir_exacta:04X} |"
                                f" Leído: 0x{dato:02X} | Esperado:"
                                f" 0x{PATRON:02X} | Vuelta #{info['vueltas']}"
                            )
                            print(
                                f"\n[{hora_pantalla}] [ALERT"
                                f" 0x{addr:02X}] {msg_seu}"
                            )
                            logger.agregar_evento(msg_seu)

            temp_cpu = get_cpu_temp()
            hora_pantalla = datetime.now().strftime("%H:%M:%S")
            msg_resumen = (
                f"Vuelta #{info['vueltas']} completa ({tamano_actual // 1024}"
                f" KB) | SEUs acumulados: {info['errores_totales']} | CPU:"
                f" {temp_cpu:.1f}°C"
            )
            print(
                f"\r\033[K[{hora_pantalla}] [INFO 0x{addr:02X}] {msg_resumen}"
            )
            logger.agregar_evento(msg_resumen)

            # Verifica si corresponde rotar los archivos en DATOS / SUBIDA
            logger.verificar_y_guardar()

        time.sleep(PAUSA_ENTRE_VUELTAS)

except KeyboardInterrupt:
    print("\nDeteniendo servicio I2C...")
    for addr, info in eeproms_activas.items():
        info["logger"].agregar_evento("SERVICIO DETENIDO MANUALMENTE")
        info["logger"].verificar_y_guardar(forzar=True)
    print("Archivos en DATOS y SUBIDA sincronizados. Programa finalizado.")