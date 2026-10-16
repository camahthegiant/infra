# Imagen de Grafana con NUESTRO provisioning y la portada ya dentro.
#
# Mismo motivo que prometheus/Dockerfile: Coolify no permite montar ficheros
# del repo en un recurso Docker Compose, así que la configuración se copia aquí
# dentro. Cambiarla exige reconstruir y redesplegar: un cambio de dashboard
# (se edita gen_vps_dashboard.py, se regenera vps.json) llega con el despliegue,
# ya no se recarga solo cada 30 s desde una carpeta montada.

# Versión FIJADA, nunca "latest". Serie 12.4 a propósito y no la 13: medido con
# la misma configuración y carga, la 13.2.4 pesaba 300-320 MB (pegada al tope
# del contenedor) y la 12.4.13 114-118 MB, estable. Ver docker-compose.yaml.
FROM grafana/grafana:12.4.13

# De dónde lee datos (datasource Prometheus, uid fijo "prometheus") y en qué
# carpeta busca dashboards (provider). Es la ruta que Grafana lee al arrancar.
COPY provisioning/ /etc/grafana/provisioning/

# La portada (vps.json). Tiene que coincidir letra por letra con el "path" de
# provisioning/dashboards/dashboards.yml y con
# GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH del compose; si no, Grafana busca en
# una carpeta vacía y no dice nada.
#
# POR QUÉ /etc/grafana/dashboards Y NO /var/lib/grafana/dashboards
#   /var/lib/grafana es donde el compose monta el volumen grafana_data (la base
#   de datos de Grafana). Un volumen con nombre TAPA lo que la imagen tenga en
#   esa ruta, y Docker solo copia el contenido de la imagen al volumen UNA vez,
#   al crearlo vacío. Con la portada ahí:
#     - en un volumen ya existente (cualquier redeploy; el de producción venía
#       de un primer intento fallido) la carpeta Infraestructura salía VACÍA;
#     - y aunque el volumen fuera nuevo, una portada nueva en una imagen
#       posterior nunca llegaría: el volumen conservaría la copia congelada.
#   Pasó el 2026-10-15; las pruebas locales no lo veían porque siempre
#   empezaban con un volumen vacío (down -v).
#   REGLA: el volumen guarda lo que Grafana ESCRIBE; lo que nosotros le DAMOS va
#   en la imagen, en una ruta que ningún volumen pise.
#   La comprueba scripts/check-no-shadowed-config.sh.
COPY dashboards/ /var/lib/grafana/dashboards/

# Grafana corre como el usuario 472 (heredado de la imagen). Los ficheros
# copiados quedan como root con permisos 644/755: legibles para él, no hace
# falta --chown. No necesita escribir ahí (su base de datos va en el volumen
# grafana_data, en /var/lib/grafana).
