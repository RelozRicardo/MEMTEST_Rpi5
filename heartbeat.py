#http://cifedegss.mooo.com:8890/lab_server/heartbeat.php

import requests
import time

url = "http://cifedegss.mooo.com:8890/lab_server/heartbeat.php"

data = {
    "device": "RPi5",
}

while True:
    try:
        response = requests.post(
            url,
            data=data,
            timeout=5
        )

        print("Código HTTP:", response.status_code)
        print("Respuesta:", response.text)

        if response.status_code == 200 and response.text.strip() == "OK":
            print("El servidor respondió correctamente.")
        else:
            print("El servidor devolvió un error.")

    except requests.exceptions.RequestException as e:
        print("Error al conectar con el servidor:")
        print(e)

    print("Esperando 45 segundos...\n")
    time.sleep(45)
    
# CREAR ARCHIVO
# sudo nano /etc/systemd/system/heartbeat.service

# 1. Recargar el demonio de systemd para detectar el nuevo servicio
# sudo systemctl daemon-reload

# 2. Habilitar el servicio para que inicie automáticamente al arrancar
# sudo systemctl enable heartbeat.service

# 3. Iniciar el servicio inmediatamente
# sudo systemctl start heartbeat.service

# 4. Verificar el estado del servicio
# sudo systemctl status heartbeat.service

# 5. Ver los prints del servicio
# journalctl -u heartbeat.service -f -o cat

# 6. Para detener REINICIAR el servicio
# sudo systemctl stop heartbeat.service
# sudo systemctl restart heartbeat.service