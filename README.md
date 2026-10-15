# infra

Infraestructura compartida del VPS que aloja Paufer, Gast-On y Multas, como código.
Hoy contiene la **monitorización**: saber qué está caído o saturado antes de que lo note un usuario.

## Estado

| Fase | Qué | Estado |
|---|---|---|
| 1 | Métricas del servidor y de los contenedores (node_exporter, cAdvisor) + Prometheus | hecha, probada en local |
| 2 | Sondas HTTP a las URLs públicas y caducidad de certificados (blackbox) | hecha, probada en local (6/6 URLs OK) |
| 3 | Reglas de alerta y avisos a Telegram (Alertmanager) | hecha: envío real y ciclo firing/resolved probados; reglas con tests unitarios |
| 4 | Grafana con dashboard provisionado, tras Traefik | hecha, probada en local (7/7 paneles con datos) |
| 5 | Despliegue en Coolify y medida real de RAM en el VPS | en curso: el primer intento falló (bind mounts) y se corrigió horneando la configuración en las imágenes |
| 6 | CI de este repo (los comandos de "Validar sin arrancar nada") | pendiente |

## Estructura

```
docker-compose.yml          # los servicios; es lo que despliega Coolify
docker-compose.local.yml    # solo para probar en local (9090, 9093 y 3000 en 127.0.0.1)
alertmanager/
├── Dockerfile              # FROM versión fijada + COPY de la configuración
└── alertmanager.yml        # política de avisos: agrupar, repetir, a quién (Telegram)
blackbox/
├── Dockerfile
└── blackbox.yml            # "recetas" de comprobación (qué cuenta como éxito)
grafana/
├── Dockerfile
├── provisioning/
│   ├── datasources/prometheus.yml   # de dónde lee datos (uid fijo: "prometheus")
│   └── dashboards/dashboards.yml    # en qué carpeta busca dashboards
├── dashboards/
│   └── vps.json            # la portada (GENERADO; JSON no admite comentarios: el porqué
│                           #   está en el campo "description" de cada panel)
└── tools/
    └── gen_vps_dashboard.py  # fuente real de vps.json, comentada. Editar aquí y regenerar
prometheus/
├── Dockerfile
├── prometheus.yml          # a quién pregunta Prometheus y cada cuánto
├── rules/
│   └── alerts.yml          # CUÁNDO hay un problema (va dentro de la imagen)
└── tests/
    └── alerts_test.yml     # tests unitarios de las reglas (solo promtool/CI; NO entra en la imagen)
```

`tests/` está fuera de `rules/` a propósito: Prometheus carga todo `rules/*.yml` y tomaría el
fichero de test por reglas. Los `.dockerignore` lo dejan fuera de la imagen, igual que `tools/`.

### Por qué cada servicio lleva su Dockerfile

La configuración **va dentro de la imagen** y no se monta. Medido en el primer despliegue
(2026-10-15): un recurso Docker Compose de Coolify **no deja el repo en la ruta desde la que se
montan los volúmenes**. En el servidor solo había el compose y el `.env` generados por Coolify y
carpetas vacías, y `alertmanager.yml` era un *directorio* (Docker lo crea cuando el origen del
montaje no existe). `build:` sí usa el clon del repo, y por eso funciona (es lo que ya usan
Gast-On y Multas).

Consecuencias: cambiar la configuración exige **reconstruir y redesplegar** (ya no basta con
reiniciar), y en local se arranca con `up -d --build`. A cambio, lo que corre en producción es
exactamente lo que hay en un commit.

## Cómo funciona

```
node_exporter ──┐
 (el servidor)  │
cadvisor ───────┼──►  prometheus ──► alertmanager ──► Telegram
 (contenedores) │     guarda y        agrupa y avisa
blackbox ───────┘     evalúa reglas
 (URLs, por fuera)         └──► grafana ◄── tú, por HTTPS (Traefik)
                                dibuja
```

Prometheus decide **cuándo** hay un problema (`rules/alerts.yml`); Alertmanager decide **qué
hacer con él** (agrupar, no repetir, enviar). Son programas distintos a propósito.

Prometheus **pregunta** cada 30 s a cada exportador y guarda las respuestas con la hora
(modelo *pull*). Los exportadores no necesitan saber que existe, y por eso no hace falta
publicar ningún puerto.

### Qué ve cada pieza

