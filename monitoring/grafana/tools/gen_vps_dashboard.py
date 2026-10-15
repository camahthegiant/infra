#!/usr/bin/env python3
"""Genera grafana/dashboards/vps.json: la portada "VPS · visión general".

POR QUÉ UN GENERADOR Y NO EL JSON A MANO
  Un dashboard de Grafana son cientos de líneas de JSON, y JSON no admite
  comentarios: a mano no se puede mantener ni explicar. Aquí cada decisión de
  diseño lleva su comentario, y para cambiar un color o un umbral se edita este
  fichero y se regenera. El que consume Grafana es el vps.json resultante; este
  script es su fuente.

USO (desde cualquier carpeta; no necesita dependencias):
  python3 monitoring/grafana/tools/gen_vps_dashboard.py

  Reescribe monitoring/grafana/dashboards/vps.json. Grafana lo recoge solo en
  unos 30 s (updateIntervalSeconds de provisioning/dashboards/dashboards.yml).

CRITERIO DE DISEÑO
  Lo importante se ve en dos segundos; el detalle existe pero no estorba.
    1. Banner: ¿está todo bien? (lo único que se mira el 99 % de las veces)
    2. Una tarjeta por app: web y API, en verde o rojo.
    3. Línea de tiempo: cuándo cayó algo y cuánto duró.
    4. Cuatro indicadores de recursos.
    5. Detalle plegado: tiempos, memoria por contenedor, reinicios.
  Color con significado: verde / naranja / rojo SOLO para estado. Las series de
  datos van en tonos neutros para que lo rojo destaque de verdad.
"""
import json
from pathlib import Path

# Mismo uid fijo que grafana/provisioning/datasources/prometheus.yml. Si no
# coincide, los paneles salen con "datasource not found".
DS = {"type": "prometheus", "uid": "prometheus"}

VERDE, NARANJA, ROJO = "green", "orange", "red"


def target(expr, legend="", instant=False, ref="A"):
    """Una consulta PromQL. instant=True para valores sueltos (stat, gauge)."""
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref}
    if instant:
        t.update({"instant": True, "range": False})
    return t


def thresholds(*steps):
    """steps: (color, valor). El primero lleva valor None (base)."""
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for c, v in steps]}


# OK / CAÍDO para probe_success (1 = la sonda funciona, 0 = falla).
def mapeo_estado(ok="OK", caido="CAÍDO"):
    return [{"type": "value", "options": {
        "0": {"text": caido, "color": ROJO, "index": 1},
        "1": {"text": ok, "color": VERDE, "index": 0},
    }}]


def reducer():
    return {"calcs": ["lastNotNull"], "fields": "", "values": False}


# --- Piezas --------------------------------------------------------------- #

def banner(pid):
    # min() de todas las sondas: basta que UNA falle para que valga 0.
    return {
        "id": pid, "type": "stat", "title": "Estado general",
        "description": "Resumen de las 6 sondas HTTP (web y API de las tres apps). Verde = todas "
                       "responden; rojo = al menos una falla. Una caída corta (un redeploy dura ~1 min) "
                       "se ve rojo aquí pero NO avisa: la alerta ServicioCaido espera 2 minutos seguidos.",
        "gridPos": {"x": 0, "y": 0, "w": 24, "h": 3}, "datasource": DS,
        "targets": [target("min(probe_success)", instant=True)],
        "fieldConfig": {"defaults": {
            "mappings": mapeo_estado("● TODO OK", "● HAY SERVICIOS CAÍDOS"),
            "thresholds": thresholds((ROJO, None), (VERDE, 1)),
            "color": {"mode": "thresholds"}}, "overrides": []},
        "options": {"colorMode": "background", "graphMode": "none", "textMode": "value",
                    "justifyMode": "center", "reduceOptions": reducer()},
    }


def tarjeta_app(pid):
    # UNA definición, repetida por la variable oculta "app" (repeat): añadir una
    # app en prometheus.yml crea su tarjeta sola, sin tocar este fichero.
    # El título "$app" lo sustituye Grafana por paufer / gaston / multas.
    return {
        "id": pid, "type": "stat", "title": "$app",
        "description": "Web y API de esta app, vistas como las ve un usuario (blackbox, cada 30 s). "
                       "Las tarjetas salen de la etiqueta app de las sondas (prometheus.yml).",
        "repeat": "app", "repeatDirection": "h", "maxPerRow": 4,
        "gridPos": {"x": 0, "y": 3, "w": 8, "h": 5}, "datasource": DS,
        "targets": [target('probe_success{app="$app"}', "{{tier}}", instant=True)],
        "fieldConfig": {"defaults": {
            "mappings": mapeo_estado(),
            "thresholds": thresholds((ROJO, None), (VERDE, 1)),
            "color": {"mode": "thresholds"}}, "overrides": []},
        "options": {"colorMode": "background", "graphMode": "none", "textMode": "value_and_name",
                    "justifyMode": "center", "orientation": "horizontal",
                    "reduceOptions": reducer()},
    }


