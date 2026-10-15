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
| 5 | Despliegue en Coolify y medida real de RAM en el VPS | pendiente |
| 6 | CI de este repo (los comandos de "Validar sin arrancar nada") | pendiente |

## Estructura

```
monitoring/
├── docker-compose.yml          # los servicios; es lo que despliega Coolify
├── docker-compose.local.yml    # solo para probar en local (9090, 9093 y 3000 en 127.0.0.1)
├── alertmanager/
│   └── alertmanager.yml        # política de avisos: agrupar, repetir, a quién (Telegram)
├── blackbox/
│   └── blackbox.yml            # "recetas" de comprobación (qué cuenta como éxito)
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/prometheus.yml   # de dónde lee datos (uid fijo: "prometheus")
│   │   └── dashboards/dashboards.yml    # en qué carpeta busca dashboards
│   └── dashboards/
│       └── vps.json            # el dashboard (JSON: sin comentarios; el porqué está en
│                               #   el campo "description" de cada panel)
└── prometheus/
    ├── prometheus.yml          # a quién pregunta Prometheus y cada cuánto
    ├── rules/
    │   └── alerts.yml          # CUÁNDO hay un problema (lo carga Prometheus)
    └── tests/
        └── alerts_test.yml     # tests unitarios de las reglas (solo los ejecuta promtool/CI)
```

`tests/` está fuera de `rules/` a propósito: Prometheus carga todo `rules/*.yml` y tomaría el
fichero de test por reglas. Los tests ni siquiera se montan en el servidor.

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
cambie a mano en la interfaz **se pierde** al reiniciar; el flujo es ajustar un panel en la
interfaz, copiar el JSON al repo y commitearlo.

| Panel | Consulta | Responde a |
|---|---|---|
| Estado de los servicios | `probe_success` | ¿Responden las 6 URLs? |
| Tiempo de respuesta | `probe_duration_seconds` | ¿Va lenta alguna? |
| Días hasta caducar el certificado | `(probe_ssl_earliest_cert_expiry - time()) / 86400` | ¿Renovó Traefik? |
| RAM disponible del VPS | `node_memory_MemAvailable_bytes` | ¿Cuánto margen queda? (línea = 300 MB, la alerta) |
| CPU del VPS | `1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))` | ¿Está saturado? |
| Memoria por contenedor | `container_memory_working_set_bytes{name!=""}` | ¿Quién gasta la RAM? |
| Reinicios por contenedor (1 h) | `changes(container_start_time_seconds{name!=""}[1h])` | ¿Algo en bucle? |

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
cd monitoring
read -s -x TELEGRAM_BOT_TOKEN
read -s -x GRAFANA_ADMIN_PASSWORD       # en local, una desechable: NO la de producción
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
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
cd monitoring
TELEGRAM_BOT_TOKEN=ficticio GRAFANA_ADMIN_PASSWORD=ficticio docker compose config -q

# Sintaxis de la configuración y de las reglas
docker run --rm --entrypoint promtool \
  -v "$PWD/prometheus:/etc/prometheus:ro" \
  prom/prometheus:v3.15.0 check config /etc/prometheus/prometheus.yml

# Tests unitarios de las reglas: ¿saltan cuando deben y NO saltan cuando no?
docker run --rm --entrypoint promtool \
  -v "$PWD/prometheus:/p:ro" \
  prom/prometheus:v3.15.0 test rules /p/tests/alerts_test.yml

# Configuración de Alertmanager
docker run --rm --entrypoint sh \
  -v "$PWD/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro" \
  prom/alertmanager:v0.34.1 -c \
  'echo x > /tmp/telegram_token && amtool check-config /etc/alertmanager/alertmanager.yml'
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
- **`docker-compose.local.yml` aparte.** Para no tocar el de producción y que no se pueda
  publicar Prometheus en el VPS por un descuido.

## Avisos

- `docker compose down -v` **borra los volúmenes**: el histórico de métricas (`prometheus_data`),
  lo avisado (`alertmanager_data`) y los usuarios de Grafana (`grafana_data`). Solo en local.
- cAdvisor monta `/var/run` (socket de Docker). El `:ro` no limita lo que se puede ordenar a
  Docker a través del socket: es un riesgo conocido y aceptado (imagen oficial, versión fijada,
  sin exponer). **Nunca publicar su puerto.**
- Los secretos (token del bot de Telegram, contraseña de Grafana) viven en Coolify, nunca en este repo.

## Medido (local, ~2 min tras arrancar, 5-9 contenedores en el host)

| Servicio | RAM | Tope |
|---|---|---|
| grafana | 141 MB | 256 MB (subido desde 192 al medir: dejaba ~50 MB de margen) |
| prometheus | 79 MB | 256 MB |
| cadvisor | 34 MB | 128 MB |
| blackbox_exporter | 17 MB | 32 MB |
| alertmanager | 16 MB | 48 MB |
| node_exporter | 13 MB | 32 MB |
| **Total** | **~300 MB** | ~750 MB |

Pendiente de confirmar en el VPS, con ~16 contenedores y días de datos: Prometheus crece con el
tiempo y Grafana con el uso.

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
cd monitoring
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```