| Pieza | Mira | Configuración por app |
|---|---|---|
| node_exporter | El servidor entero (por dentro) | ninguna |
| cAdvisor | Todos los contenedores Docker (por dentro) | ninguna: descubre los nuevos solo |
| blackbox | Las URLs públicas, como un usuario (por fuera) | una línea por URL en `prometheus.yml` |

Blackbox es la única que detecta lo que ve el usuario (un 503, un certificado caducado, Traefik
mal enrutado); cAdvisor y node_exporter no pueden saber eso. Por eso hacen falta las tres.

### URLs vigiladas

Dos por app (la web y el endpoint de salud del backend): Paufer, Gast-On y Multas. Una app
nueva **no** se vigila sola: hay que añadirla en `prometheus/prometheus.yml`, job `blackbox`.

**Limitación:** blackbox corre en el propio VPS. Si el VPS entero cae, cae con él (y con
Prometheus y Alertmanager), y no prueba que el servidor sea alcanzable desde internet. Se cubre
con un chequeo externo gratuito (UptimeRobot o similar); pendiente.

## Alertas

| Alerta | Cuándo salta | Espera | Por qué |
|---|---|---|---|
| `ServicioCaido` | `probe_success == 0` | 2 min | Un redeploy tira la app ~1 min y es normal; sin la espera, un aviso en cada despliegue |
| `CertificadoPorCaducar` | caduca en < 14 días | 1 h | Traefik renueva a los ~30 d; si a los 14 sigue igual, la renovación falla en silencio |
| `ContenedorEnBucleDeReinicios` | > 2 arranques en 10 min | — | El fallo de Gast-On del 2026-09-25 |
| `MemoriaDisponibleBaja` | `available` < 300 MB | 5 min | Sin swap, el kernel empieza a matar procesos |

Criterio: cada alerta tiene que significar "haz algo". CPU, disco y latencia se añaden cuando
haya datos reales del VPS y se sepa qué es normal; con umbrales a ciegas serían ruido.

## Grafana

Único servicio alcanzable desde internet (`grafana.paufer.es`, por Traefik). Login obligatorio,
sin registro ni acceso anónimo, cookie solo por HTTPS. Lee de Prometheus con `access: proxy`
(las consultas las hace el servidor, por eso Prometheus no se publica).

Todo es código: datasource y dashboard se cargan desde `grafana/` en solo lectura. Lo que se
cambie a mano en la interfaz **se pierde** al reiniciar. El dashboard se **genera**:

```bash
python3 grafana/tools/gen_vps_dashboard.py   # reescribe grafana/dashboards/vps.json
```

Para cambiar un color, un umbral o una consulta se edita el script (cada decisión de diseño
lleva su comentario) y se regenera. Grafana recoge el cambio solo en ~30 s.

### La portada: "VPS · visión general"

Es la página de inicio de Grafana (`GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH`) y viene en modo
oscuro. Diseñada para que lo importante se vea en dos segundos y el detalle exista sin estorbar.
Color con significado: verde / naranja / rojo **solo** para estado.

| Pieza | Consulta | Responde a |
|---|---|---|
| Banner "Estado general" | `min(probe_success)` | ¿Está todo bien? |
| Tarjeta por app (repetida) | `probe_success{app="$app"}` | ¿Web y API de esa app responden? |
| Línea de tiempo | `probe_success` | ¿Cuándo cayó algo y cuánto duró? |
| RAM libre | `MemAvailable / MemTotal` | ¿Cuánto margen queda? (rojo ≈ 300 MB, la alerta) |
| CPU en uso | `1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))` | ¿Está saturado? |
| Disco `/` | `1 - avail / size` | ¿Se llena? (aún sin alerta) |
| Certificado (días) | `min((expiry - time()) / 86400)` | ¿Renovó Traefik? |
| *Detalle (plegado)* | tiempo de respuesta, memoria por contenedor, reinicios | Profundizar cuando una alerta pregunta "por qué" |

La tarjeta de app es **una sola definición repetida** por la variable oculta `app`, que sale de
la etiqueta `app` de las sondas (`prometheus.yml`): una app nueva crea su tarjeta sola.

### Por qué no se copiaron dashboards de la comunidad

Se evaluaron los más usados de grafana.com (Node Exporter Full 1860, Blackbox 16124, cAdvisor
19792) y se descartaron: son ~250 paneles para un VPS con tres apps, ~20 saldrían permanentemente
en "No data", obligaban a cambiar nuestras métricas y etiquetas para encajar con los de otros
(`cluster`, `container_fs_*`) y su licencia no consta. Si un incidente pide el detalle de CPU o
red, se importan en 30 s desde Grafana (*Dashboards → Import → 1860*) sin mantener nada.

