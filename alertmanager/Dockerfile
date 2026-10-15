# Imagen de Alertmanager con NUESTRA política de avisos ya dentro.
#
# Mismo motivo que prometheus/Dockerfile: Coolify no permite montar ficheros
# del repo en un recurso Docker Compose, así que la configuración se copia aquí
# dentro. Cambiarla exige reconstruir y redesplegar.

# Versión FIJADA, nunca "latest".
FROM prom/alertmanager:v0.34.1

# Política de avisos: agrupar, no repetir de más y enviar a Telegram. Es la
# ruta que lee --config.file en el compose.
#
# EL TOKEN DEL BOT NO VA AQUÍ ni debe ir nunca: una imagen se puede copiar,
# subir a un registro o inspeccionar. alertmanager.yml solo dice "léelo de
# /tmp/telegram_token"; el compose escribe ese fichero al ARRANCAR el
# contenedor, a partir de la variable TELEGRAM_BOT_TOKEN (secret de Coolify).
# Por eso el entrypoint de ese arranque sigue en docker-compose.yml y no aquí.
COPY alertmanager.yml /etc/alertmanager/alertmanager.yml
