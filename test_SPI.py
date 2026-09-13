import time
import spidev
import RPi.GPIO as GPIO

# Configuración del bus SPI (Bus 0, CE0)
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 2000000  # 2 MHz para pruebas de diagnóstico
spi.mode = 0b00


def esperar_listo():
  """Lee el Status Register 1 (0x05) hasta que el bit BUSY (bit 0) sea 0."""
  while True:
    resp = spi.xfer2([0x05, 0x00])
    if not (resp[1] & 0x01):  # Bit 0 = BUSY
      break
    time.sleep(0.001)


def leer_jedec_id():
  """Lee e interpreta el identificador del fabricante y modelo (0x9F)."""
  resp = spi.xfer2([0x9F, 0x00, 0x00, 0x00])
  mf_id = resp[1]
  type_id = resp[2]
  cap_id = resp[3]

  print(
      f"[JEDEC ID] Fabricante: 0x{mf_id:02X} | Tipo: 0x{type_id:02X} |"
      f" Capacidad: 0x{cap_id:02X}"
  )
  if mf_id == 0xEF and cap_id == 0x17:
    print("  -> Identificada correctamente: Winbond W25Q64 (8 MB / 64 Mbit)")
  elif mf_id in [0x00, 0xFF]:
    print(
        "  -> ERROR GRAVE: Sin comunicación SPI. Revisa VCC, GND, MOSI, MISO y"
        " CLK."
    )
  else:
    print("  -> Chip detectado pero con ID no estándar de Winbond.")


def remover_protecciones_sw():
  """Habilita escritura y limpia los bits de protección de bloque (BP0-BP2) en el Status Register."""
  esperar_listo()
  spi.xfer2([0x06])  # Write Enable (0x06)

  # Escribir 0x00 en Status Register 1 (0x01) para quitar escrituras bloqueadas por SW
  spi.xfer2([0x01, 0x00])
  esperar_listo()
  print("[OK] Protecciones de software removidas del Status Register.")


def borrar_sector_0():
  """Ejecuta Sector Erase (0x20) en el sector 0 (dirección 0x000000 - 4 KB)."""
  esperar_listo()
  spi.xfer2([0x06])  # Write Enable

  # Comando 0x20 + Dirección 24-bit (0x000000)
  print("[INFO] Borrando Sector 0 (0x000000)...")
  spi.xfer2([0x20, 0x00, 0x00, 0x00])
  esperar_listo()
  print("[OK] Sector 0 borrado a 0xFF.")


def probar_escritura_lectura():
  direccion = 0x000000
  patron_prueba = [0xAA] * 256

  # 1. Verificar borrado (debe leer 0xFF)
  lectura_previa = spi.xfer2([0x03, 0x00, 0x00, 0x00] + [0x00] * 256)[4:]
  print(
      f"[TEST BORRADO] Primeros 256 bytes leídos:"
      f" {[hex(b) for b in lectura_previa]}"
  )

  # 2. Habilitar escritura y grabar 256 bytes con Page Program (0x02)
  esperar_listo()
  spi.xfer2([0x06])  # Write Enable

  cmd_write = [0x02, 0x00, 0x00, 0x00] + patron_prueba
  spi.xfer2(cmd_write)
  esperar_listo()
  print(
      f"[INFO] Escritos 256 bytes de 0xAA en la dirección"
      f" 0x{direccion:06X}..."
  )

  # 3. Leer y verificar los 256 bytes
  lectura_posterior = spi.xfer2([0x03, 0x00, 0x00, 0x00] + [0x00] * 256)[4:]
  print(
      f"[TEST LECTURA] Primeros 256 bytes leídos:"
      f" {[hex(b) for b in lectura_posterior]}"
  )

  # 4. Evaluación del test
  if lectura_posterior == patron_prueba:
    print(
        "\n>>> ¡PRUEBA EXITOSA! La W25Q64 borra, escribe y lee perfectamente."
    )
  else:
    print("\n>>> ¡PRUEBA FALLIDA!")
    if all(b == 0xFF for b in lectura_posterior):
      print(
          "  -> Causa probable: El chip está protegido físicamente (/WP en"
          " LOW) o falló el Write Enable."
      )
    elif all(b == 0x00 for b in lectura_posterior):
      print("  -> Causa probable: Cortocircuito en MISO/MOSI o falla de VCC.")


if __name__ == "__main__":
  try:
    print("=== TEST ISLADO W25Q64 ===")
    leer_jedec_id()
    remover_protecciones_sw()
    borrar_sector_0()
    probar_escritura_lectura()
  except KeyboardInterrupt:
    print("\nTest cancelado.")
  finally:
    spi.close()