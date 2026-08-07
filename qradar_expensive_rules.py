#!/usr/bin/env python3
"""
QRadar Expensive Rules Analyzer    [ARCHIVED — historical reference only]
========================================================================

AVISO:  Esta version sin tests, sin paquete y con varios bugs conocidos
    (HTML injection, parser silencioso, sin XSS escape) ha sido REEMPLAZADA
    por un proyecto propio con pytest, CI, JSON/CSV/Markdown y anonimizacion:

         https://github.com/lrodriguezd/qradar-rule-profiler

    Instalacion:
        pipx install git+https://github.com/lrodriguezd/qradar-rule-profiler.git
        qradar-rule-profiler report CustomRule-*.txt

    Este archivo se conserva solo por referencia historica.

========================================================================
Analiza el archivo CustomRule TSV exportado desde JMX/MBeans del EP
y genera un reporte HTML con ranking de reglas costosas y recomendaciones.

Uso:
    python3 qradar_expensive_rules.py <archivo_tsv> [--top N] [--threshold-ms X]

Ejemplo:
    python3 qradar_expensive_rules.py CustomRule-YYYY-MM-DD-hh-mm-epXX-NNNNN.txt
    python3 qradar_expensive_rules.py CustomRule-*.txt --top 50 --threshold-ms 5
"""

import csv
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE UMBRALES (en segundos, igual que el archivo)
# ─────────────────────────────────────────────────────────────────────────────
THRESHOLDS = {
    "critical":  0.100,   # > 100ms  → CRÍTICO: deshabilitar o reescribir
    "high":      0.050,   # > 50ms   → ALTO: revisar y optimizar
    "medium":    0.020,   # > 20ms   → MEDIO: monitorear
    "low":       0.010,   # > 10ms   → BAJO: aceptable pero a observar
}

FIRED_COUNT_MIN = 0  # Incluir reglas aunque nunca hayan disparado (pueden ser costosas igual)


