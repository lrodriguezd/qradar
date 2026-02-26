#!/usr/bin/env python3
"""
QRadar Expensive Custom Properties Analyzer
=============================================
Analiza archivos .tabular exportados desde JMX/MBeans del EC (Event Collector)
y genera un reporte HTML con ranking de custom properties costosas y recomendaciones.

Referencia IBM: https://www.ibm.com/docs/en/qradar-on-cloud?topic=appliances-expensive-custom-properties-found

Uso:
    python3 qradar_expensive_properties.py <archivo.tabular> [opciones]

Ejemplos:
    python3 qradar_expensive_properties.py CustomProperties-2026-02-26-12-49.tabular
    python3 qradar_expensive_properties.py CustomProperties-*.tabular --top 50
    python3 qradar_expensive_properties.py CustomProperties-epfp01.tabular --threshold-ms 0.1

Cómo obtener el archivo desde QRadar (SSH en el EC):
    /opt/qradar/support/getCustomPropertyStats.sh > CustomProperties-$(hostname)-$(date +%Y%m%d).tabular
"""

import csv
import sys
import os
import re
import argparse
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# UMBRALES (en nanosegundos, igual que el archivo)
# ─────────────────────────────────────────────────────────────────────────────
NS_PER_MS = 1_000_000

THRESHOLDS = {
    "critical": 500_000,    # > 0.5ms  → CRÍTICO: deshabilitar o reescribir
    "high":     200_000,    # > 0.2ms  → ALTO: optimizar urgente
    "medium":    50_000,    # > 0.05ms → MEDIO: revisar
    "low":       20_000,    # > 0.02ms → BAJO: aceptable
}

# EPS de referencia para calcular impacto (ajustar según tu entorno)
REFERENCE_EPS = 1000


# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISIS DE REGEX
# ─────────────────────────────────────────────────────────────────────────────
def analyze_regex(pattern):
    """
    Detecta patrones anti-performáticos en la regex.
    Devuelve lista de problemas encontrados.
    """
    issues = []

    if not pattern:
        return issues

    # Backtracking catastrófico: grupos anidados con cuantificadores
    if re.search(r'\(.*[\+\*].*\)[\+\*\?]', pattern):
        issues.append(("CRÍTICO", "Posible backtracking catastrófico: cuantificadores anidados como `(.*+)+` o `(.+)*`. Puede causar timeout completo del parser."))

    # Lazy quantifiers amplios: .*? o .+? sin ancla
    lazy_count = len(re.findall(r'\.\*\?|\.\+\?', pattern))
    if lazy_count >= 2:
        issues.append(("ALTO", f"Múltiples lazy quantifiers (`.*?` o `.+?`): {lazy_count} encontrados. Cada uno fuerza backtracking adicional. Usar clases de caracteres negadas `[^delimitador]+` en su lugar."))
    elif lazy_count == 1:
        issues.append(("MEDIO", "Lazy quantifier (`.*?` o `.+?`) detectado. Considerar reemplazar con clase negada `[^delimitador]+` para mejor rendimiento."))

    # Greedy sin límite: .* o .+ sin anclaje
    greedy_count = len(re.findall(r'(?<!\[)\.[\*\+](?!\?)', pattern))
    if greedy_count >= 3:
        issues.append(("ALTO", f"Múltiples greedy quantifiers sin límite (`.*` o `.+`): {greedy_count} encontrados. Reducir el scope usando anclas o delimitadores específicos."))
    elif greedy_count >= 1:
        issues.append(("BAJO", f"`.*` o `.+` sin límite encontrado ({greedy_count}x). Considerar acotar con anclas o clases de caracteres más específicas."))

    # Alternación excesiva
    pipe_count = pattern.count('|')
    if pipe_count >= 5:
        issues.append(("ALTO", f"Alta alternación: {pipe_count} opciones con `|`. Evaluar si se puede dividir en múltiples custom properties o usar una clase de caracteres."))
    elif pipe_count >= 2:
        issues.append(("MEDIO", f"Alternación con {pipe_count} opciones. Ordenar de mayor a menor frecuencia esperada para mejorar rendimiento."))

    # Lookahead / lookbehind
    if re.search(r'\(\?[=!<]', pattern):
        issues.append(("MEDIO", "Lookahead o lookbehind detectado. Aunque son válidos, pueden impactar rendimiento en payloads largos. Evaluar si son necesarios."))

    # Regex muy larga (>100 chars)
    if len(pattern) > 150:
        issues.append(("BAJO", f"Regex larga ({len(pattern)} caracteres). Dividir en múltiples propiedades más específicas puede mejorar el rendimiento y la mantenibilidad."))

    # Sin ancla de inicio ni fin
    if not pattern.startswith('^') and not pattern.endswith('$') and '\\A' not in pattern and '\\Z' not in pattern:
        issues.append(("INFO", "Sin anclas `^` o `$`. Agregar anclas cuando sea posible para reducir el espacio de búsqueda del motor regex."))

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# CLASIFICACIÓN DE SEVERIDAD
# ─────────────────────────────────────────────────────────────────────────────
def classify_severity(avg_ns):
    if avg_ns >= THRESHOLDS["critical"]:
        return "CRÍTICO", "#dc2626", "🔴"
    elif avg_ns >= THRESHOLDS["high"]:
        return "ALTO", "#ea580c", "🟠"
    elif avg_ns >= THRESHOLDS["medium"]:
        return "MEDIO", "#ca8a04", "🟡"
    else:
        return "BAJO", "#16a34a", "🟢"


