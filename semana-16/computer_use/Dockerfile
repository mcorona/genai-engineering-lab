# Disposable desktop for the semana 16 computer use spike (activity 8): Xvfb + Chromium in kiosk mode on the MOV-010
# legacy screen. No credentials and no database inside; it runs with --network none, --read-only and --cap-drop ALL,
# and the model's API calls happen outside it (computer_use/correr.py). The app files are mounted read-only at /app.
#   docker build -t legacy-screen-desktop:1 semana-16/computer_use
FROM python:3.13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends chromium xvfb xdotool imagemagick fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 agente
COPY arrancar.sh /usr/local/bin/arrancar.sh
USER agente
ENV DISPLAY=:1 HOME=/home/agente
ENTRYPOINT ["sh", "/usr/local/bin/arrancar.sh"]