# ─────────────────────────────────────────────────────────────────────────────
# LÓGICA DE RECOMENDACIÓN
# ─────────────────────────────────────────────────────────────────────────────
def get_recommendation(rule):
    """
    Genera recomendación específica basada en el perfil de la regla.
    Combina tiempo de evaluación, frecuencia de disparo y tipo de regla.
    """
    avg_ms   = rule["avg_test_ms"]
    max_ms   = rule["max_test_ms"]
    alltime_max_ms = rule["alltime_max_ms"]
    fired    = rule["fired_count"]
    tested   = rule["total_test_count"]
    name     = rule["name"]
    folder   = rule["folder"]
    rule_id  = rule["id"]
    cap_eps  = rule["capacity_eps"]

    recommendations = []
    action = "MONITOREAR"
    priority = 4

    # ── Regla muy costosa y nunca dispara ──────────────────────────────────
    if avg_ms > THRESHOLDS["critical"] * 1000 and fired == 0 and tested > 500:
        action = "DESHABILITAR"
        priority = 1
        recommendations.append(
            f"Esta regla consume {avg_ms:.1f}ms promedio evaluándose contra cada evento "
            f"pero NUNCA ha generado una ofensa (FiredCount=0 en {tested:,} evaluaciones). "
            f"Es un costo de CPU puro sin valor operacional."
        )

    # ── Regla crítica con alto volumen ────────────────────────────────────
    elif avg_ms > THRESHOLDS["critical"] * 1000 and tested > 1000:
        action = "REESCRIBIR"
        priority = 1
        recommendations.append(
            f"Tiempo promedio de {avg_ms:.1f}ms con {tested:,} evaluaciones totales. "
            f"Tiempo acumulado: {(avg_ms * tested / 1000):.1f}s de CPU solo en esta regla. "
            f"Reescribir anteponiendo condiciones simples (IP, puerto, categoría) antes "
            f"de condiciones complejas (funciones, acumulaciones, referencias)."
        )

    # ── Regla de BB (Building Block) costosa ──────────────────────────────
    elif "BB" in name or "BB" in folder:
        if avg_ms > THRESHOLDS["medium"] * 1000:
            action = "OPTIMIZAR BB"
            priority = 2
            recommendations.append(
                f"Es un Building Block referenciado por múltiples reglas. "
                f"Optimizarlo impacta positivamente en TODAS las reglas que lo usan. "
                f"Revisar condiciones y simplificar la lógica de clasificación."
            )

    # ── Regla con picos extremos (max >> avg) ─────────────────────────────
    if alltime_max_ms > avg_ms * 10 and alltime_max_ms > THRESHOLDS["high"] * 1000:
        recommendations.append(
            f"Pico histórico de {alltime_max_ms:.0f}ms vs promedio de {avg_ms:.1f}ms "
            f"(ratio {alltime_max_ms/max(avg_ms,0.001):.0f}x). "
            f"Indica comportamiento inestable ante ciertos eventos — revisar condiciones "
            f"con expresiones regulares o lookups costosos que se activan esporádicamente."
        )

    # ── Regla con CapacityEps baja (sistema bajo presión por esta regla) ──
    if cap_eps > 0 and cap_eps < 500000:
        recommendations.append(
            f"CapacityEPS={cap_eps:,.0f} — esta regla limita la capacidad del EP a menos "
            f"de 500K EPS. Optimizar para aumentar el headroom del procesador."
        )

    # ── Regla de alta frecuencia con tiempo medio-alto ────────────────────
    if tested > 2000 and avg_ms > THRESHOLDS["medium"] * 1000:
        if action == "MONITOREAR":
            action = "OPTIMIZAR"
            priority = 2
        recommendations.append(
            f"Alta frecuencia de evaluación ({tested:,} veces). "
            f"Agregar condiciones de filtrado más selectivas al inicio de la regla "
            f"para reducir el número de eventos que llegan a las condiciones costosas."
        )

    # ── Regla que disparó muchas veces ────────────────────────────────────
    if fired > 1000:
        recommendations.append(
            f"Ha generado {fired:,} ofensas/responses. Si el volumen de alertas es "
            f"excesivo, evaluar agregar condiciones de supresión o ajustar umbrales."
        )

    # ── Sin recomendaciones específicas ───────────────────────────────────
    if not recommendations:
        if avg_ms > THRESHOLDS["medium"] * 1000:
            recommendations.append(
                "Tiempo de evaluación elevado. Revisar condiciones de la regla y "
                "asegurarse de que las más selectivas estén primero en la cadena de evaluación."
            )
        else:
            recommendations.append(
                "Dentro de rango aceptable. Continuar monitoreando si el sistema "
                "experimenta degradación de rendimiento."
            )

    # Determinar acción si aún es MONITOREAR pero tiene tiempo alto
    if action == "MONITOREAR" and avg_ms > THRESHOLDS["high"] * 1000:
        action = "REVISAR"
        priority = 3

    return {
        "action": action,
        "priority": priority,
        "details": recommendations,
        "qradar_url": f"/console/do/sem/editrule?appName=Sem&pageId=EditRule&ruleId={rule_id}" if rule_id else None
    }


# ─────────────────────────────────────────────────────────────────────────────
# PARSER DEL ARCHIVO TSV
# ─────────────────────────────────────────────────────────────────────────────
def parse_tsv(filepath):
    """Lee el archivo CustomRule TSV y extrae métricas relevantes."""
    rules = []

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")

        for row in reader:
            try:
                # Extraer folder desde el MBean string
                mbean = row.get("MBean", "")
                folder = ""
                if "folder=" in mbean:
                    folder = mbean.split("folder=")[1].split(",")[0]

                # Convertir a float con fallback a 0
                def to_float(key):
                    val = row.get(key, "0") or "0"
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return 0.0

                def to_int(key):
                    val = row.get(key, "0") or "0"
                    try:
                        return int(float(val))
                    except (ValueError, TypeError):
                        return 0

                # Convertir tiempos de segundos a milisegundos
                avg_test_s      = to_float("AllTimeAverageTestTime")
                max_test_s      = to_float("AllTimeMaximumTestTime")
                current_max_s   = to_float("MaximumTestTime")
                avg_test_ms     = avg_test_s * 1000
                max_test_ms     = max_test_s * 1000

                # Filtrar filas con tiempo 0 (nunca evaluadas)
                total_test = to_int("TotalTestCount")
                if total_test == 0 and avg_test_ms == 0:
                    continue

                rule = {
                    "name":            row.get("Name", "").strip(),
                    "folder":          folder,
                    "id":              row.get("Id", "").strip(),
                    "avg_test_ms":     avg_test_ms,
                    "max_test_ms":     max_test_ms,
                    "current_max_ms":  current_max_s * 1000,
                    "alltime_max_ms":  max_test_ms,
                    "fired_count":     to_int("FiredCount"),
                    "total_test_count": total_test,
                    "total_test_time_s": to_float("TotalTestTime"),
                    "capacity_eps":    to_float("CapacityEps"),
                    "alltime_cap_eps": to_float("AllTimeCapacityEps"),
                    "response_count":  to_int("TotalResponseCount"),
                    "max_test_timestamp": row.get("AllTimeMaximumTestTimeTimestamp", ""),
                    "mbean":           mbean,
                }
                rules.append(rule)

            except Exception as e:
                continue  # Saltar filas malformadas

    return rules