# ─────────────────────────────────────────────────────────────────────────────
# LÓGICA DE RECOMENDACIÓN
# ─────────────────────────────────────────────────────────────────────────────
def get_recommendation(prop):
    avg_ns      = prop["avg_ns"]
    max_ns      = prop["max_ns"]
    min_ns      = prop["min_ns"]
    times_called = prop["times_called"]
    cancelled   = prop["cancelled"]
    pattern     = prop["pattern"]
    avg_ms      = avg_ns / NS_PER_MS

    recommendations = []
    action = "MONITOREAR"
    priority = 4

    # Regex issues
    regex_issues = analyze_regex(pattern)

    # Regla con cancelaciones — indica timeout del regex
    if cancelled > 0:
        pct_cancel = (cancelled / max(times_called, 1)) * 100
        action = "DESHABILITAR"
        priority = 1
        recommendations.append(
            f"⛔ <strong>{cancelled:,} cancelaciones</strong> ({pct_cancel:.1f}% de ejecuciones). "
            f"El motor regex está haciendo timeout en esta propiedad — está causando que eventos "
            f"sean <strong>enrutados directamente a storage sin pasar por el CRE</strong>. "
            f"Deshabilitar inmediatamente hasta reescribir la regex."
        )

    # Muy costosa con alto volumen
    elif avg_ns >= THRESHOLDS["critical"] and times_called > 1000:
        action = "REESCRIBIR"
        priority = 1
        cpu_per_sec = (avg_ns * REFERENCE_EPS) / 1e9
        recommendations.append(
            f"Con {avg_ms:.3f}ms promedio y {times_called:,} llamadas, esta propiedad consume "
            f"~{cpu_per_sec:.2f}s de CPU por segundo a {REFERENCE_EPS} EPS. "
            f"Reescribir la regex con patrones más eficientes."
        )

    # Costosa con pocas llamadas (baja frecuencia, pero peso unitario alto)
    elif avg_ns >= THRESHOLDS["critical"] and times_called < 100:
        action = "REVISAR"
        priority = 2
        recommendations.append(
            f"Alto costo por evaluación ({avg_ms:.3f}ms) pero pocas llamadas ({times_called}). "
            f"Si el volumen de eventos que coincide aumenta, el impacto será significativo. "
            f"Acotar el scope de log sources o categorías donde aplica."
        )

    # Alto costo
    elif avg_ns >= THRESHOLDS["high"]:
        action = "OPTIMIZAR"
        priority = 2
        recommendations.append(
            f"Tiempo de evaluación elevado ({avg_ms:.3f}ms promedio). "
            f"Revisar el patrón regex y aplicar las optimizaciones indicadas abajo."
        )

    # Pico muy superior al promedio
    variance_ratio = max_ns / max(avg_ns, 1)
    if variance_ratio > 20 and max_ns > THRESHOLDS["high"]:
        recommendations.append(
            f"Pico máximo de {max_ns/NS_PER_MS:.3f}ms vs promedio de {avg_ms:.3f}ms "
            f"(ratio {variance_ratio:.0f}x). Comportamiento inestable ante ciertos payloads — "
            f"probablemente backtracking catastrófico en eventos específicos."
        )

    # Agregar issues de regex
    for level, issue in regex_issues:
        icon = {"CRÍTICO": "🔴", "ALTO": "🟠", "MEDIO": "🟡", "BAJO": "🔵", "INFO": "ℹ️"}.get(level, "•")
        recommendations.append(f"{icon} <em>[Regex/{level}]</em> {issue}")

    # Sin recomendaciones específicas
    if not recommendations:
        recommendations.append(
            "Dentro del rango aceptable. Continuar monitoreando si el sistema "
            "experimenta degradación de rendimiento."
        )

    if action == "MONITOREAR" and avg_ns >= THRESHOLDS["medium"]:
        action = "REVISAR"
        priority = 3

    return {
        "action": action,
        "priority": priority,
        "details": recommendations,
        "regex_issues": regex_issues,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PARSER
# ─────────────────────────────────────────────────────────────────────────────
def parse_tabular(filepath):
    """Lee el archivo .tabular y extrae métricas."""
    props = []

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")

        for row in reader:
            try:
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

                times_called = to_int("TimesCalled")
                avg_ns = to_float("AverageNanoSeconds")

                # Extraer nombre desde MBean si es posible
                mbean = row.get("MBean", "")
                name = ""
                if 'name="' in mbean:
                    name = mbean.split('name="')[1].rstrip('"')

                props.append({
                    "name":         name or mbean,
                    "mbean":        mbean,
                    "pattern":      row.get("Pattern", "").strip(),
                    "times_called": times_called,
                    "cancelled":    to_int("TimesCancelled"),
                    "avg_ns":       avg_ns,
                    "max_ns":       to_float("LongestMatchNanoSeconds"),
                    "min_ns":       to_float("ShortestMatchNanoSeconds"),
                    "avg_ms":       avg_ns / NS_PER_MS,
                    "max_ms":       to_float("LongestMatchNanoSeconds") / NS_PER_MS,
                    "min_ms":       to_float("ShortestMatchNanoSeconds") / NS_PER_MS,
                    "source_file":  Path(filepath).name,
                })

            except Exception:
                continue

    return props


# ─────────────────────────────────────────────────────────────────────────────
# GENERADOR HTML
# ─────────────────────────────────────────────────────────────────────────────
def generate_html_report(props_analyzed, source_files, top_n, threshold_ns):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    threshold_ms = threshold_ns / NS_PER_MS

    critical_count  = sum(1 for p in props_analyzed if p["avg_ns"] >= THRESHOLDS["critical"])
    high_count      = sum(1 for p in props_analyzed if THRESHOLDS["high"] <= p["avg_ns"] < THRESHOLDS["critical"])
    medium_count    = sum(1 for p in props_analyzed if THRESHOLDS["medium"] <= p["avg_ns"] < THRESHOLDS["high"])
    cancelled_count = sum(1 for p in props_analyzed if p["cancelled"] > 0)

    display_props = props_analyzed[:top_n]

    # Top 3 para resumen
    top3_html = "<br>".join([
        f"<b>#{i+1}</b> {p['pattern'][:70]}{'...' if len(p['pattern'])>70 else ''} "
        f"<span style='color:#dc2626'>({p['avg_ms']:.3f}ms avg)</span>"
        for i, p in enumerate(display_props[:3])
    ])

    # Generar filas
    rows_html = ""
    for i, prop in enumerate(display_props, 1):
        sev_label, sev_color, sev_icon = classify_severity(prop["avg_ns"])
        rec = get_recommendation(prop)

        action_colors = {
            "DESHABILITAR": "#dc2626",
            "REESCRIBIR":   "#9333ea",
            "OPTIMIZAR":    "#d97706",
            "REVISAR":      "#2563eb",
            "MONITOREAR":   "#16a34a",
        }
        action_color = action_colors.get(rec["action"], "#6b7280")

        rec_html = "<ul style='margin:4px 0 0 0; padding-left:16px;'>"
        for detail in rec["details"]:
            rec_html += f"<li style='margin-bottom:5px; line-height:1.4;'>{detail}</li>"
        rec_html += "</ul>"

        cancelled_display = (
            f'<span style="color:#dc2626; font-weight:700;">{prop["cancelled"]:,}</span>'
            if prop["cancelled"] > 0
            else f'<span style="color:#9ca3af">0</span>'
        )

        bar_pct = min(100, (prop["avg_ns"] / (THRESHOLDS["critical"] * 2)) * 100)
        pattern_display = prop["pattern"].replace("<", "&lt;").replace(">", "&gt;")

        rows_html += f"""
        <tr style="border-bottom:1px solid #e5e7eb;">
            <td style="padding:12px 8px; text-align:center; font-weight:700; color:#6b7280; font-size:13px;">{i}</td>
            <td style="padding:12px 8px; font-family:monospace; font-size:11px; color:#374151; 
                       max-width:280px; word-break:break-all;">{pattern_display}</td>
            <td style="padding:12px 8px; text-align:center;">
                <span style="display:inline-block; background:{sev_color}15; color:{sev_color}; 
                       border:1px solid {sev_color}40; border-radius:4px; 
                       padding:2px 8px; font-size:11px; font-weight:700;">
                    {sev_icon} {sev_label}
                </span>
            </td>
            <td style="padding:12px 8px; text-align:right;">
                <div style="font-weight:700; color:{sev_color}; font-size:15px;">{prop['avg_ms']:.3f}ms</div>
                <div style="font-size:10px; color:#9ca3af;">{prop['avg_ns']:,.0f} ns</div>
                <div style="background:#f3f4f6; border-radius:2px; height:4px; margin-top:4px;">
                    <div style="background:{sev_color}; width:{bar_pct:.0f}%; height:4px; border-radius:2px;"></div>
                </div>
            </td>
            <td style="padding:12px 8px; text-align:right; font-size:12px; color:#374151;">
                {prop['max_ms']:.3f}ms<br>
                <span style="color:#9ca3af; font-size:10px;">{prop['min_ms']:.4f}ms min</span>
            </td>
            <td style="padding:12px 8px; text-align:right; color:#374151; font-size:13px;">{prop['times_called']:,}</td>
            <td style="padding:12px 8px; text-align:center;">{cancelled_display}</td>
            <td style="padding:12px 8px; font-size:11px; color:#6b7280;">{prop['source_file']}</td>
            <td style="padding:12px 8px; text-align:center;">
                <span style="display:inline-block; background:{action_color}15; color:{action_color}; 
                       border:1px solid {action_color}40; border-radius:4px; 
                       padding:2px 8px; font-size:11px; font-weight:700;">
                    {rec['action']}
                </span>
            </td>
            <td style="padding:12px 8px; font-size:12px; color:#374151; min-width:300px; max-width:420px;">
                {rec_html}
            </td>
        </tr>"""

    source_label = ", ".join(source_files)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QRadar — Expensive Custom Properties Report</title>
    <style>
        * {{ box-sizing:border-box; margin:0; padding:0; }}
        body {{ font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#f9fafb; color:#111827; }}
        .header {{ background:linear-gradient(135deg, #1e1b4b 0%, #7c3aed 60%, #2563eb 100%); color:white; padding:32px 40px; }}
        .header h1 {{ font-size:24px; font-weight:700; margin-bottom:6px; }}
        .header .meta {{ font-size:13px; opacity:0.75; }}
        .content {{ padding:24px 40px; }}
        .summary-grid {{ display:grid; grid-template-columns:repeat(5,1fr); gap:16px; margin-bottom:24px; }}
        .card {{ background:white; border-radius:8px; padding:20px; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
        .card .value {{ font-size:32px; font-weight:700; margin-bottom:4px; }}
        .card .label {{ font-size:13px; color:#6b7280; }}
        table {{ width:100%; border-collapse:collapse; background:white; border-radius:8px; 
                 box-shadow:0 1px 3px rgba(0,0,0,0.1); overflow:hidden; }}
        thead tr {{ background:#1e1b4b; color:white; }}
        thead th {{ padding:12px 8px; text-align:left; font-size:11px; font-weight:600; 
                    text-transform:uppercase; letter-spacing:0.05em; white-space:nowrap; }}
        tbody tr:hover {{ background:#f9fafb; }}
        .legend {{ display:flex; gap:16px; margin-bottom:16px; flex-wrap:wrap; align-items:center; }}
        .badge {{ padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700; }}
        .footer {{ text-align:center; padding:24px; color:#9ca3af; font-size:12px; }}
    </style>
</head>
<body>

<div class="header">
    <h1>🔍 QRadar — Expensive Custom Properties Analyzer</h1>
    <div class="meta">
        Fuente: <strong>{source_label}</strong> &nbsp;|&nbsp;
        Generado: <strong>{now}</strong> &nbsp;|&nbsp;
        Umbral: <strong>&gt;{threshold_ms:.3f}ms</strong> &nbsp;|&nbsp;
        Top: <strong>{top_n}</strong>
        &nbsp;|&nbsp; Ref: <a href="https://www.ibm.com/docs/en/qradar-on-cloud?topic=appliances-expensive-custom-properties-found" style="color:#93c5fd;">IBM Docs 38750138</a>
    </div>
</div>

<div class="content">
    <div class="summary-grid" style="margin-top:24px;">
        <div class="card">
            <div class="value" style="color:#dc2626;">{critical_count}</div>
            <div class="label">🔴 CRÍTICAS (&gt;0.5ms)</div>
        </div>
        <div class="card">
            <div class="value" style="color:#ea580c;">{high_count}</div>
            <div class="label">🟠 ALTAS (0.2–0.5ms)</div>
        </div>
        <div class="card">
            <div class="value" style="color:#ca8a04;">{medium_count}</div>
            <div class="label">🟡 MEDIAS (0.05–0.2ms)</div>
        </div>
        <div class="card">
            <div class="value" style="color:#dc2626; font-size:28px;">{'⚠️ ' if cancelled_count > 0 else ''}{cancelled_count}</div>
            <div class="label">⛔ Con cancelaciones (CRE bypass)</div>
        </div>
        <div class="card">
            <div class="value" style="color:#374151;">{len(props_analyzed):,}</div>
            <div class="label">📊 Total propiedades analizadas</div>
        </div>
    </div>

    <!-- RESUMEN -->
    <div class="card" style="margin-bottom:24px; border-left:4px solid #7c3aed;">
        <div style="font-size:14px; font-weight:700; margin-bottom:8px;">📋 Resumen Ejecutivo</div>
        <div style="font-size:13px; color:#374151; line-height:1.7;">
            {'<div style="background:#fef2f2; border:1px solid #fecaca; border-radius:6px; padding:10px; margin-bottom:12px; color:#dc2626;"><strong>⛔ ALERTA CRÍTICA:</strong> Se detectaron ' + str(cancelled_count) + ' custom propert' + ('ies' if cancelled_count != 1 else 'y') + ' con cancelaciones (TimesCancelled &gt; 0). Esto indica que el motor regex está haciendo timeout, lo que causa que eventos sean enrutados directamente a storage sin pasar por el CRE. Deshabilitar inmediatamente.</div>' if cancelled_count > 0 else ''}
            Se analizaron <strong>{len(props_analyzed):,} custom properties</strong>.
            Se identificaron <strong style="color:#dc2626;">{critical_count} propiedades críticas</strong> con tiempo de evaluación 
            superior a 0.5ms que impactan directamente el rendimiento del pipeline de eventos.
            <br><br>
            <strong>Top 3 propiedades más costosas:</strong><br>
            <div style="margin-top:8px; font-family:monospace; font-size:11px; background:#f3f4f6; 
                        padding:10px; border-radius:4px; line-height:1.8; word-break:break-all;">
                {top3_html}
            </div>
        </div>
    </div>

    <!-- LEYENDA -->
    <div class="legend">
        <span style="font-size:12px; font-weight:600; color:#374151;">Acciones:</span>
        <span><span class="badge" style="background:#dc262615;color:#dc2626;border:1px solid #dc262640;">DESHABILITAR</span> Cancelaciones activas — CRE bypass</span>
        <span><span class="badge" style="background:#9333ea15;color:#9333ea;border:1px solid #9333ea40;">REESCRIBIR</span> Regex ineficiente de alto volumen</span>
        <span><span class="badge" style="background:#d9770615;color:#d97706;border:1px solid #d9770640;">OPTIMIZAR</span> Mejorar patrón regex</span>
        <span><span class="badge" style="background:#2563eb15;color:#2563eb;border:1px solid #2563eb40;">REVISAR</span> Analizar en próximo ciclo</span>
    </div>

    <!-- TABLA -->
    <div style="overflow-x:auto; margin-bottom:32px;">
        <table>
            <thead>
                <tr>
                    <th style="width:35px;">#</th>
                    <th style="min-width:200px;">Patrón Regex</th>
                    <th style="width:90px;">Severidad</th>
                    <th style="width:110px;">Avg Time ▼</th>
                    <th style="width:110px;">Max / Min</th>
                    <th style="width:80px;">Llamadas</th>
                    <th style="width:80px;">Canceladas</th>
                    <th style="width:100px;">Fuente</th>
                    <th style="width:110px;">Acción</th>
                    <th>Recomendación</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>

    <!-- GUÍA -->
    <div class="card" style="margin-bottom:24px;">
        <div style="font-size:16px; font-weight:700; margin-bottom:16px; padding-bottom:8px; border-bottom:2px solid #e5e7eb;">
            🔧 Guía de Optimización de Custom Properties
        </div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; font-size:13px;">
            <div>
                <div style="font-weight:700; color:#7c3aed; margin-bottom:8px;">Patrones ineficientes → alternativas</div>
                <table style="width:100%; font-size:12px; border:none; box-shadow:none;">
                    <tr style="background:#f3f4f6;">
                        <th style="padding:6px; text-align:left; background:#7c3aed; color:white;">❌ Evitar</th>
                        <th style="padding:6px; text-align:left; background:#16a34a; color:white;">✅ Preferir</th>
                    </tr>
                    <tr style="border-bottom:1px solid #e5e7eb;"><td style="padding:6px; font-family:monospace;">.*?</td><td style="padding:6px; font-family:monospace;">[^delimitador]+</td></tr>
                    <tr style="border-bottom:1px solid #e5e7eb;"><td style="padding:6px; font-family:monospace;">(.+)+</td><td style="padding:6px; font-family:monospace;">([^x]+)</td></tr>
                    <tr style="border-bottom:1px solid #e5e7eb;"><td style="padding:6px; font-family:monospace;">.*campo=.*</td><td style="padding:6px; font-family:monospace;">campo=([^\\s]+)</td></tr>
                    <tr style="border-bottom:1px solid #e5e7eb;"><td style="padding:6px; font-family:monospace;">(a|b|c|d|e)</td><td style="padding:6px; font-family:monospace;">[abcde]</td></tr>
                    <tr><td style="padding:6px; font-family:monospace;">^.*?texto</td><td style="padding:6px; font-family:monospace;">texto</td></tr>
                </table>
            </div>
            <div>
                <div style="font-weight:700; color:#7c3aed; margin-bottom:8px;">Pasos de remediación (IBM Docs 38750138)</div>
                <ol style="padding-left:16px; line-height:1.9; color:#374151;">
                    <li>Deshabilitar propiedades con <strong>cancelaciones activas</strong> (TimesCancelled &gt; 0)</li>
                    <li>Revisar el payload del evento y ajustar el regex al formato real</li>
                    <li>Acotar el scope: especificar <strong>log source</strong> y <strong>event name</strong> concretos</li>
                    <li>Reemplazar <code>.*?</code> por clases negadas <code>[^delimitador]+</code></li>
                    <li>Ordenar parsers de log source por volumen (mayor a menor)</li>
                    <li>Desactivar parsers de log source no utilizados</li>
                </ol>
            </div>
            <div>
                <div style="font-weight:700; color:#dc2626; margin-bottom:8px;">⚠️ Impacto de TimesCancelled &gt; 0</div>
                <div style="background:#fef2f2; border:1px solid #fecaca; border-radius:6px; padding:12px; color:#374151; line-height:1.6;">
                    Cuando una custom property cancela, el evento <strong>se enruta directamente 
                    a storage sin pasar por el CRE</strong>. Esto significa que ninguna regla de 
                    correlación puede actuar sobre ese evento — es el mismo síntoma descrito en 
                    el error QRadar 38750138. El impacto es silencioso: no hay alerta visible 
                    pero las ofensas no se generan.
                </div>
            </div>
            <div>
                <div style="font-weight:700; color:#16a34a; margin-bottom:8px;">✅ Cómo obtener el archivo</div>
                <div style="font-family:monospace; font-size:11px; background:#f0fdf4; padding:12px; 
                            border-radius:4px; line-height:1.8; color:#374151; border:1px solid #bbf7d0;">
                    # SSH al Event Collector (EC):<br>
                    cd /opt/qradar/support<br>
                    ./getCustomPropertyStats.sh \<br>
                    &nbsp;&nbsp;&gt; CustomProperties-$(hostname)-$(date +%Y%m%d).tabular<br>
                    <br>
                    # Copiar al host local:<br>
                    scp root@&lt;ec-ip&gt;:CustomProperties-*.tabular .
                </div>
            </div>
        </div>
    </div>

</div>

<div class="footer">
    QRadar Expensive Custom Properties Analyzer &nbsp;·&nbsp; {now} &nbsp;·&nbsp;
    Ref: <a href="https://www.ibm.com/docs/en/qradar-on-cloud?topic=appliances-expensive-custom-properties-found">IBM Docs 38750138</a>
</div>

</body>
</html>"""

    return html


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Analiza custom properties costosas de QRadar y genera reporte HTML"
    )
    parser.add_argument("input_files", nargs="+", help="Archivo(s) .tabular de CustomProperties")
    parser.add_argument("--top", type=int, default=100, help="Cuántas propiedades mostrar (default: 100)")
    parser.add_argument("--threshold-ms", type=float, default=0.02, help="Solo analizar props con avg > N ms (default: 0.02ms = 20000ns)")
    parser.add_argument("--output", type=str, default=None, help="Nombre del archivo HTML de salida")
    args = parser.parse_args()

    all_props = []
    threshold_ns = args.threshold_ms * NS_PER_MS

    for filepath in args.input_files:
        if not os.path.exists(filepath):
            print(f"[ERROR] No se encontró: {filepath}", file=sys.stderr)
            continue
        print(f"[INFO] Procesando: {filepath}")
        props = parse_tabular(filepath)
        print(f"       → {len(props):,} propiedades parseadas")
        all_props.extend(props)

    if not all_props:
        print("[ERROR] No se pudieron parsear propiedades.", file=sys.stderr)
        sys.exit(1)

    # Filtrar y ordenar
    filtered = [p for p in all_props if p["avg_ns"] >= threshold_ns]
    # Canceladas siempre al tope independientemente del tiempo
    cancelled = [p for p in all_props if p["cancelled"] > 0 and p not in filtered]
    filtered = cancelled + filtered
    filtered.sort(key=lambda p: (-(p["cancelled"] > 0), -p["avg_ns"]))

    print(f"[INFO] Propiedades sobre umbral {args.threshold_ms}ms: {len(filtered):,} de {len(all_props):,}")
    print(f"[INFO] Con cancelaciones (CRE bypass): {sum(1 for p in all_props if p['cancelled'] > 0)}")

    # Generar reporte
    html = generate_html_report(filtered, args.input_files, args.top, threshold_ns)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = args.output or f"qradar_expensive_properties_{ts}.html"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[OK] Reporte generado: {out_path}")
    print(f"     → Críticas  (>0.5ms): {sum(1 for p in filtered if p['avg_ns'] >= THRESHOLDS['critical'])}")
    print(f"     → Altas    (>0.2ms): {sum(1 for p in filtered if THRESHOLDS['high'] <= p['avg_ns'] < THRESHOLDS['critical'])}")
    print(f"     → Medias  (>0.05ms): {sum(1 for p in filtered if THRESHOLDS['medium'] <= p['avg_ns'] < THRESHOLDS['high'])}")
    print(f"     → Con cancelaciones: {sum(1 for p in filtered if p['cancelled'] > 0)}")


if __name__ == "__main__":
    main()
