# infra

Infraestructura compartida del VPS que aloja Paufer, Gast-On y Multas, como código.
Hoy contiene la **monitorización**: saber qué está caído o saturado antes de que lo note un usuario.

## Estado

| Fase | Qué | Estado |
|---|---|---|
| 1 | Métricas del servidor y de los contenedores (node_exporter, cAdvisor) + Prometheus | hecha, probada en local |
| 2 | Sondas HTTP a las URLs públicas y caducidad de certificados (blackbox) | pendiente |
| 3 | Alertas a Telegram (Alertmanager) | pendiente |
| 4 | Grafana con dashboards, tras Traefik | pendiente |

## Estructura

```
monitoring/
├── docker-compose.yml          # los servicios; es lo que despliega Coolify
├── docker-compose.local.yml    # solo para probar en local (publica el 9090)
└── prometheus/
    └── prometheus.yml          # a quién pregunta Prometheus y cada cuánto
```

## Cómo funciona

```
node_exporter ──┐
 (el servidor)  │
cadvisor ───────┼──►  prometheus  ──►  (grafana, alertmanager: fases 3-4)
 (contenedores) │     guarda y evalúa
```

Prometheus **pregunta** cada 30 s a cada exportador y guarda las respuestas con la hora
(modelo *pull*). Los exportadores no necesitan saber que existe, y por eso no hace falta
publicar ningún puerto.

## Probar en local

```bash
cd monitoring
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
# http://localhost:9090/targets -> prometheus, node y cadvisor en UP
docker compose -f docker-compose.yml -f docker-compose.local.yml down
```

Validar la configuración sin arrancar nada:

```bash
docker compose config -q
docker run --rm --entrypoint promtool \
  -v "$PWD/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  prom/prometheus:v3.15.0 check config /etc/prometheus/prometheus.yml
```

## Decisiones y por qué

- **Versiones de imagen fijadas, nunca `latest`.** Un redeploy no debe traer una versión distinta
  sin avisar (así cayó Gast-On el 2026-09-25 con SQLAlchemy 2.1).
- **`mem_limit` en cada servicio.** El VPS tiene 4 GB y no tiene swap: si algo se desboca, que
  muera la monitorización y no el backend de producción.
- **Sin `ports:` en producción.** Los contenedores de un mismo compose se hablan por una red
  interna usando el nombre del servicio y el puerto de escucha del programa. `ports:` solo hace
  falta para abrir algo hacia fuera, y nada de Prometheus debe poder alcanzarse desde internet.
  Grafana será la única excepción (fase 4) y entrará por Traefik.
- **`docker-compose.local.yml` aparte.** Para no tocar el de producción y que no se pueda
  publicar Prometheus en el VPS por un descuido.

## Avisos

- `docker compose down -v` **borra el volumen `prometheus_data`** y con él el histórico.
- cAdvisor monta `/var/run` (socket de Docker). El `:ro` no limita lo que se puede ordenar a
  Docker a través del socket: es un riesgo conocido y aceptado (imagen oficial, versión fijada,
  sin exponer). **Nunca publicar su puerto.**
- Los secretos (token del bot de Telegram, contraseña de Grafana) viven en Coolify, nunca en este repo.

## Medido (local, recién arrancado, 5 contenedores)

| Servicio | RAM | Tope |
|---|---|---|
| node_exporter | 20 MB | 32 MB |
| prometheus | 40 MB | 256 MB |
| cadvisor | 50 MB | 128 MB |

Pendiente de confirmar en el VPS, con ~16 contenedores y días de datos.

---

# infra (English)

Shared infrastructure for the VPS hosting Paufer, Gast-On and Multas, as code.
Currently holds the **monitoring stack**: Prometheus scraping node_exporter (host) and
cAdvisor (containers) every 30 s; blackbox probes, Alertmanager (Telegram) and Grafana follow.

- Image versions are pinned (never `latest`) and every service has a `mem_limit` — the VPS has
  4 GB and no swap.
- No `ports:` in production: containers talk over the compose network by service name.
  `docker-compose.local.yml` publishes Prometheus on `127.0.0.1:9090` for local testing only.
- Secrets live in Coolify, never in this repo. `docker compose down -v` wipes the metrics volume.

```bash
cd monitoring
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```
