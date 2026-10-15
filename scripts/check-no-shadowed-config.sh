#!/usr/bin/env bash
# Comprueba que la configuración horneada en la imagen de Grafana SOBREVIVE a
# un volumen que ya existía.
#
# EL FALLO QUE CAZA (2026-10-15, primer despliegue real)
#   La portada se copiaba a /var/lib/grafana/dashboards, y /var/lib/grafana es
#   donde se monta el volumen grafana_data. Un volumen con nombre TAPA lo que la
#   imagen tenga en esa ruta, y Docker solo copia el contenido de la imagen al
#   volumen UNA vez, al crearlo vacío. En producción el volumen ya existía (con
#   grafana.db): la carpeta "Infraestructura" salió vacía. En local nadie lo
#   vio porque las pruebas empezaban siempre de cero (down -v).
#
# QUÉ HACE
#   Construye la imagen, crea un volumen que YA CONTIENE algo (como el de
#   producción), lo monta donde lo monta el compose y comprueba que la ruta de
#   dashboards que lee el provider sigue conteniendo la portada.
#   La ruta se LEE del propio dashboards.yml de la imagen, así que el test no
#   depende de una ruta escrita aquí: si alguien la mueve bajo el volumen, falla.
#
# USO
#   scripts/check-no-shadowed-config.sh        # devuelve 0 si pasa, 1 si falla
#
# Regla que protege: el volumen guarda lo que Grafana ESCRIBE (su base de
# datos); lo que nosotros le DAMOS va en la imagen, en una ruta que ningún
# volumen pise.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGEN="infra-grafana:check-$$"
VOLUMEN="infra-check-gf-$$"

# Se limpia siempre, pase o falle.
limpiar() {
  docker volume rm -f "$VOLUMEN" >/dev/null 2>&1 || true
  docker rmi -f "$IMAGEN" >/dev/null 2>&1 || true
}
trap limpiar EXIT

docker build -q -t "$IMAGEN" "$RAIZ/grafana" >/dev/null

# Un volumen que ya tiene contenido, como el de producción tras el primer
# arranque. Si estuviera vacío, Docker copiaría la imagen al crearlo y el fallo
# no se vería (es justo lo que pasaba en las pruebas locales).
docker volume create "$VOLUMEN" >/dev/null
docker run --rm -v "$VOLUMEN:/data" alpine sh -c 'touch /data/grafana.db'

# Mismo punto de montaje que el compose (grafana_data:/var/lib/grafana).
docker run --rm -v "$VOLUMEN:/var/lib/grafana" --entrypoint sh "$IMAGEN" -c '
  CONF=/etc/grafana/provisioning/dashboards/dashboards.yml
  RUTA=$(sed -n "s/^ *path: *//p" "$CONF" | head -1)
  if [ -z "$RUTA" ]; then echo "FALLA: no se encontró options.path en $CONF"; exit 1; fi
  if ls "$RUTA"/*.json >/dev/null 2>&1; then
    echo "OK: el provider lee $RUTA y la portada está ahí ($(ls "$RUTA" | tr "\n" " "))"
  else
    echo "FALLA: el provider lee $RUTA, pero con el volumen montado no hay ningún dashboard."
    echo "       Esa ruta está bajo el punto de montaje del volumen y queda tapada."
    exit 1
  fi
'