**Trampa de la contraseña de admin:** `GRAFANA_ADMIN_PASSWORD` solo se aplica **la primera
vez**, al crear el volumen `grafana_data`. Después vive cifrada dentro de la base de datos y la
variable se ignora: cambiarla en Coolify y redesplegar **no** la cambia. Para cambiarla:

```bash
docker exec <contenedor-grafana> grafana cli admin reset-admin-password '<nueva>'
```

Elegirla bien **antes** del primer despliegue real. El `:?` sigue siendo necesario: garantiza
que el primer arranque nunca sea con `admin/admin`.

## Secretos

Nunca van en el repo. Los dos son obligatorios (`${...:?}` en el compose): si falta alguno, el
despliegue falla en ese momento en vez de arrancar "en verde" con un servicio mudo o abierto.

| Variable | Para qué | Si faltara sin `:?` |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Que Alertmanager pueda enviar mensajes | Arrancaría sin poder avisar de nada |
| `GRAFANA_ADMIN_PASSWORD` | Contraseña del admin de Grafana | Arrancaría con `admin/admin` |
| `GRAFANA_ADMIN_USER` (opcional) | Nombre del admin; `admin` por defecto | — |

En producción son secrets de Coolify; en local se pasan por la terminal y desaparecen con ella.

## Probar en local

```fish
# Los secretos pasan por tu teclado, nunca por un fichero ni por el historial
read -s -x TELEGRAM_BOT_TOKEN
read -s -x GRAFANA_ADMIN_PASSWORD       # en local, una desechable: NO la de producción
# --build es obligatorio tras cambiar configuración: va dentro de la imagen
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
# http://localhost:9090/targets  -> todos en UP
# http://localhost:9090/alerts   -> las 4 reglas, en inactive
# http://localhost:3000          -> Grafana, carpeta Infraestructura > "VPS: visión general"
docker compose -f docker-compose.yml -f docker-compose.local.yml down -v   # -v: borra los volúmenes locales
```

`down -v` es correcto en local (los datos son de usar y tirar y es lo único que fuerza a Grafana
a leer de nuevo la contraseña). **En producción nunca.**

Probar el envío a Telegram sin romper nada, inyectando una alerta falsa en Alertmanager:

```bash
curl -s -X POST http://127.0.0.1:9093/api/v2/alerts -H 'Content-Type: application/json' \
  -d '[{"labels":{"alertname":"PruebaManual","instance":"prueba","severity":"warning"}}]'
# a los ~30 s llega el mensaje; a los 5 min, el de [RESOLVED]
```

## Validar sin arrancar nada

Es lo que ejecutará el CI. Ninguna necesita secretos reales: se pasan valores ficticios.

```bash
TELEGRAM_BOT_TOKEN=ficticio GRAFANA_ADMIN_PASSWORD=ficticio docker compose config -q

# Tests unitarios de las reglas: ¿saltan cuando deben y NO saltan cuando no?
# (tests/ no entra en la imagen, así que se ejecutan desde el fuente)
docker run --rm --entrypoint promtool \
  -v "$PWD/prometheus:/p:ro" \
  prom/prometheus:v3.15.0 test rules /p/tests/alerts_test.yml

# Se validan los ARTEFACTOS: la configuración dentro de las imágenes construidas,
# que es lo que de verdad correrá. Si el COPY de un Dockerfile fallara o apuntara a
# otra ruta, esto lo detecta y validar el fuente no.
docker build -q -t infra-prometheus:ci prometheus
docker run --rm --entrypoint promtool infra-prometheus:ci \
  check config /etc/prometheus/prometheus.yml

docker build -q -t infra-alertmanager:ci alertmanager
docker run --rm --entrypoint sh infra-alertmanager:ci -c \
  'echo x > /tmp/telegram_token && amtool check-config /etc/alertmanager/alertmanager.yml'

docker build -q -t infra-blackbox:ci blackbox
docker run --rm infra-blackbox:ci \
  --config.check --config.file=/etc/blackbox/blackbox.yml
```

Los tests son equivalentes a `pytest` para la monitorización. Se comprobó que tienen dientes:
sabotear una regla (quitar el `for`, subir un umbral) los hace fallar.

## Decisiones y por qué

