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
    reset_memoria_spi,
    get_cpu_temp,
    BufferLoggerSPI
)

PATRON = 0xAA
CHUNK_PAGE = 128   # Escritura en bloques de 128 bytes
CHUNK_READ = 128   # Lectura de monitoreo en bloques de 128 bytes
PAUSA_ENTRE_VUELTAS = 1  # Pausa breve para permitir intercalar escaneo dinámico

memorias_activas = {}

# =========================================================
# INICIALIZACIÓN Y SEGURIDAD AL ARRANQUE
# =========================================================
print("=== INICIANDO SERVICIO MONITOREO MEMORIAS SPI CONTINUO ===")

# Pausa de seguridad para estabilización de fuente en frío
print("[BOOT] Esperando estabilización de alimentación del sistema (3s)...")
time.sleep(3)

# Forzar Reset por Software de la memoria
try:
    reset_memoria_spi(0)
    print("[BOOT] Comando de Reset enviado exitosamente a la memoria CS0.")
except Exception as e:
    print(f"[BOOT] Advertencia al enviar Reset SPI: {e}")

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

            # ---------------------------------------------------------
            # Cargar patrón 0xAA con reporte por porcentaje (cada 10%)
            # ---------------------------------------------------------
            print(f"  -> CS{dev_id}: Cargando patrón 0xAA...")
            patron_bloque = [PATRON] * CHUNK_PAGE
            paso_porcentaje = 10  # Imprimir cada 10%
            siguiente_umbral = paso_porcentaje

            for mem_addr in range(0, tamano_memoria, CHUNK_PAGE):
                write_page_spi(dev_id, mem_addr, patron_bloque)

                # Calcular porcentaje actual
                porcentaje = (mem_addr + CHUNK_PAGE) * 100 / tamano_memoria

                if porcentaje >= siguiente_umbral or mem_addr + CHUNK_PAGE >= tamano_memoria:
                    hora_act = datetime.now().strftime("%H:%M:%S")
                    progreso_mb = (mem_addr + CHUNK_PAGE) / (1024 * 1024)
                    print(
                        f"[{hora_act}]   -> CS{dev_id}: Escritos"
                        f" {progreso_mb:.2f}/{mb_size:.2f} MB ({porcentaje:.0f}%)"
                    )
                    siguiente_umbral += paso_porcentaje

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
         # ---------------------------------------------------------
        # Monitoreo pasante con reportes parciales de avance
        # ---------------------------------------------------------
        for dev_id, info in list(memorias_activas.items()):
            info["vueltas"] += 1
            logger = info["logger"]
            tamano_memoria = info["tamano"]

            # Reportar progreso cada 512 KB (524288 bytes)
            TRAMO_BYTES = 512 * 1024
            siguiente_reporte = TRAMO_BYTES

            for mem_addr in range(0, tamano_memoria, CHUNK_READ):
                bloque = read_block_spi(dev_id, mem_addr, CHUNK_READ)

                for offset, dato in enumerate(bloque):
                    if dato != PATRON:
                        dir_exacta = mem_addr + offset
                        info["errores_totales"] += 1

                        if dir_exacta not in info["errores_reportados"]:
                            info["errores_reportados"].add(dir_exacta)

                            hora_pantalla = datetime.now().strftime("%H:%M:%S")
                            msg_seu = (
                                f"SEU DETECTADO! Dir: 0x{dir_exacta:06X} | Leido: 0x{dato:02X} |"
                                f" Esperado: 0x{PATRON:02X} | Vuelta #{info['vueltas']}"
                            )
                            print(f"\n[{hora_pantalla}] [ALERT CS{dev_id}] {msg_seu}")
                            logger.agregar_evento(msg_seu)

                # Imprimir avance parcial cada 512 KB o al finalizar la memoria
                if (
                    mem_addr + CHUNK_READ >= siguiente_reporte
                    or mem_addr + CHUNK_READ >= tamano_memoria
                ):
                    porcentaje_lectura = (
                        (mem_addr + CHUNK_READ) * 100 / tamano_memoria
                    )
                    temp_cpu = get_cpu_temp()
                    hora_pantalla = datetime.now().strftime("%H:%M:%S")

                    msg_progreso = (
                        f"CS{dev_id} | Vuelta #{info['vueltas']} | Progreso:"
                        f" {porcentaje_lectura:.0f}% | SEUs Acumulados:"
                        f" {info['errores_totales']} | CPU: {temp_cpu:.1f}°C"
                    )

                    # Actualizar línea en vivo en la terminal
                    print(f"\r\033[K[{hora_pantalla}] [READ CS{dev_id}] {msg_progreso}", end="", flush=True)

                    siguiente_reporte += TRAMO_BYTES

                # Al terminar la vuelta completa se hace un salto de línea limpio
                print()
                logger.agregar_evento(
                    f"Vuelta #{info['vueltas']} completada. Total SEUs:"
                    f" {info['errores_totales']}"
                )
                logger.verificar_y_guardar()
        time.sleep(PAUSA_ENTRE_VUELTAS)

except KeyboardInterrupt:
    print("\nDeteniendo servicio SPI...")
    for dev_id, info in memorias_activas.items():
        info["logger"].agregar_evento("SERVICIO DETENIDO MANUALMENTE")
        info["logger"].verificar_y_guardar(forzar=True)
    print("Buffer guardado y programa finalizado.")