def linea_tiempo(pid):
    return {
        "id": pid, "type": "state-timeline", "title": "Estado, última ventana de tiempo",
        "description": "Cada fila es una sonda; verde = responde, rojo = falla. Sirve para ver de un "
                       "vistazo CUÁNDO cayó algo y CUÁNTO duró, cosa que un número suelto no dice. Un "
                       "corte de ~1 minuto coincide con un despliegue.",
        "gridPos": {"x": 0, "y": 8, "w": 24, "h": 7}, "datasource": DS,
        "targets": [target("probe_success", "{{app}} · {{tier}}")],
        "fieldConfig": {"defaults": {
            "mappings": mapeo_estado(),
            "thresholds": thresholds((ROJO, None), (VERDE, 1)),
            "color": {"mode": "thresholds"},
            "custom": {"fillOpacity": 85, "lineWidth": 0}}, "overrides": []},
        "options": {"mergeValues": True, "showValue": "never", "rowHeight": 0.8,
                    "alignValue": "center", "legend": {"showLegend": False},
                    "tooltip": {"mode": "single"}},
    }


def indicador(pid, x, titulo, desc, expr, unidad, th, vmin=0, vmax=1, decimales=0):
    """Un gauge de 6 de ancho. Cuatro indicadores = 24 columnas."""
    return {
        "id": pid, "type": "gauge", "title": titulo, "description": desc,
        "gridPos": {"x": x, "y": 15, "w": 6, "h": 5}, "datasource": DS,
        "targets": [target(expr, instant=True)],
        "fieldConfig": {"defaults": {
            "unit": unidad, "min": vmin, "max": vmax, "decimals": decimales,
            "thresholds": th, "color": {"mode": "thresholds"}}, "overrides": []},
        "options": {"showThresholdMarkers": True, "showThresholdLabels": False,
                    "reduceOptions": reducer()},
    }


