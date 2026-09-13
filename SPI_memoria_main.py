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
    obtener_capacidad_spi,
    chip_erase_spi,
    write_page_spi,
    read_block_spi,
    get_cpu_temp,
    BufferLoggerSPI
)

PATRON = 0xAA
CHUNK_PAGE = 128   # Escritura en bloques de 128 bytes
CHUNK_READ = 128   # Lectura de monitoreo en bloques de 128 bytes
PAUSA_ENTRE_VUELTAS = 1  # Pausa breve para permitir intercalar escaneo dinámico

memorias_activas = {}

print("=== INICIANDO SERVICIO MONITOREO MEMORIAS SPI CONTINUO ===")

try:
    while True:
        # 1. Escaneo dinámico de puertos
        hora_act = datetime.now().strftime("%H:%M:%S")
        print(f"\r\033[K[{hora_act}] Monitoreando bus SPI (Activas: {list(memorias_activas.keys())})...", end="", flush=True)

        detectadas = set(buscar_memorias_spi())
        conocidas = set(memorias_activas.keys())

        nuevas = detectadas - conocidas
        desconectadas = conocidas - detectadas

        # 2. Inicializar canales nuevos (ej. Si conectas CS1 en caliente)
        for dev_id in nuevas:
            print()
            tamano_memoria = obtener_capacidad_spi(dev_id)
            mb_size = tamano_memoria / (1024 * 1024)

            print(f"[{datetime.now().strftime('%H:%M:%S')}] ¡NUEVA MEMORIA DETECTADA! Canal CS{dev_id} | Tamaño: {mb_size:.2f} MB")

            logger = BufferLoggerSPI(device_id=dev_id, intervalo_minutos=2)
            logger.agregar_evento(f"MEMORIA SPI CONECTADA CANAL CS{dev_id} | CAPACIDAD: {tamano_memoria} BYTES")

            print(f"  -> CS{dev_id}: Borrando memoria (Chip Erase)...")
            chip_erase_spi(dev_id)

            print(f"  -> CS{dev_id}: Cargando patrón 0xAA...")
            patron_bloque = [PATRON] * CHUNK_PAGE
            for mem_addr in range(0, tamano_memoria, CHUNK_PAGE):
                write_page_spi(dev_id, mem_addr, patron_bloque)

                if mem_addr > 0 and (mem_addr % (1024 * 1024) == 0):
                    progreso_mb = mem_addr / (1024 * 1024)
                    print(f"  -> CS{dev_id}: Escritos {progreso_mb:.1f} / {mb_size:.1f} MB")

            print(f"  -> CS{dev_id}: Inicialización completa. Sumado a monitoreo.")
            logger.agregar_evento("Inicialización completada.")

            memorias_activas[dev_id] = {
                "logger": logger,
                "tamano": tamano_memoria,
                "vueltas": 0,
                "errores_totales": 0,
                "errores_reportados": set(),
                "inicio": datetime.now(),
            }

        # 3. Remover memorias que se desconectaron
        for dev_id in desconectadas:
            info = memorias_activas[dev_id]
            logger = info["logger"]
            duracion = datetime.now() - info["inicio"]

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Memoria SPI CS{dev_id} desconectada.")
            logger.agregar_evento(f"MEMORIA DESCONECTADA CANAL CS{dev_id} | Tiempo: {duracion}")
            logger.verificar_y_guardar(forzar=True)
            del memorias_activas[dev_id]

        # 4. Monitoreo pasante: Realiza 1 vuelta completa en TODAS las memorias activas
        for dev_id, info in list(memorias_activas.items()):
            info["vueltas"] += 1
            logger = info["logger"]
            tamano_memoria = info["tamano"]

            for mem_addr in range(0, tamano_memoria, CHUNK_READ):
                bloque = read_block_spi(dev_id, mem_addr, CHUNK_READ)

                for offset, dato in enumerate(bloque):
                    if dato != PATRON:
                        dir_exacta = mem_addr + offset
                        info["errores_totales"] += 1

                        if dir_exacta not in info["errores_reportados"]:
                            info["errores_reportados"].add(dir_exacta)

                            hora_pantalla = datetime.now().strftime("%H:%M:%S")
                            msg_seu = f"SEU DETECTADO! Dir: 0x{dir_exacta:06X} | Leido: 0x{dato:02X} | Esperado: 0x{PATRON:02X} | Vuelta #{info['vueltas']}"
                            print(f"\n[{hora_pantalla}] [ALERT CS{dev_id}] {msg_seu}")
                            logger.agregar_evento(msg_seu)

            temp_cpu = get_cpu_temp()
            hora_pantalla = datetime.now().strftime("%H:%M:%S")
            msg_resumen = f"Vuelta #{info['vueltas']} completa ({tamano_memoria / (1024*1024):.1f} MB) | SEUs: {info['errores_totales']} | CPU: {temp_cpu:.1f}°C"
            
            # Imprime el resumen con un salto de línea limpio para que QUEDE en el historial
            print(f"\r\033[K[{hora_pantalla}] [INFO CS{dev_id}] {msg_resumen}\n")
            logger.agregar_evento(msg_resumen)

            logger.verificar_y_guardar()

        time.sleep(PAUSA_ENTRE_VUELTAS)

except KeyboardInterrupt:
    print("\nDeteniendo servicio SPI...")
    for dev_id, info in memorias_activas.items():
        info["logger"].agregar_evento("SERVICIO DETENIDO MANUALMENTE")
        info["logger"].verificar_y_guardar(forzar=True)
    print("Buffer guardado y programa finalizado.")