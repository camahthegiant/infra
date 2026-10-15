# Imagen de Prometheus con NUESTRA configuración ya dentro.
#
# POR QUÉ UNA IMAGEN PROPIA Y NO MONTAR LOS FICHEROS
#   Un recurso Docker Compose de Coolify no deja el repo en una ruta desde la
#   que se puedan montar ficheros: los bind mounts (./prometheus/prometheus.yml)
#   apuntan a carpetas vacías y el contenedor no arranca ("not a directory").
#   Lo que SÍ funciona es "build:", cuyo contexto sale del clon del repo. Por
#   eso la configuración se copia aquí dentro en tiempo de construcción.
#
# CONSECUENCIA
#   Cambiar prometheus.yml o las reglas exige reconstruir y redesplegar; ya no
#   basta con reiniciar el contenedor. Es una ventaja: lo que corre en
#   producción es exactamente lo que hay en un commit, no "un fichero que
#   alguien editó en el servidor".

# Versión FIJADA, nunca "latest": un redeploy no debe traer una versión
# distinta sin avisar (así cayó Gast-On el 2026-09-25 con SQLAlchemy 2.1).
FROM prom/prometheus:v3.15.0

# A quién pregunta Prometheus y cada cuánto. Es la ruta que lee --config.file.
COPY prometheus.yml /etc/prometheus/prometheus.yml

# CUÁNDO hay un problema: las reglas de alerta. Es la carpeta a la que apunta
# rule_files de prometheus.yml (/etc/prometheus/rules/*.yml).
# tests/ NO se copia a propósito (ver .dockerignore): son material de
# desarrollo y Prometheus tomaría el fichero de test por reglas.
COPY rules/ /etc/prometheus/rules/

# El usuario, el puerto (9090) y el comando de arranque los hereda de la imagen
# oficial: no hace falta repetirlos.