def serie(pid, titulo, desc, x, y, w, h, expr, leyenda, unidad, vmin=0, apilada=False):
    # Estilo común: línea suave, relleno ligero y sin puntos. Paleta clásica de
    # Grafana para distinguir series; el rojo/verde se reserva para estado.
    custom = {"lineInterpolation": "smooth", "lineWidth": 2, "fillOpacity": 10,
              "gradientMode": "opacity", "showPoints": "never"}
    if apilada:
        custom["stacking"] = {"mode": "normal", "group": "A"}
    return {
        "id": pid, "type": "timeseries", "title": titulo, "description": desc,
        "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": DS,
        "targets": [target(expr, leyenda)],
        "fieldConfig": {"defaults": {"unit": unidad, "min": vmin,
                                     "color": {"mode": "palette-classic"}, "custom": custom},
                        "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }


def reinicios(pid, x, y, w, h):
    return {
        "id": pid, "type": "stat", "title": "Reinicios por contenedor (última hora)",
        "description": "Cuántas veces ha arrancado cada contenedor en la última hora. 0 es lo sano. Un "
                       "redeploy crea contenedores con nombre nuevo, así que no cuenta. 3 o más en 10 min "
                       "es el bucle de reinicios de Gast-On del 2026-09-25 (alerta "
                       "ContenedorEnBucleDeReinicios).",
        "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": DS,
        "targets": [target('changes(container_start_time_seconds{name!=""}[1h])', "{{name}}", instant=True)],
        "fieldConfig": {"defaults": {
            "unit": "none", "thresholds": thresholds((VERDE, None), (NARANJA, 1), (ROJO, 3)),
            "color": {"mode": "thresholds"}}, "overrides": []},
        "options": {"colorMode": "background", "graphMode": "none", "textMode": "value_and_name",
                    "justifyMode": "center", "reduceOptions": reducer()},
    }


def main():
    # Indicadores de recursos. Los umbrales de color replican los de las alertas
    # donde las hay (RAM 300 MB ≈ 8 % de los 3819 MB del VPS) y son orientativos
    # donde no (CPU, disco): se afinarán con datos reales del VPS.
    indicadores = [
        indicador(
            4, 0, "RAM libre",
            "RAM realmente aprovechable (MemAvailable: cuenta la caché que el kernel puede soltar, no "
            "solo la 'libre') sobre el total. El VPS no tiene swap: al agotarse, el kernel mata "
            "procesos. Rojo por debajo del ~8 % = los 300 MB de la alerta MemoriaDisponibleBaja.",
            "node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes", "percentunit",
            thresholds((ROJO, None), (NARANJA, 0.08), (VERDE, 0.20))),
        indicador(
            5, 6, "CPU en uso",
            "Porcentaje de CPU en uso (todos los núcleos) en los últimos 5 min. El VPS tiene 2 vCPU; "
            "los picos cortos al generar un horario (solver OR-Tools) son normales. Lo preocupante es "
            "un nivel alto sostenido. Sin alerta todavía: el umbral se decidirá con datos reales.",
            '1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))', "percentunit",
            thresholds((VERDE, None), (NARANJA, 0.60), (ROJO, 0.85))),
        indicador(
            6, 12, "Disco /",
            "Porcentaje usado del disco raíz. Es compartido por las bases de datos de las tres apps y "
            "por las imágenes de Docker. Sin alerta todavía: este panel es el primer aviso visual.",
            'max(1 - node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}'
            ' / node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"})',
            "percentunit", thresholds((VERDE, None), (NARANJA, 0.70), (ROJO, 0.85))),
        indicador(
            7, 18, "Certificado (días)",
            "Días que le quedan al certificado más próximo a caducar. Let's Encrypt dura 90 días y "
            "Traefik renueva hacia los 30: lo normal es 30-90. Bajo 14 días (alerta "
            "CertificadoPorCaducar) es que la renovación falla en silencio.",
            "min((probe_ssl_earliest_cert_expiry - time()) / 86400)", "d",
            thresholds((ROJO, None), (NARANJA, 14), (VERDE, 21)), vmin=0, vmax=90),
    ]

    # Fila plegada: existe, pero no ocupa pantalla hasta que se despliega.
    detalle = {
        "id": 8, "type": "row", "title": "Detalle", "collapsed": True,
        "gridPos": {"x": 0, "y": 20, "w": 24, "h": 1},
        "panels": [
            serie(9, "Tiempo de respuesta",
                  "Cuánto tarda cada URL en contestar (redirecciones y TLS incluidos). Medido desde el "
                  "propio VPS: es el tiempo de Traefik + app, sin la red de internet. Una subida "
                  "sostenida suele anticipar un problema de RAM o CPU. El timeout de la sonda es 10 s.",
                  0, 21, 12, 8, "probe_duration_seconds", "{{app}} · {{tier}}", "s"),
            serie(10, "Memoria por contenedor (los 8 mayores)",
                  "RAM de cada contenedor (working set), los 8 que más usan. Los nombres son los de "
                  "Coolify (backend-g7r8rl4s…): pendiente de mapearlos a cada app con las etiquetas "
                  "que ponga Coolify en el VPS.",
                  12, 21, 12, 8, 'topk(8, container_memory_working_set_bytes{name!=""})',
                  "{{name}}", "bytes"),
            reinicios(11, 0, 29, 24, 5),
        ],
    }

    dashboard = {
        "uid": "vps-overview",
        "title": "VPS · visión general",
        "description": "Portada del VPS de Paufer, Gast-On y Multas. Generado por "
                       "grafana/tools/gen_vps_dashboard.py: no se edita desde la interfaz (se pierde).",
        "tags": ["infra", "vps"],
        "timezone": "browser",
        "editable": False,
        # Cursor compartido entre gráficas: al pasar el ratón por una, se marca
        # el mismo instante en todas.
        "graphTooltip": 1,
        "refresh": "30s",
        "time": {"from": "now-24h", "to": "now"},
        "schemaVersion": 39,
        "version": 2,
        "templating": {"list": [{
            # Variable OCULTA (hide=2): no se ve ni se elige. Solo existe para
            # que la tarjeta de app se repita una vez por cada valor de la
            # etiqueta "app" de las sondas.
            "name": "app", "type": "query", "datasource": DS, "hide": 2,
            "query": {"query": "label_values(probe_success, app)", "refId": "app"},
            "definition": "label_values(probe_success, app)",
            "includeAll": True, "multi": True, "refresh": 1, "sort": 1,
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
        }]},
        "panels": [banner(1), tarjeta_app(2), linea_tiempo(3), *indicadores, detalle],
    }

    destino = Path(__file__).resolve().parent.parent / "dashboards" / "vps.json"
    destino.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    visibles = len([p for p in dashboard["panels"] if p["type"] != "row"])
    ocultos = len(detalle["panels"])
    print(f"escrito {destino}  ({visibles} paneles a la vista + {ocultos} en la fila plegada)")


if __name__ == "__main__":
    main()
