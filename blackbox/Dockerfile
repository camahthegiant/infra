# Imagen de blackbox_exporter con NUESTRAS recetas de comprobación dentro.
#
# Mismo motivo que prometheus/Dockerfile: Coolify no permite montar ficheros
# del repo en un recurso Docker Compose, así que la configuración se copia aquí
# dentro. Cambiarla exige reconstruir y redesplegar.

# Versión FIJADA, nunca "latest". Es la misma con la que se validó
# blackbox.yml (--config.check): validar con una y desplegar otra anularía la
# comprobación.
FROM prom/blackbox-exporter:v0.29.0

# Los "módulos" (http_2xx: sigue redirecciones, exige HTTPS, IPv4, timeout
# 10 s). Es la ruta que lee --config.file en el compose.
#
# OJO: si esta línea faltara o la ruta no coincidiera con --config.file,
# blackbox NO fallaría: usaría los módulos por defecto de la imagen y nuestras
# decisiones (fail_if_not_ssl, ip4...) se ignorarían en silencio.
COPY blackbox.yml /etc/blackbox/blackbox.yml