- **Versiones de imagen fijadas, nunca `latest`.** Un redeploy no debe traer una versión distinta
  sin avisar (así cayó Gast-On el 2026-09-25 con SQLAlchemy 2.1).
- **`mem_limit` en cada servicio.** El VPS tiene 4 GB y no tiene swap: si algo se desboca, que
  muera la monitorización y no el backend de producción.
- **Sin `ports:` en producción.** Los contenedores de un mismo compose se hablan por una red
  interna usando el nombre del servicio y el puerto de escucha del programa. `ports:` solo hace
  falta para abrir algo hacia fuera, y nada de Prometheus debe poder alcanzarse desde internet.
  Grafana es la única excepción y entra por Traefik (labels), sin `ports:`.
- **Configuración de Grafana como código y en solo lectura.** Reproducible desde el repo; el
  precio es que lo cambiado a mano en la interfaz no sobrevive.
- **Grafana 12.4, no la 13.** Medido con la misma configuración y carga: 13.2.4 pesaba 300-320 MB
  (pegada al tope) y 12.4.13 114-118 MB, estable. En un VPS de 4 GB sin swap, 3× más memoria no
  se justifica. 12.4 sigue recibiendo parches. Si se sube a la 13, repetir la medida.
- **Apagado lo que no se usa en Grafana:** su motor de alertas (las evalúa Prometheus) y la
  preinstalación de plugins. Menos memoria y ningún tráfico saliente al arrancar.
- **Medir antes de fijar un tope.** Mi estimación de memoria de Grafana (100-150 MB) falló con la
  13 en un factor 2-3: por eso cada `mem_limit` lleva su medida en un comentario.
- **`docker-compose.local.yml` aparte.** Para no tocar el de producción y que no se pueda
  publicar Prometheus en el VPS por un descuido.

## Avisos

- `docker compose down -v` **borra los volúmenes**: el histórico de métricas (`prometheus_data`),
  lo avisado (`alertmanager_data`) y los usuarios de Grafana (`grafana_data`). Solo en local.
- cAdvisor monta `/var/run` (socket de Docker). El `:ro` no limita lo que se puede ordenar a
  Docker a través del socket: es un riesgo conocido y aceptado (imagen oficial, versión fijada,
  sin exponer). **Nunca publicar su puerto.**
- Los secretos (token del bot de Telegram, contraseña de Grafana) viven en Coolify, nunca en este repo.
- **Antes de hacer público este repo:** `alertmanager/alertmanager.yml` lleva el `chat_id` de
  Telegram en claro (sin el token nadie puede escribir con él, pero es un dato personal), y
  `prometheus.yml` y el compose los subdominios reales. Sacar el `chat_id` a una variable.

## Medido (local, ~2 min tras arrancar, 5-9 contenedores en el host)

| Servicio | RAM | Tope |
|---|---|---|
| grafana 12.4.13 | 114-118 MB (estable bajo carga) | 192 MB |
| prometheus | 79-105 MB | 256 MB |
| cadvisor | 34-47 MB | 128 MB |
| blackbox_exporter | 17-24 MB | 32 MB |
| alertmanager | 15 MB | 48 MB |
| node_exporter | 13-15 MB | 32 MB |
| **Total** | **~280-320 MB** | ~690 MB |

(Grafana 13.2.4 en la misma prueba: 300-320 MB, pegada a un tope de 320.) Pendiente de
confirmar en el VPS, con ~16 contenedores y días de datos: Prometheus crece con el tiempo.

---

# infra (English)

Shared infrastructure for the VPS hosting Paufer, Gast-On and Multas, as code.
Currently holds the **monitoring stack**: Prometheus scraping node_exporter (host), cAdvisor
(containers) and blackbox probes (6 public URLs) every 30 s; alert rules unit-tested with
`promtool`, delivered through Alertmanager to Telegram, with a provisioned Grafana dashboard
(config-as-code, behind Traefik). Next: deploy on Coolify and CI for this repo.

- Image versions are pinned (never `latest`) and every service has a `mem_limit` — the VPS has
  4 GB and no swap.
- No `ports:` in production: containers talk over the compose network by service name.
  `docker-compose.local.yml` publishes Prometheus on `127.0.0.1:9090` for local testing only.
- Secrets live in Coolify, never in this repo. `docker compose down -v` wipes the metrics volume.

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

Configuration is **baked into the images** (one Dockerfile per service): a Coolify Docker
Compose resource does not place the repo at a path usable for file bind mounts, but `build:`
does use the repo clone. Changing config means rebuild + redeploy.
