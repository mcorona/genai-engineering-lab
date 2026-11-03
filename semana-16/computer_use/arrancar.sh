#!/bin/sh
# Starts the display, the legacy screen (from the read-only snapshot in /app) and Chromium in kiosk mode.
set -e
Xvfb :1 -screen 0 1280x800x24 -nolisten tcp >/dev/null 2>&1 &
python3 /app/pantalla.py --puerto 8716 --datos /app/datos.json --bitacora /tmp/solicitudes.jsonl \
  --canario "$CANARIO" >/dev/null 2>&1 &
sleep 2
cd /app
exec chromium $(python3 -c 'import entorno; print(" ".join(entorno.argumentos_chromium("/home/agente/perfil")))') \
  >/dev/null 2>&1