# ─────────────────────────────────────────────────────────────────────────────
# CLASIFICACIÓN DE SEVERIDAD
# ─────────────────────────────────────────────────────────────────────────────
def classify_severity(avg_ms):
    if avg_ms >= THRESHOLDS["critical"] * 1000:
        return "CRÍTICO", "#dc2626", "[CRITICO]"
    elif avg_ms >= THRESHOLDS["high"] * 1000:
        return "ALTO", "#ea580c", "[ALTO]"
    elif avg_ms >= THRESHOLDS["medium"] * 1000:
        return "MEDIO", "#ca8a04", "[MEDIO]"
    else:
        return "BAJO", "#16a34a", "[BAJO]"


# ─────────────────────────────────────────────────────────────────────────────
# GENERADOR DE REPORTE HTML
# ─────────────────────────────────────────────────────────────────────────────
def generate_html_report(rules_analyzed, source_file, top_n, threshold_ms):
    """Genera el reporte HTML completo."""

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ep_name = Path(source_file).stem
    total_rules_in_file = len(rules_analyzed) + 0  # ajustar si se filtró
    critical_count = sum(1 for r in rules_analyzed if r["avg_test_ms"] >= THRESHOLDS["critical"] * 1000)
    high_count     = sum(1 for r in rules_analyzed if THRESHOLDS["high"] * 1000 <= r["avg_test_ms"] < THRESHOLDS["critical"] * 1000)
    medium_count   = sum(1 for r in rules_analyzed if THRESHOLDS["medium"] * 1000 <= r["avg_test_ms"] < THRESHOLDS["high"] * 1000)

    # Calcular CPU total acumulada por todas las reglas
    total_cpu_s = sum(r["total_test_time_s"] for r in rules_analyzed)

    # Top N para mostrar
    display_rules = rules_analyzed[:top_n]

    # Generar filas de la tabla
    rows_html = ""
    for i, rule in enumerate(display_rules, 1):
        sev_label, sev_color, sev_icon = classify_severity(rule["avg_test_ms"])
        rec = get_recommendation(rule)

        action_colors = {
            "DESHABILITAR": "#dc2626",
            "REESCRIBIR":   "#9333ea",
            "OPTIMIZAR BB": "#ea580c",
            "OPTIMIZAR":    "#d97706",
            "REVISAR":      "#2563eb",
            "MONITOREAR":   "#16a34a",
        }
        action_color = action_colors.get(rec["action"], "#6b7280")

        rec_html = "<ul style='margin:4px 0 0 0; padding-left:18px;'>"
        for detail in rec["details"]:
            rec_html += f"<li style='margin-bottom:4px;'>{detail}</li>"
        rec_html += "</ul>"

        fired_display = f"{rule['fired_count']:,}" if rule['fired_count'] > 0 else '<span style="color:#9ca3af">0</span>'
        cpu_total = rule['total_test_time_s']
        cpu_display = f"{cpu_total:.2f}s" if cpu_total < 60 else f"{cpu_total/60:.1f}min"

        # Barra de calor para avg_test_ms
        bar_pct = min(100, (rule["avg_test_ms"] / (THRESHOLDS["critical"] * 1000 * 2)) * 100)
        bar_color = sev_color

        rows_html += f"""
        <tr style="border-bottom: 1px solid #e5e7eb;">
            <td style="padding:12px 8px; text-align:center; font-weight:700; color:#6b7280; font-size:13px;">#{i}</td>
            <td style="padding:12px 8px;">
                <div style="font-weight:600; color:#111827; font-size:13px; margin-bottom:2px;">{rule['name']}</div>
                <div style="font-size:11px; color:#6b7280;">{rule['folder']}</div>
                {'<div style="font-size:11px; color:#9ca3af;">ID: ' + rule['id'] + '</div>' if rule['id'] else ''}
            </td>
            <td style="padding:12px 8px; text-align:center;">
                <span style="display:inline-block; background:{sev_color}15; color:{sev_color};
                       border:1px solid {sev_color}40; border-radius:4px;
                       padding:2px 8px; font-size:11px; font-weight:700;">
                    {sev_icon} {sev_label}
                </span>
            </td>
            <td style="padding:12px 8px; text-align:right;">
                <div style="font-weight:700; color:{sev_color}; font-size:15px;">{rule['avg_test_ms']:.1f}ms</div>
                <div style="background:#f3f4f6; border-radius:2px; height:4px; margin-top:4px;">
                    <div style="background:{bar_color}; width:{bar_pct:.0f}%; height:4px; border-radius:2px;"></div>
                </div>
            </td>
            <td style="padding:12px 8px; text-align:right; color:#374151; font-size:13px;">{rule['max_test_ms']:.1f}ms</td>
            <td style="padding:12px 8px; text-align:right; color:#374151; font-size:13px;">{rule['total_test_count']:,}</td>
            <td style="padding:12px 8px; text-align:right; font-size:13px;">{fired_display}</td>
            <td style="padding:12px 8px; text-align:right; color:#6b7280; font-size:13px;">{cpu_display}</td>
            <td style="padding:12px 8px; text-align:center;">
                <span style="display:inline-block; background:{action_color}15; color:{action_color};
                       border:1px solid {action_color}40; border-radius:4px;
                       padding:2px 8px; font-size:11px; font-weight:700;">
                    {rec['action']}
                </span>
            </td>
            <td style="padding:12px 8px; font-size:12px; color:#374151; min-width:280px; max-width:380px;">
                {rec_html}
            </td>
        </tr>"""

    # Generar resumen ejecutivo
    top3_names = "<br>".join([
        f"<b>#{i+1}</b> {r['name']} ({r['avg_test_ms']:.1f}ms)"
        for i, r in enumerate(display_rules[:3])
    ])

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QRadar — Expensive Rules Report</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #f9fafb; color: #111827; }}
        .header {{ background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #1e40af 100%);
                   color: white; padding: 32px 40px; }}
        .header h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 6px; }}
        .header .meta {{ font-size: 13px; opacity: 0.75; }}
        .content {{ padding: 24px 40px; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
        .card {{ background: white; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .card .value {{ font-size: 32px; font-weight: 700; margin-bottom: 4px; }}
        .card .label {{ font-size: 13px; color: #6b7280; }}
        .section-title {{ font-size: 18px; font-weight: 700; margin-bottom: 16px; color: #111827;
                          padding-bottom: 8px; border-bottom: 2px solid #e5e7eb; }}
        table {{ width: 100%; border-collapse: collapse; background: white;
                 border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }}
        thead tr {{ background: #1e1b4b; color: white; }}
        thead th {{ padding: 12px 8px; text-align: left; font-size: 12px; font-weight: 600;
                    text-transform: uppercase; letter-spacing: 0.05em; white-space: nowrap; }}
        tbody tr:hover {{ background: #f9fafb; }}
        .legend {{ display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }}
        .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 12px; color: #6b7280; }}
        .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
        .footer {{ text-align: center; padding: 24px; color: #9ca3af; font-size: 12px; }}
        @media print {{
            body {{ background: white; }}
            .header {{ background: #1e1b4b !important; -webkit-print-color-adjust: exact; }}
        }}
    </style>
</head>
<body>

<div class="header">
    <h1>QRadar — Expensive Rules Analyzer</h1>
    <div class="meta">
        Fuente: <strong>{ep_name}</strong> &nbsp;|&nbsp;
        Generado: <strong>{now}</strong> &nbsp;|&nbsp;
        Umbral análisis: <strong>&gt;{threshold_ms}ms</strong> &nbsp;|&nbsp;
        Mostrando top: <strong>{top_n} reglas</strong>
    </div>
</div>

<div class="content">

    <!-- RESUMEN EJECUTIVO -->
    <div class="summary-grid" style="margin-top:24px;">
        <div class="card">
            <div class="value" style="color:#dc2626;">{critical_count}</div>
            <div class="label">[CRITICO] Reglas CRÍTICAS (&gt;100ms)</div>
        </div>
        <div class="card">
            <div class="value" style="color:#ea580c;">{high_count}</div>
            <div class="label">[ALTO] Reglas ALTAS (50–100ms)</div>
        </div>
        <div class="card">
            <div class="value" style="color:#ca8a04;">{medium_count}</div>
            <div class="label">[MEDIO] Reglas MEDIAS (20–50ms)</div>
        </div>
        <div class="card">
            <div class="value" style="color:#374151;">{total_cpu_s:.1f}s</div>
            <div class="label">CPU acumulada (top {top_n})</div>
        </div>
    </div>

    <!-- CONTEXTO -->
    <div class="card" style="margin-bottom:24px; border-left:4px solid #1e40af;">
        <div style="font-size:14px; font-weight:700; margin-bottom:8px;">Resumen Ejecutivo</div>
        <div style="font-size:13px; color:#374151; line-height:1.6;">
            Se analizaron <strong>{len(rules_analyzed):,} reglas activas</strong> del Event Processor <strong>{ep_name}</strong>.
            Se identificaron <strong style="color:#dc2626;">{critical_count} reglas críticas</strong> con tiempo de evaluación
            superior a 100ms, que representan el mayor impacto en el rendimiento del CRE.
            <br><br>
            <strong>Top 3 reglas más costosas:</strong><br>
            <div style="margin-top:8px; font-family:monospace; font-size:12px; background:#f3f4f6; padding:10px; border-radius:4px;">
                {top3_names}
            </div>
            <br>
            <strong>Recomendación prioritaria:</strong> Las reglas marcadas como
            <span style="background:#dc262615; color:#dc2626; border:1px solid #dc262640; border-radius:4px;
                  padding:1px 6px; font-size:11px; font-weight:700;">DESHABILITAR</span> y
            <span style="background:#9333ea15; color:#9333ea; border:1px solid #9333ea40; border-radius:4px;
                  padding:1px 6px; font-size:11px; font-weight:700;">REESCRIBIR</span>
            deben atenderse en las próximas 48 horas. Las reglas Building Block
            (<span style="background:#ea580c15; color:#ea580c; border:1px solid #ea580c40; border-radius:4px;
                  padding:1px 6px; font-size:11px; font-weight:700;">OPTIMIZAR BB</span>)
            tienen efecto multiplicador sobre el resto del motor de correlación.
        </div>
    </div>

    <!-- LEYENDA -->
    <div class="legend">
        <span style="font-size:12px; font-weight:600; color:#374151;">Acciones:</span>
        <span class="legend-item"><span class="badge" style="background:#dc262615;color:#dc2626;border:1px solid #dc262640;">DESHABILITAR</span> Regla costosa sin valor operacional</span>
        <span class="legend-item"><span class="badge" style="background:#9333ea15;color:#9333ea;border:1px solid #9333ea40;">REESCRIBIR</span> Refactorizar la lógica de la regla</span>
        <span class="legend-item"><span class="badge" style="background:#ea580c15;color:#ea580c;border:1px solid #ea580c40;">OPTIMIZAR BB</span> Building Block — impacto multiplicado</span>
        <span class="legend-item"><span class="badge" style="background:#d9770615;color:#d97706;border:1px solid #d9770640;">OPTIMIZAR</span> Agregar filtros más selectivos</span>
        <span class="legend-item"><span class="badge" style="background:#2563eb15;color:#2563eb;border:1px solid #2563eb40;">REVISAR</span> Analizar en próximo ciclo</span>
    </div>

    <!-- TABLA PRINCIPAL -->
    <div style="overflow-x:auto; margin-bottom:32px;">
        <table>
            <thead>
                <tr>
                    <th style="width:40px;">#</th>
                    <th>Nombre de Regla / Folder</th>
                    <th style="width:90px;">Severidad</th>
                    <th style="width:110px;">Avg Test Time ▼</th>
                    <th style="width:110px;">Max AllTime</th>
                    <th style="width:90px;">Total Tests</th>
                    <th style="width:80px;">Disparos</th>
                    <th style="width:80px;">CPU Total</th>
                    <th style="width:110px;">Acción</th>
                    <th>Recomendación</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>

    <!-- GUÍA DE OPTIMIZACIÓN -->
    <div class="card" style="margin-bottom:24px;">
        <div style="font-size:16px; font-weight:700; margin-bottom:16px; padding-bottom:8px; border-bottom:2px solid #e5e7eb;">
            Guía de Optimización de Reglas en QRadar
        </div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; font-size:13px;">
            <div>
                <div style="font-weight:700; color:#1e40af; margin-bottom:8px;">Orden de condiciones (más importante)</div>
                <ol style="padding-left:16px; line-height:1.8; color:#374151;">
                    <li>Categoría de evento / Log Source Type</li>
                    <li>IP de origen/destino con referencias simples</li>
                    <li>Puertos y protocolos</li>
                    <li>Campos de texto (username, hostname)</li>
                    <li>Expresiones regulares (más costoso)</li>
                    <li>Funciones de acumulación (window) — al final</li>
                </ol>
            </div>
            <div>
                <div style="font-weight:700; color:#1e40af; margin-bottom:8px;">Cómo obtener el archivo desde QRadar</div>
                <div style="font-family:monospace; font-size:11px; background:#f3f4f6; padding:12px; border-radius:4px; line-height:1.8; color:#374151;">
                    # Desde la consola QRadar (SSH):<br>
                    cd /opt/qradar/support<br>
                    ./getAllCustomRuleStats.sh &gt; CustomRule-$(hostname)-$(date +%Y%m%d).txt<br>
                    <br>
                    # O via JMX directo al EP:<br>
                    # Admin → System Config → Console Settings<br>
                    # → JMX: com.q1labs.sem → type=filters
                </div>
            </div>
            <div>
                <div style="font-weight:700; color:#dc2626; margin-bottom:8px;">AVISO: Antes de deshabilitar una regla</div>
                <ul style="padding-left:16px; line-height:1.8; color:#374151;">
                    <li>Verificar si tiene ofensas activas asociadas</li>
                    <li>Confirmar con el equipo SOC si es operacionalmente requerida</li>
                    <li>Exportar la regla antes de modificarla (backup)</li>
                    <li>Aplicar cambios en horario de baja actividad</li>
                </ul>
            </div>
            <div>
                <div style="font-weight:700; color:#16a34a; margin-bottom:8px;">OK: Métricas post-optimización</div>
                <ul style="padding-left:16px; line-height:1.8; color:#374151;">
                    <li>AllTimeAverageTestTime debe bajar &lt;10ms</li>
                    <li>CapacityEPS debe subir (más margen disponible)</li>
                    <li>AccumulationService delays deben reducirse</li>
                    <li>Throttles de EC deben disminuir progresivamente</li>
                </ul>
            </div>
        </div>
    </div>

</div>

<div class="footer">
    Generado por QRadar Expensive Rules Analyzer &nbsp;·&nbsp; {now} &nbsp;·&nbsp;
    Fuente: {source_file}
</div>

</body>
</html>"""

    return html


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Analiza reglas costosas de QRadar y genera reporte HTML"
    )
    parser.add_argument("input_files", nargs="+", help="Archivo(s) TSV de CustomRule")
    parser.add_argument("--top", type=int, default=100, help="Cuántas reglas mostrar en el reporte (default: 100)")
    parser.add_argument("--threshold-ms", type=float, default=10.0, help="Solo analizar reglas con avg > N ms (default: 10)")
    parser.add_argument("--output", type=str, default=None, help="Nombre del archivo de salida HTML")
    args = parser.parse_args()

    all_rules = []

    for filepath in args.input_files:
        if not os.path.exists(filepath):
            print(f"[ERROR] No se encontró el archivo: {filepath}", file=sys.stderr)
            continue

        print(f"[INFO] Procesando: {filepath}")
        rules = parse_tsv(filepath)
        print(f"       → {len(rules):,} reglas parseadas")
        all_rules.extend(rules)

    if not all_rules:
        print("[ERROR] No se pudieron parsear reglas. Verificar formato del archivo.", file=sys.stderr)
        sys.exit(1)

    # Filtrar por umbral mínimo
    threshold_s = args.threshold_ms / 1000
    filtered = [r for r in all_rules if r["avg_test_ms"] >= args.threshold_ms]
    print(f"[INFO] Reglas sobre umbral {args.threshold_ms}ms: {len(filtered):,} de {len(all_rules):,} totales")

    # Ordenar por avg_test_ms descendente
    filtered.sort(key=lambda r: r["avg_test_ms"], reverse=True)

    # Generar reporte
    source_label = ", ".join(args.input_files)
    html = generate_html_report(filtered, source_label, args.top, args.threshold_ms)

    # Guardar
    if args.output:
        out_path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = f"qradar_expensive_rules_{ts}.html"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[OK] Reporte generado: {out_path}")
    print(f"     → Reglas críticas (>100ms): {sum(1 for r in filtered if r['avg_test_ms'] >= 100)}")
    print(f"     → Reglas altas   (>50ms):   {sum(1 for r in filtered if 50 <= r['avg_test_ms'] < 100)}")
    print(f"     → Reglas medias  (>20ms):   {sum(1 for r in filtered if 20 <= r['avg_test_ms'] < 50)}")


if __name__ == "__main__":
    main()
