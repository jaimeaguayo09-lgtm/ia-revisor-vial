
import io, re
from collections import defaultdict
import fitz
import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

st.set_page_config(page_title="IA Revisor Vial", page_icon="🛣️", layout="wide")
st.title("🛣️ IA Revisor Vial — Versión 2.1")
st.caption("Revisión técnica 2.1: consolida el motor técnico y genera un informe PDF estructurado para revisión y remisión al consultor.")

MODULES = ["Antecedentes","Aforos","Demanda","Capacidad y saturación","Modelación","Geometría",
           "Señalización y demarcación","Consistencia documental","Medidas de mitigación"]

def clean(s): return re.sub(r"\s+"," ",s or "").strip()

@st.cache_data(show_spinner=False)
def extract_pdf(data):
    d=fitz.open(stream=data,filetype="pdf")
    return [{"page":i+1,"text":clean(p.get_text("text"))} for i,p in enumerate(d)]

def snippet(txt,a,b,r=130):
    return clean(txt[max(0,a-r):min(len(txt),b+r)])

# v0.3: deliberately narrow, high-confidence quantity rules.
# A number is accepted only when grammatically attached to the target concept.
RULES = {
 "Estacionamientos de vehículos": [
   r"(?P<n>\d{1,4})\s+(?:unidades?\s+)?(?:de\s+)?estacionamientos?\s+(?:para\s+)?veh[ií]culos?\s+motorizados?",
   r"(?:dotaci[oó]n\s+de\s+)?estacionamientos?\s+(?:vehiculares|para\s+veh[ií]culos?)\s*(?:de|:|es|corresponde\s+a)?\s*(?P<n>\d{1,4})\b",
 ],
 "Estacionamientos de bicicletas": [
   r"(?P<n>\d{1,4})\s+(?:unidades?\s+)?(?:de\s+)?estacionamientos?\s+(?:para\s+)?bicicletas?\b",
   r"(?:estacionamientos?|cupos?)\s+(?:para\s+|de\s+)?bicicletas?\s*(?:de|:|es|corresponde\s+a)?\s*(?P<n>\d{1,4})\b",
   r"bicicleteros?\s*(?:de|:|es|corresponde\s+a)?\s*(?P<n>\d{1,4})\b",
 ],
 "Estacionamientos PMR": [
   r"(?:se\s+consideran|considerando|incluye[n]?|contempla[n]?|corresponden?)\s+(?P<n>\d{1,3})\s+(?:estacionamientos?\s+)?para\s+personas?\s+con\s+movilidad\s+reducida\b",
   r"(?P<n>\d{1,3})\s+estacionamientos?\s+(?:reservados?\s+)?para\s+personas?\s+con\s+movilidad\s+reducida\b",
   r"(?:estacionamientos?|cupos?)\s+(?:para\s+)?(?:personas?\s+con\s+movilidad\s+reducida|PMR)\s*(?:de|:|es|corresponde\s+a)?\s*(?P<n>\d{1,3})\b",
 ],
}

def extract_concepts(pages):
    out=defaultdict(list)
    for p in pages:
        for concept,pats in RULES.items():
            for pat in pats:
                for m in re.finditer(pat,p["text"],re.I):
                    n=int(m.group("n"))
                    ev=snippet(p["text"],m.start(),m.end())
                    key=(concept,n,p["page"],ev)
                    if not any((h["concept"],h["value"],h["page"],h["evidence"])==key for h in out[concept]):
                        out[concept].append({"concept":concept,"value":n,"page":p["page"],"evidence":ev})
    return out

def obsrow(i,materia,pags,hallazgo,evidencia,comprobacion,clasif,accion):
    return {"ID":f"RV-{i:03d}","Página":pags,"Materia":materia,"Hallazgo":hallazgo,
            "Evidencia":evidencia,"Comprobación":comprobacion,
            "Clasificación":clasif,"Acción requerida":accion}

def _pct(s):
    try: return float(s.replace(",", "."))
    except: return None

def _rows_after_header(text, header_pattern):
    m = re.search(header_pattern, text, re.I)
    if not m: return []
    tail = text[m.end():]
    rows = []
    # Typical extracted table row: ARC PM-L PT-L
    for rm in re.finditer(r"(?m)(?<!\d)(\d{3,4})\s+(\d{1,3})\s+(\d{1,3})(?!\d)", tail):
        arc, pm, pt = rm.group(1), int(rm.group(2)), int(rm.group(3))
        if pm <= 200 and pt <= 200:
            rows.append((arc, pm, pt))
        if len(rows) >= 80: break
    return rows

def _scenario_tables(pages):
    """
    Extractor 1.6 basado en la estructura real del IMIV.

    Regla principal:
    el escenario NO se determina por el rótulo repetido de la columna
    "Grados de saturación - Situación Proyecto", porque el propio informe usa
    ese mismo rótulo dentro del Cuadro 9.16 mitigado.

    Se determina por el contexto documental / título de cuadro:
      Cuadro 8.1  -> BASE
      Cuadro 9.11 -> PROYECTO
      Cuadro 9.16 -> MITIGADO

    La continuación de una tabla en la página siguiente conserva el escenario
    del cuadro iniciado en la página anterior.
    """
    scenarios={"ACTUAL":{}, "BASE":{}, "PROYECTO":{}, "MITIGADO":{}}
    source_pages={k:set() for k in scenarios}
    active=None

    def identify(text):
        tl=text.lower()
        # Títulos de cuadro tienen precedencia absoluta.
        if re.search(r"cuadro\s+n?[°º]?\s*9\.16\b", tl):
            return "MITIGADO"
        if re.search(r"cuadro\s+n?[°º]?\s*9\.11\b", tl):
            return "PROYECTO"
        if re.search(r"cuadro\s+n?[°º]?\s*8\.1\b", tl):
            return "BASE"
        # Contexto explícito, útil para tablas que no tengan número reconocible.
        if "situación con proyecto mitigado" in tl or "situacion con proyecto mitigado" in tl:
            return "MITIGADO"
        if "resultados modelación, situación con proyecto" in tl or "resultados modelacion, situacion con proyecto" in tl:
            return "PROYECTO"
        if "resultados modelación, situación base" in tl or "resultados modelacion, situacion base" in tl:
            return "BASE"
        return None

    for i,p in enumerate(pages):
        t=p["text"]
        detected=identify(t)
        if detected:
            active=detected

        # Una página puede ser continuación de la tabla anterior y comenzar
        # directamente con "Arco Grados de saturación...".
        has_gs_header=bool(re.search(r"arco\s+grados?\s+de\s+saturaci[oó]n", t, re.I))
        if not active or not has_gs_header:
            # Si aparece una sección distinta y no hay tabla GS, no reutilizar
            # indefinidamente el escenario activo.
            if detected is None and re.search(r"\b(?:tiempo de viaje|combustible|9\.4|9\.5|10\.)\b", t, re.I):
                active=None
            continue

        rows=_rows_after_header(
            t,
            r"arco\s+grados?\s+de\s+saturaci[oó]n\s*-\s*situaci[oó]n\s+(?:actual|base|proyecto)"
        )
        if rows:
            for arc,pm,pt in rows:
                scenarios[active][arc]={"PM-L":pm,"PT-L":pt,"page":p["page"]}
            source_pages[active].add(p["page"])

    return scenarios, source_pages

def technical_checks(pages, selected):
    confirmed, alerts, conforms = [], [], []

    # Consistencia documental estricta.
    if "Consistencia documental" in selected:
        concepts = extract_concepts(pages)
        for concept, hits in concepts.items():
            vals = sorted(set(h["value"] for h in hits))
            if len(vals) > 1:
                byval = defaultdict(list)
                for h in hits: byval[h["value"]].append(h)
                ev, pset = [], set()
                for v in vals:
                    h = byval[v][0]
                    pset.add(h["page"])
                    ev.append(f"Valor {v} — pág. {h['page']}: {h['evidence']}")
                confirmed.append({
                    "Página": ", ".join(map(str, sorted(pset))),
                    "Materia": "Consistencia documental",
                    "Hallazgo": f"Se identificaron declaraciones explícitas con valores distintos para «{concept}»: {vals}.",
                    "Evidencia": "\n\n".join(ev),
                    "Comprobación": "Comparación contextual estricta del mismo concepto.",
                    "Clasificación": "INCONSISTENCIA",
                    "Acción requerida": "Verificar el valor correcto y uniformar el estudio."
                })

    scenarios, srcpages = _scenario_tables(pages)

    # Una ficha consolidada por arco/período.
    if "Capacidad y saturación" in selected or "Modelación" in selected:
        arcs = set()
        for scen in scenarios.values():
            arcs |= set(scen.keys())

        for arc in sorted(arcs, key=lambda x:int(x)):
            for period in ["PM-L", "PT-L"]:
                vals = {}
                pages_used = []
                for scen in ["ACTUAL", "BASE", "PROYECTO", "MITIGADO"]:
                    if arc in scenarios[scen]:
                        vals[scen] = scenarios[scen][arc][period]
                        pages_used.append(str(scenarios[scen][arc]["page"]))

                if not vals:
                    continue

                chain = " → ".join(
                    f"{k.title()}={vals[k]}%"
                    for k in ["ACTUAL","BASE","PROYECTO","MITIGADO"] if k in vals
                )
                pg = ", ".join(dict.fromkeys(pages_used))

                # Prioriza comparación Base → Proyecto → Mitigado.
                if all(k in vals for k in ["BASE","PROYECTO","MITIGADO"]):
                    b, p, m = vals["BASE"], vals["PROYECTO"], vals["MITIGADO"]
                    dp = p - b
                    dm = m - p

                    if p > b or p > 85:
                        status = []
                        if p > b:
                            status.append(f"el escenario Proyecto aumenta {dp:+d} puntos porcentuales respecto de Base")
                        if p > 85:
                            status.append(f"Proyecto alcanza {p}%")
                        if m < p:
                            status.append(f"Mitigado reduce {abs(dm)} puntos porcentuales respecto de Proyecto")
                        elif m > p:
                            status.append(f"Mitigado aumenta {dm:+d} puntos porcentuales respecto de Proyecto")
                        else:
                            status.append("Mitigado no modifica el valor respecto de Proyecto")

                        alerts.append({
                            "Página": pg,
                            "Materia": "Evolución de saturación",
                            "Hallazgo": f"Arco {arc} — {period}: " + "; ".join(status) + ".",
                            "Evidencia": f"{chain}.",
                            "Comprobación": "Comparación consolidada del mismo arco y período entre escenarios Base → Proyecto → Mitigado.",
                            "Clasificación": "ALERTA TÉCNICA CONSOLIDADA",
                            "Acción requerida": "Revisar la incidencia atribuible al proyecto y vincular la variación con la medida de mitigación correspondiente.",
                            "_gs_base": b,
                            "_gs_proyecto": p,
                            "_gs_mitigado": m,
                            "_delta_bp": dp,
                            "_delta_pm": dm
                        })

                    if p > 85 and m <= 85:
                        conforms.append({
                            "Página": pg,
                            "Materia": "Efecto de mitigación",
                            "Hallazgo": f"Arco {arc} — {period}: Proyecto={p}% y Mitigado={m}%; la modelación muestra una reducción de {p-m} puntos porcentuales.",
                            "Evidencia": f"{chain}.",
                            "Comprobación": "Comparación numérica del mismo arco/período Proyecto → Mitigado.",
                            "Clasificación": "COMPROBACIÓN NUMÉRICA",
                            "Acción requerida": "Verificar que la medida modelada corresponda a la medida descrita y representada en planos."
                        })
                    elif p > 85 and m > 85:
                        alerts.append({
                            "Página": pg,
                            "Materia": "Efecto de mitigación",
                            "Hallazgo": f"Arco {arc} — {period}: permanece sobre 85% en el escenario mitigado ({p}% → {m}%).",
                            "Evidencia": f"{chain}.",
                            "Comprobación": "Comparación numérica Proyecto → Mitigado.",
                            "Clasificación": "ALERTA TÉCNICA CONSOLIDADA",
                            "Acción requerida": "Revisar la suficiencia de la medida para este arco/período.",
                            "_gs_base": b,
                            "_gs_proyecto": p,
                            "_gs_mitigado": m,
                            "_delta_bp": dp,
                            "_delta_pm": dm
                        })

                # Si no existe cadena completa, conserva solo casos altos y los agrupa.
                else:
                    vmax = max(vals.values())
                    if vmax > 85:
                        alerts.append({
                            "Página": pg,
                            "Materia": "Capacidad y saturación",
                            "Hallazgo": f"Arco {arc} — {period}: se identifican valores que requieren revisión ({chain}).",
                            "Evidencia": f"{chain}.",
                            "Comprobación": "Consolidación de escenarios disponibles para el mismo arco/período.",
                            "Clasificación": "ALERTA TÉCNICA",
                            "Acción requerida": "Completar la trazabilidad entre escenarios y revisar la tabla fuente."
                        })

    # Presencia documental, sin confundirla con conformidad técnica.
    whole = " ".join(p["text"].lower() for p in pages)
    expected = {
        "Aforos":["aforo","conteo vehicular"],
        "Demanda":["generación de viajes","generacion de viajes","demanda"],
        "Modelación":["modelación","modelacion","transyt"],
        "Medidas de mitigación":["medidas de mitigación","medidas de mitigacion","mitigación","mitigacion"],
    }
    for module, terms in expected.items():
        if module in selected and any(t in whole for t in terms):
            conforms.append({
                "Página":"—",
                "Materia":module,
                "Hallazgo":f"Se identificó contenido documental asociado al módulo «{module}».",
                "Evidencia":"Presencia textual detectada.",
                "Comprobación":"Control de presencia; no equivale a validación técnica.",
                "Clasificación":"COMPROBACIÓN DOCUMENTAL",
                "Acción requerida":"Continuar con controles técnicos específicos."
            })

    # Criterio de trabajo:
    # Estado operacional = GS del escenario PROYECTO.
    # Impacto incremental = GS PROYECTO - GS BASE, exclusivamente.
    # No se usan otros porcentajes del texto para calcular el impacto.
    for row in alerts:
        p = row.get("_gs_proyecto")
        b = row.get("_gs_base")
        delta = row.get("_delta_bp")

        if p is not None:
            row["GS Base"] = f"{b/100:.2f}".replace(".", ",") if b is not None else "—"
            row["GS Proyecto"] = f"{p/100:.2f}".replace(".", ",")
            row["Δ Proyecto-Base"] = (f"{delta/100:+.2f}".replace(".", ",")
                                      if delta is not None else "—")

            if p > 100:
                row["Estado operacional"] = "SOBRESATURADO (>1,00)"
            elif p > 85:
                row["Estado operacional"] = "SOBRE UMBRAL (>0,85)"
            else:
                row["Estado operacional"] = "ACEPTABLE (≤0,85)"

            if delta is None or delta <= 0:
                row["Impacto incremental"] = "SIN AUMENTO"
            elif delta >= 10:
                row["Impacto incremental"] = "ALTO (≥0,10)"
            elif delta >= 5:
                row["Impacto incremental"] = "MEDIO (0,05–0,09)"
            else:
                row["Impacto incremental"] = "BAJO (0,01–0,04)"

            # Prioridad de revisión: estado e impacto siguen siendo columnas separadas.
            if p > 100 or (delta is not None and delta >= 10):
                row["Prioridad"] = "ALTA"
            elif p > 85 or (delta is not None and delta >= 5):
                row["Prioridad"] = "MEDIA"
            else:
                row["Prioridad"] = "REVISIÓN"
        else:
            # Cadena incompleta: no se inventa Base→Proyecto.
            row["GS Base"] = "—"
            row["GS Proyecto"] = "—"
            row["Δ Proyecto-Base"] = "—"
            row["Estado operacional"] = "REQUIERE TRAZABILIDAD"
            row["Impacto incremental"] = "NO CALCULABLE"
            row["Prioridad"] = "REVISIÓN"

    for row in confirmed:
        row["Prioridad"] = "ALTA"
        row["Estado operacional"] = "—"
        row["Impacto incremental"] = "—"
        row["GS Base"] = "—"
        row["GS Proyecto"] = "—"
        row["Δ Proyecto-Base"] = "—"
    for row in conforms:
        row["Prioridad"] = "—"
        row["Estado operacional"] = "—"
        row["Impacto incremental"] = "—"
        row["GS Base"] = "—"
        row["GS Proyecto"] = "—"
        row["Δ Proyecto-Base"] = "—"


    # --- MÓDULO 1.0: FLUJOS INDUCIDOS Y DISTRIBUCIÓN ---
    # Se valida aritmética de porcentajes x total cuando la tabla está explícitamente
    # identificada. No se infieren rutas ni valores faltantes.
    if "Demanda" in selected:
        for pge in pages:
            txt = pge["text"]

            # Totales de distribución PM/PT detectados en las tablas 9.9 y 9.10.
            if "VIAJES INDUCIDOS PUNTA MAÑANA" in txt.upper():
                mt = re.search(r"total\s+entrada\s+(\d+)\s+total\s+salida\s+(\d+)", txt, re.I)
                if mt:
                    ent, sal = int(mt.group(1)), int(mt.group(2))
                    conforms.append({
                        "Página":str(pge["page"]), "Materia":"Demanda / distribución",
                        "Hallazgo":f"Punta Mañana: total entrada={ent} viajes/h y total salida={sal} viajes/h.",
                        "Evidencia":snippet(txt, mt.start(), mt.end(), 260),
                        "Comprobación":"Extracción de totales declarados en la tabla de distribución de flujos.",
                        "Clasificación":"COMPROBACIÓN NUMÉRICA",
                        "Acción requerida":"Contrastar estos totales con los flujos inducidos que alimentan la modelación.",
                        "Prioridad":"—","Estado operacional":"—","Impacto incremental":"—",
                        "GS Base":"—","GS Proyecto":"—","Δ Proyecto-Base":"—"
                    })

            if "VIAJES INDUCIDOS PUNTA TARDE" in txt.upper():
                mt = re.search(r"total\s+entrada\s+(\d+)\s+total\s+salida\s+(\d+)", txt, re.I)
                if mt:
                    ent, sal = int(mt.group(1)), int(mt.group(2))
                    conforms.append({
                        "Página":str(pge["page"]), "Materia":"Demanda / distribución",
                        "Hallazgo":f"Punta Tarde: total entrada={ent} viajes/h y total salida={sal} viajes/h.",
                        "Evidencia":snippet(txt, mt.start(), mt.end(), 260),
                        "Comprobación":"Extracción de totales declarados en la tabla de distribución de flujos.",
                        "Clasificación":"COMPROBACIÓN NUMÉRICA",
                        "Acción requerida":"Contrastar estos totales con los flujos inducidos que alimentan la modelación.",
                        "Prioridad":"—","Estado operacional":"—","Impacto incremental":"—",
                        "GS Base":"—","GS Proyecto":"—","Δ Proyecto-Base":"—"
                    })

    # --- MÓDULO 1.0: TIEMPOS DE VIAJE DE RED ---
    if "Modelación" in selected:
        for pge in pages:
            txt = pge["text"]
            if "Tiempos de viaje Transporte Privado" in txt:
                m = re.search(r"PROYECTO\s+PM-L\s+(\d+).*?PT-L\s+(\d+).*?Total\s+(\d+)", txt, re.I|re.S)
                if m:
                    pm, pt, total = map(int, m.groups())
                    ok = (pm + pt == total)
                    target = conforms if ok else confirmed
                    target.append({
                        "Página":str(pge["page"]), "Materia":"Modelación / tiempo de viaje",
                        "Hallazgo":f"Transporte privado: PM-L={pm}, PT-L={pt}, total informado={total}.",
                        "Evidencia":snippet(txt, m.start(), m.end(), 220),
                        "Comprobación":f"Suma automática: {pm}+{pt}={pm+pt}; total informado={total}.",
                        "Clasificación":"COMPROBACIÓN NUMÉRICA" if ok else "ERROR ARITMÉTICO",
                        "Acción requerida":"Mantener trazabilidad." if ok else "Revisar el total informado y resultados dependientes.",
                        "Prioridad":"—" if ok else "ALTA","Estado operacional":"—","Impacto incremental":"—",
                        "GS Base":"—","GS Proyecto":"—","Δ Proyecto-Base":"—"
                    })

    # Colas/demoras: la versión 1.0 no inventa datos si no identifica tablas inequívocas.
    whole_low = " ".join(p["text"].lower() for p in pages)
    if "Modelación" in selected:
        if not ("longitud de cola" in whole_low or "longitudes de cola" in whole_low):
            alerts.append({
                "Página":"—","Materia":"Modelación / colas",
                "Hallazgo":"No se identificó una tabla textual inequívoca de longitudes de cola para integrar al cruce por arco/período.",
                "Evidencia":"Búsqueda documental automática.",
                "Comprobación":"Control de disponibilidad del indicador; no se inventan valores.",
                "Clasificación":"REQUIERE REVISIÓN PROFESIONAL",
                "Acción requerida":"Verificar anexos/modelación o tablas no extraíbles como texto.",
                "Prioridad":"REVISIÓN","Estado operacional":"—","Impacto incremental":"NO CALCULABLE",
                "GS Base":"—","GS Proyecto":"—","Δ Proyecto-Base":"—"
            })


    for prefix, rows in [("OBS",confirmed),("ALT",alerts),("CHK",conforms)]:
        for i,row in enumerate(rows,1):
            row["ID"]=f"{prefix}-{i:03d}"
    return confirmed, alerts, conforms


def _strict_scenario_tables(pages):
    """
    1.5: usa exclusivamente las tablas identificadas por encabezado de escenario.
    No desplaza valores entre columnas ni infiere Proyecto a partir de Mitigado.
    """
    scenarios, source_pages = _scenario_tables(pages)
    out = {}
    source_names = {
        "BASE": "Cuadro 8.1",
        "PROYECTO": "Cuadro 9.11",
        "MITIGADO": "Cuadro 9.16",
        "ACTUAL": "Situación Actual"
    }
    for scen, arcs in scenarios.items():
        out[scen] = {}
        for arc, vals in arcs.items():
            copied = dict(vals)
            copied["source"] = copied.get("source") or source_names.get(scen, scen)
            out[scen][arc] = copied
    return out, source_pages

def build_arc_sheet(pages):
    scenarios, _ = _strict_scenario_tables(pages)
    rows = []
    arcs = set()
    for scen in scenarios.values():
        arcs |= set(scen.keys())

    for arc in sorted(arcs, key=lambda x:int(x)):
        for period in ["PM-L", "PT-L"]:
            def val(s):
                return scenarios[s].get(arc, {}).get(period)
            def pg(s):
                return scenarios[s].get(arc, {}).get("page")

            b, p, m = val("BASE"), val("PROYECTO"), val("MITIGADO")
            if b is None and p is None and m is None:
                continue

            delta = (p-b) if (b is not None and p is not None) else None
            mit_delta = (m-p) if (m is not None and p is not None) else None

            if p is None:
                state = "REQUIERE TRAZABILIDAD"
            elif p > 100:
                state = "SOBRESATURADO (>1,00)"
            elif p > 85:
                state = "SOBRE UMBRAL (>0,85)"
            else:
                state = "ACEPTABLE (≤0,85)"

            if delta is None:
                impact = "NO CALCULABLE"
            elif delta <= 0:
                impact = "SIN AUMENTO"
            elif delta >= 10:
                impact = "ALTO (≥0,10)"
            elif delta >= 5:
                impact = "MEDIO (0,05–0,09)"
            else:
                impact = "BAJO (0,01–0,04)"

            # Evaluación reglamentaria GS — art. 3.6.11 letra b), DS N°30.
            if b is None or p is None or m is None:
                priority = "REQUIERE REVISIÓN PROFESIONAL"
            elif b <= 85:
                if p <= 85:
                    priority = "SIN OBSERVACIÓN NORMATIVA"
                elif m <= 85:
                    priority = "MITIGACIÓN RESTABLECE UMBRAL"
                else:
                    priority = "OBSERVACIÓN NORMATIVA"
            else:
                if m <= b + 1:
                    priority = "CONDICIÓN BASE >85% — CUMPLE REGLA +1%"
                else:
                    priority = "OBSERVACIÓN NORMATIVA"

            if p is not None and m is not None:
                if m < p:
                    effect = f"Reduce {p-m} pp"
                elif m > p:
                    effect = f"Aumenta {m-p} pp"
                else:
                    effect = "Sin variación"
            else:
                effect = "NO CALCULABLE"

            pages_used = [str(x) for x in [pg("BASE"),pg("PROYECTO"),pg("MITIGADO")] if x]
            base_meta = scenarios.get("BASE", {}).get(arc, {})
            proj_meta = scenarios.get("PROYECTO", {}).get(arc, {})
            mit_meta = scenarios.get("MITIGADO", {}).get(arc, {})

            rows.append({
                "Arco": arc,
                "Período": period,
                "GS Base": "—" if b is None else f"{b/100:.2f}".replace(".",","),
                "GS Proyecto": "—" if p is None else f"{p/100:.2f}".replace(".",","),
                "Δ Proyecto-Base": "—" if delta is None else f"{delta/100:+.2f}".replace(".",","),
                "GS Mitigado": "—" if m is None else f"{m/100:.2f}".replace(".",","),
                "Δ Mitigado-Proyecto": "—" if mit_delta is None else f"{mit_delta/100:+.2f}".replace(".",","),
                "Estado operacional": state,
                "Impacto incremental": impact,
                "Efecto mitigación": effect,
                "Prioridad": priority,
                "Fuente Base": base_meta.get("source", "—"),
                "Página Base": base_meta.get("page", "—"),
                "Fuente Proyecto": proj_meta.get("source", "—"),
                "Página Proyecto": proj_meta.get("page", "—"),
                "Fuente Mitigado": mit_meta.get("source", "—"),
                "Página Mitigado": mit_meta.get("page", "—"),
                "Página(s)": ", ".join(dict.fromkeys(pages_used)) or "—"
            })
    return rows


def build_behavior_alerts(pages):
    """
    Alertas técnicas independientes del cumplimiento normativo.
    No se presentan como incumplimiento.

    Regla 1.7:
    - Si el escenario mitigado empeora el GS respecto del Proyecto:
      +0,01 a +0,04 -> BAJA
      +0,05 a +0,09 -> MEDIA
      >= +0,10 -> ALTA
    """
    sheet = build_arc_sheet(pages)
    rows=[]
    n=1
    for r in sheet:
        try:
            p=float(str(r["GS Proyecto"]).replace(",", "."))
            m=float(str(r["GS Mitigado"]).replace(",", "."))
        except Exception:
            continue
        d=m-p
        if d <= 0:
            continue
        if d >= 0.10:
            level="ALTA"
        elif d >= 0.05:
            level="MEDIA"
        else:
            level="BAJA"
        rows.append({
            "N°":n,
            "Nivel":level,
            "Arco":r["Arco"],
            "Período":r["Período"],
            "GS Proyecto":r["GS Proyecto"],
            "GS Mitigado":r["GS Mitigado"],
            "Δ Mitigado-Proyecto":f"+{d:.2f}".replace(".", ","),
            "Fuente Proyecto":r.get("Fuente Proyecto", "—"),
            "Página Proyecto":r.get("Página Proyecto", "—"),
            "Fuente Mitigado":r.get("Fuente Mitigado", "—"),
            "Página Mitigado":r.get("Página Mitigado", "—"),
            "Alerta técnica":(
                f"El escenario mitigado aumenta el grado de saturación en {d*100:.0f} "
                + ("punto porcentual" if round(d*100) == 1 else "puntos porcentuales")
                + " respecto del escenario Proyecto."
            ),
            "Acción de revisión":(
                "Verificar la causa del aumento, la codificación de la medida de mitigación "
                "y la coherencia de la modelación. Esta alerta no constituye por sí sola "
                "un incumplimiento normativo."
            )
        })
        n+=1
    return rows

def build_consultant_matrix(pages):
    sheet = build_arc_sheet(pages)
    rows = []
    n = 1
    for r in sheet:
        decision = r["Prioridad"]
        if decision not in ["OBSERVACIÓN NORMATIVA", "REQUIERE REVISIÓN PROFESIONAL"]:
            continue
        evidence = (
            f"GS Base={r['GS Base']}; GS Proyecto={r['GS Proyecto']}; "
            f"Δ Proyecto-Base={r['Δ Proyecto-Base']}; GS Mitigado={r['GS Mitigado']}; "
            f"Δ Mitigado-Proyecto={r['Δ Mitigado-Proyecto']}."
        )
        if decision == "OBSERVACIÓN NORMATIVA":
            obs = (f"Arco {r['Arco']} — {r['Período']}: revisar los grados de saturación "
                   "informados conforme al parámetro reglamentario de semejanza.")
            action = ("Revisar la modelación y acreditar el cumplimiento del artículo 3.6.11 letra b) "
                      "del DS N°30: si Base no supera 85%, cuando Proyecto supera 85% la mitigación "
                      "debe disminuir el GS hasta 85% o menos; si Base ya supera 85%, el GS mitigado "
                      "no debe aumentar más de 1 punto porcentual respecto de Base.")
        else:
            obs = (f"Arco {r['Arco']} — {r['Período']}: no fue posible reconstruir de forma "
                   "inequívoca Base → Proyecto → Mitigado.")
            action = "Completar la trazabilidad antes de concluir cumplimiento reglamentario."
        rows.append({
            "N°":n,"Clasificación":decision,"Arco":r["Arco"],"Período":r["Período"],
            "Fuente Base":r.get("Fuente Base", "—"),
            "Página Base":r.get("Página Base", "—"),
            "Fuente Proyecto":r.get("Fuente Proyecto", "—"),
            "Página Proyecto":r.get("Página Proyecto", "—"),
            "Fuente Mitigado":r.get("Fuente Mitigado", "—"),
            "Página Mitigado":r.get("Página Mitigado", "—"),
            "Antecedente revisado":"Grado de saturación — art. 3.6.11 letra b), DS N°30",
            "Observación":obs,"Evidencia numérica":evidence,
            "Efecto mitigación":r["Efecto mitigación"],"Acción requerida":action})
        n += 1
    return rows


def _table_block(text, table_no):
    pat = re.compile(
        rf"Cuadro\s+N?[°º]?\s*{re.escape(table_no)}\s*:(.*?)(?=Cuadro\s+N?[°º]?\s*\d+\.\d+\s*:|$)",
        re.I | re.S
    )
    m = pat.search(text)
    return m.group(1) if m else ""

def _norm_tokens(block):
    # Normaliza espacios/saltos de línea, conservando el orden de lectura del PDF.
    return re.sub(r"\s+", " ", block).strip()

def _row_values_between_labels(block, label, next_labels):
    """
    Extrae números después de una etiqueta de fila y antes de la siguiente
    etiqueta conocida. No depende de que la fila empiece en una línea física.
    Si no puede delimitar inequívocamente, devuelve [].
    """
    flat=_norm_tokens(block)
    label_pat=rf"(?<![\w-]){re.escape(label)}(?![\w-])"
    matches=list(re.finditer(label_pat, flat, re.I))
    if len(matches) != 1:
        return []
    a=matches[0].end()
    b=len(flat)
    for nxt in next_labels:
        nm=re.search(rf"(?<![\w-]){re.escape(nxt)}(?![\w-])", flat[a:], re.I)
        if nm:
            b=min(b, a+nm.start())
    segment=flat[a:b]
    vals=[]
    for x in re.findall(r"(?<![\w$])\d+(?:[.,]\d+)?", segment):
        try:
            vals.append(float(x.replace(".","").replace(",",".")))
        except Exception:
            pass
    return vals

def _extract_three_rows(block):
    """
    Reconstruye PM-L, PT-L y Total por posición relativa de etiquetas.
    Exige exactamente una aparición de cada etiqueta.
    """
    flat=_norm_tokens(block)
    labels=["PM-L","PT-L","Total"]
    pos={}
    for lab in labels:
        ms=list(re.finditer(rf"(?<![\w-]){re.escape(lab)}(?![\w-])", flat, re.I))
        if len(ms)!=1:
            return [],[],[]
        pos[lab]=ms[0]
    if not (pos["PM-L"].start() < pos["PT-L"].start() < pos["Total"].start()):
        return [],[],[]
    def nums(a,b):
        seg=flat[a:b]
        out=[]
        for x in re.findall(r"(?<![\w$])\d+(?:[.,]\d+)?", seg):
            try: out.append(float(x.replace(".","").replace(",",".")))
            except: pass
        return out
    pm=nums(pos["PM-L"].end(),pos["PT-L"].start())
    pt=nums(pos["PT-L"].end(),pos["Total"].start())
    total=nums(pos["Total"].end(),len(flat))
    return pm,pt,total

def deterministic_arithmetic_checks(pages):
    """
    Recalcula Cuadros 9.12–9.15 usando patrones específicos de la estructura
    documental observada. No usa costos monetarios en las operaciones.
    """
    results=[]
    full="\n".join(p["text"] for p in pages)

    def page_for(table_no):
        for pg in pages:
            if re.search(rf"Cuadro\s+N?[°º]?\s*{re.escape(table_no)}\s*:", pg["text"], re.I):
                return pg["page"]
        return "—"

    def block(table_no):
        return _table_block(full, table_no)

    def vals_time(b):
        flat=_norm_tokens(b)
        m=re.search(
            r"PM-L\s+(\d+(?:[.,]\d+)?)\s+\$\s*[\d.]+\s+"
            r"PT-L\s+(\d+(?:[.,]\d+)?)\s+\$\s*[\d.]+\s+"
            r"Total\s+(\d+(?:[.,]\d+)?)\s+\$",
            flat,re.I)
        return tuple(float(x.replace(",",".")) for x in m.groups()) if m else None

    def vals_fuel(b):
        flat=_norm_tokens(b)
        m=re.search(
            r"PM-L\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s+\$\s*[\d.]+\s+"
            r"PT-L\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s+\$\s*[\d.]+\s+"
            r"Total\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s+\$",
            flat,re.I)
        return tuple(float(x.replace(",",".")) for x in m.groups()) if m else None

    for no,matter in [("9.12","Tiempo de viaje transporte privado"),
                      ("9.13","Tiempo de viaje transporte público")]:
        v=vals_time(block(no))
        if not v: continue
        pm,pt,tot=v; calc=pm+pt; ok=abs(calc-tot)<0.001
        results.append({
            "ID":f"AR-{no}","Página":page_for(no),"Fuente":f"Cuadro {no}",
            "Materia":matter,"Comprobación":f"{pm:g} + {pt:g} = {calc:g}",
            "Total informado":f"{tot:g}","Diferencia":f"{tot-calc:+g}",
            "Clasificación":"COMPROBACIÓN CORRECTA" if ok else "OBSERVACIÓN CONFIRMADA",
            "Observación":"La suma de los períodos coincide con el total informado." if ok
                else f"El total informado ({tot:g}) no coincide con la suma PM-L + PT-L ({calc:g})."
        })

    for no,matter in [("9.14","Consumo combustible transporte privado"),
                      ("9.15","Consumo combustible transporte público")]:
        v=vals_fuel(block(no))
        if not v: continue
        pm_m,pm_r,pm_t,pt_m,pt_r,pt_t,t_m,t_r,t_t=v
        checks=[
            ("PM-L: Marcha + Ralentí = Total",pm_m+pm_r,pm_t),
            ("PT-L: Marcha + Ralentí = Total",pt_m+pt_r,pt_t),
            ("Total Marcha: PM-L + PT-L",pm_m+pt_m,t_m),
            ("Total Ralentí: PM-L + PT-L",pm_r+pt_r,t_r),
            ("Total general: PM-L + PT-L",pm_t+pt_t,t_t),
        ]
        for j,(label,calc,inf) in enumerate(checks,1):
            ok=abs(calc-inf)<0.001
            results.append({
                "ID":f"AR-{no}-{j}","Página":page_for(no),"Fuente":f"Cuadro {no}",
                "Materia":matter,"Comprobación":f"{label}: calculado {calc:g}",
                "Total informado":f"{inf:g}","Diferencia":f"{inf-calc:+g}",
                "Clasificación":"COMPROBACIÓN CORRECTA" if ok else "OBSERVACIÓN CONFIRMADA",
                "Observación":"La operación aritmética coincide con el valor informado." if ok
                    else f"El valor informado ({inf:g}) no coincide con el valor recalculado ({calc:g})."
            })
    return results

def analyze(pages, selected):
    return technical_checks(pages, selected)

def make_pdf(project,source,n_pages,obs):
    """Informe técnico 2.1: salida legible, trazable y separada por naturaleza del hallazgo."""
    b=io.BytesIO()
    doc=SimpleDocTemplate(
        b,pagesize=A4,rightMargin=1.35*cm,leftMargin=1.35*cm,
        topMargin=1.35*cm,bottomMargin=1.35*cm,
        title=f"Informe técnico de revisión vial - {project}"
    )
    ss=getSampleStyleSheet()
    title=ParagraphStyle("t21",parent=ss["Title"],alignment=TA_CENTER,fontSize=16,leading=19,spaceAfter=8)
    subtitle=ParagraphStyle("sub21",parent=ss["BodyText"],alignment=TA_CENTER,fontSize=9,leading=12,textColor=colors.grey)
    body=ParagraphStyle("b21",parent=ss["BodyText"],fontSize=8.5,leading=11)
    small=ParagraphStyle("s21",parent=ss["BodyText"],fontSize=6.5,leading=8.2,wordWrap="LTR")
    cell=ParagraphStyle("c21",parent=small,fontSize=6.2,leading=7.7,wordWrap="LTR")
    h1=ParagraphStyle("h121",parent=ss["Heading1"],fontSize=13,leading=16,spaceBefore=8,spaceAfter=7)
    h2=ParagraphStyle("h221",parent=ss["Heading2"],fontSize=11.5,leading=14,spaceBefore=8,spaceAfter=6)

    confirmed=[x for x in obs if "OBSERVACIÓN CONFIRMADA" in str(x.get("Clasificación",""))]
    alerts=[x for x in obs if "ALERTA" in str(x.get("Clasificación",""))]
    checks=[x for x in obs if "COMPROBACIÓN" in str(x.get("Clasificación",""))]

    story=[
        Spacer(1,1.1*cm),
        Paragraph("INFORME TÉCNICO DE REVISIÓN VIAL",title),
        Paragraph("IA Revisor Vial — Versión 2.1",subtitle),Spacer(1,14),
        Paragraph(f"<b>Proyecto:</b> {project}",body),
        Paragraph(f"<b>Documento revisado:</b> {source}",body),
        Paragraph(f"<b>Extensión:</b> {n_pages} páginas",body),Spacer(1,10),
        Paragraph("<b>Alcance.</b> Revisión automatizada basada en evidencia extraída del estudio, controles determinísticos y reglas técnicas activas. Una alerta técnica no se califica por sí sola como incumplimiento normativo. La ausencia de observaciones tampoco equivale a una aprobación técnica integral.",body),
        Spacer(1,16),Paragraph("Resumen ejecutivo",h1)
    ]
    summary=[
        [Paragraph("<b>Categoría</b>",small),Paragraph("<b>Cantidad</b>",small),Paragraph("<b>Interpretación</b>",small)],
        [Paragraph("Observaciones confirmadas",small),str(len(confirmed)),Paragraph("Diferencias demostradas mediante evidencia o recálculo determinístico.",small)],
        [Paragraph("Alertas técnicas",small),str(len(alerts)),Paragraph("Situaciones que requieren revisión profesional; no equivalen automáticamente a incumplimiento normativo.",small)],
        [Paragraph("Comprobaciones",small),str(len(checks)),Paragraph("Controles numéricos o documentales trazables que no presentan diferencia en la regla comprobada.",small)],
    ]
    ts=Table(summary,colWidths=[4.2*cm,2.0*cm,10.4*cm],repeatRows=1)
    ts.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),.35,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
        ("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(1,1),(1,-1),"CENTER"),
        ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)
    ]))
    story += [ts,Spacer(1,12)]
    if confirmed:
        story.append(Paragraph(f"Se identificaron <b>{len(confirmed)} observaciones confirmadas</b> que deben ser corregidas o aclaradas por el consultor. Las alertas técnicas se presentan separadamente para evitar confundir una condición de revisión con un incumplimiento demostrado.",body))
    else:
        story.append(Paragraph("No se identificaron observaciones confirmadas con las reglas automáticas activas. Las alertas técnicas, si existen, se mantienen separadas para revisión profesional.",body))

    def esc(v):
        return str(v if v not in (None,"") else "—").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br/>")

    def obs_table(items):
        rows=[[Paragraph("<b>ID</b>",cell),Paragraph("<b>Pág.</b>",cell),Paragraph("<b>Materia</b>",cell),
               Paragraph("<b>Observación</b>",cell),Paragraph("<b>Comprobación / evidencia</b>",cell),Paragraph("<b>Acción requerida</b>",cell)]]
        for x in items:
            ev=x.get("Comprobación","") or x.get("Evidencia","")
            rows.append([Paragraph(esc(x.get("ID","")),cell),Paragraph(esc(x.get("Página","—")),cell),
                         Paragraph(esc(x.get("Materia","")),cell),Paragraph(esc(x.get("Hallazgo","")),cell),
                         Paragraph(esc(ev),cell),Paragraph(esc(x.get("Acción requerida","")),cell)])
        t=Table(rows,colWidths=[1.25*cm,1.35*cm,2.45*cm,5.25*cm,3.45*cm,3.05*cm],repeatRows=1,hAlign="LEFT")
        t.setStyle(TableStyle([
            ("GRID",(0,0),(-1,-1),.3,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
            ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),
            ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)
        ]))
        return t

    story += [PageBreak(),Paragraph("1. Observaciones confirmadas",h1),
              Paragraph("Hallazgos demostrados mediante evidencia o recálculo determinístico. Se presentan como materias que requieren corrección, aclaración o justificación del consultor.",body),Spacer(1,6)]
    if confirmed: story.append(obs_table(confirmed))
    else: story.append(Paragraph("No se registraron observaciones confirmadas.",body))

    story += [PageBreak(),Paragraph("2. Alertas técnicas",h1),
              Paragraph("Condiciones que requieren revisión profesional. Estas alertas no constituyen, por sí solas, un incumplimiento normativo.",body),Spacer(1,6)]
    if alerts: story.append(obs_table(alerts))
    else: story.append(Paragraph("No se registraron alertas técnicas.",body))

    story += [PageBreak(),Paragraph("3. Comprobaciones",h1),
              Paragraph("Controles utilizados para verificar trazabilidad y consistencia. Se incorporan como anexo de respaldo y no como observaciones al consultor.",body),Spacer(1,6)]
    if checks: story.append(obs_table(checks))
    else: story.append(Paragraph("No se registraron comprobaciones.",body))

    story += [PageBreak(),Paragraph("4. Trazabilidad de observaciones confirmadas",h1)]
    if not confirmed:
        story.append(Paragraph("Sin observaciones confirmadas para detallar.",body))
    for x in confirmed:
        story += [Paragraph(f"{esc(x.get('ID',''))} — {esc(x.get('Materia',''))}",h2),
                  Paragraph(f"<b>Página(s):</b> {esc(x.get('Página','—'))}",body),
                  Paragraph(f"<b>Hallazgo:</b> {esc(x.get('Hallazgo',''))}",body),
                  Paragraph(f"<b>Comprobación:</b> {esc(x.get('Comprobación',''))}",body),
                  Paragraph(f"<b>Evidencia:</b> {esc(x.get('Evidencia',''))}",body),
                  Paragraph(f"<b>Acción requerida:</b> {esc(x.get('Acción requerida',''))}",body),Spacer(1,10)]

    story += [Spacer(1,8),Paragraph("Nota metodológica",h2),
              Paragraph("El informe distingue expresamente entre observaciones confirmadas, alertas técnicas y comprobaciones. Sólo se formula un incumplimiento normativo cuando existe una regla aplicable y una fuente normativa suficientemente trazable; en caso contrario, el resultado permanece como alerta o materia de revisión profesional.",body)]
    doc.build(story)
    return b.getvalue()

with st.sidebar:
    st.header("Caso")
    project=st.text_input("Nombre","Caso Piloto 001")
    up=st.file_uploader("Estudio PDF",type=["pdf"])
    st.header("Módulos")
    selected=[m for m in MODULES if st.checkbox(m,True,key=m)]
    st.info("Regla 0.3: si no existe evidencia suficiente para demostrar un hallazgo, no se formula como observación.")

if not up:
    st.info("Carga un estudio en PDF para comenzar."); st.stop()

pages=extract_pdf(up.getvalue())
st.success(f"Documento cargado: {len(pages)} páginas")
a,b,c=st.columns(3); a.metric("Páginas",len(pages)); b.metric("Módulos seleccionados",len(selected)); c.metric("Proyecto",project)

# Versión 2.0: el motor técnico no depende de que el usuario pulse el botón
# después de cada despliegue. Se recalcula automáticamente cuando cambia
# el PDF o la selección de módulos. El botón permite forzar el recálculo.
import hashlib
_analysis_key = hashlib.sha256(up.getvalue()).hexdigest() + "|" + "|".join(sorted(selected))
_force_analysis = st.button("Analizar estudio", type="primary")
if _force_analysis or st.session_state.get("analysis_key") != _analysis_key:
    with st.spinner("Ejecutando revisión técnica trazable..."):
        st.session_state["review04"] = analyze(pages, selected)
        st.session_state["analysis_key"] = _analysis_key

confirmed, alerts, conforms = st.session_state.get("review04", ([], [], []))

# Integración 1.9.6: el módulo aritmético validado alimenta el resumen general.
arithmetic_summary = deterministic_arithmetic_checks(pages)
arithmetic_confirmed = [
    r for r in arithmetic_summary
    if r.get("Clasificación") == "OBSERVACIÓN CONFIRMADA"
]

# Adaptación al esquema común del informe, sin modificar el parser aritmético.
arithmetic_report = []
for r in arithmetic_confirmed:
    arithmetic_report.append({
        "ID": r.get("ID",""),
        "Prioridad": "CONFIRMADA",
        "Página": str(r.get("Página","—")),
        "Materia": r.get("Materia","Comprobación aritmética"),
        "Hallazgo": r.get("Observación",""),
        "Evidencia": (
            f'Fuente: {r.get("Fuente","")}. '
            f'Comprobación: {r.get("Comprobación","")}. '
            f'Total informado: {r.get("Total informado","")}. '
            f'Diferencia: {r.get("Diferencia","")}.'
        ),
        "Comprobación": r.get("Comprobación",""),
        "Acción requerida": "Corregir el total informado y verificar la consistencia del cuadro correspondiente.",
        "Clasificación": "OBSERVACIÓN CONFIRMADA"
    })

# Fuente única de resultados 1.9.9.
# Desde este punto, contador, pestañas, CSV y PDF consumen las mismas colecciones.
review_results = {
    "confirmed": confirmed + arithmetic_report,
    "alerts": alerts,
    "checks": conforms,
}

confirmed_all = review_results["confirmed"]
alerts_all = review_results["alerts"]
checks_all = review_results["checks"]

m1, m2, m3 = st.columns(3)
m1.metric("Observaciones confirmadas", len(confirmed_all))
m2.metric("Alertas técnicas", len(alerts_all))
m3.metric("Comprobaciones", len(checks_all))

if alerts_all:
    pa = sum(1 for x in alerts_all if x.get("Prioridad") == "ALTA")
    pm = sum(1 for x in alerts_all if x.get("Prioridad") == "MEDIA")
    pr = sum(1 for x in alerts_all if x.get("Prioridad") == "REVISIÓN")
    st.caption(f"Prioridad de alertas: Alta {pa} · Media {pm} · Revisión {pr}")

tabs = st.tabs(["🔴 Observaciones confirmadas", "🟠 Alertas para revisión", "🟢 Comprobaciones", "📊 Ficha consolidada por arco", "⚠️ Alertas comportamiento", "🧮 Comprobación aritmética", "📋 Matriz normativa consultor"])

def show_rows(rows, empty_msg):
    if not rows:
        st.info(empty_msg)
        return
    df = pd.DataFrame(rows)
    cols = ["ID","Prioridad","GS Base","GS Proyecto","Δ Proyecto-Base","Estado operacional","Impacto incremental","Página","Materia","Hallazgo","Comprobación","Clasificación"]
    cols = [c for c in cols if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)
    chosen = st.selectbox("Ver detalle", [x["ID"] for x in rows], key="detail_"+rows[0]["ID"][:3])
    x = next(y for y in rows if y["ID"] == chosen)
    if "Prioridad" in x:
        st.markdown(f"**Prioridad de revisión:** {x['Prioridad']}")
    if x.get("GS Base","—") != "—":
        st.markdown(f"**GS Base:** {x['GS Base']}  |  **GS Proyecto:** {x['GS Proyecto']}  |  **Δ Proyecto-Base:** {x['Δ Proyecto-Base']}")
    if "Estado operacional" in x and x["Estado operacional"] != "—":
        st.markdown(f"**Estado operacional del escenario Proyecto:** {x['Estado operacional']}")
    if "Impacto incremental" in x and x["Impacto incremental"] != "—":
        st.markdown(f"**Impacto incremental del proyecto:** {x['Impacto incremental']}")
    st.markdown(f"**Página(s):** {x['Página']}")
    st.markdown(f"**Hallazgo:** {x['Hallazgo']}")
    st.markdown(f"**Comprobación:** {x['Comprobación']}")
    st.markdown(f"**Acción requerida:** {x['Acción requerida']}")
    if x.get("Evidencia"):
        st.markdown("**Evidencia:**")
        st.code(x["Evidencia"])

with tabs[0]:
    show_rows(confirmed_all, "No se demostraron observaciones confirmadas con las reglas automáticas activas.")
with tabs[1]:
    show_rows(alerts_all, "No se generaron alertas técnicas con las reglas automáticas activas.")
with tabs[2]:
    show_rows(checks_all, "No se generaron comprobaciones trazables con las reglas automáticas activas.")

# Exportación e informe desde la misma fuente única.
all_report = confirmed_all + alerts_all + checks_all
if all_report:
    df_all = pd.DataFrame(all_report)
    st.divider()
    c1, c2 = st.columns(2)
    c1.download_button(
        "Exportar revisión completa CSV",
        df_all.to_csv(index=False).encode("utf-8-sig"),
        "revision_tecnica_revisor_vial.csv", "text/csv"
    )
    c2.download_button(
        "📄 Generar Informe Técnico 2.1 (PDF)",
        make_pdf(project, up.name, len(pages), all_report),
        "informe_tecnico_revision_vial.pdf", "application/pdf"
    )

st.caption("Criterio de trabajo: GS Proyecto ≤ 0,85 aceptable; >0,85 sobre umbral; >1,00 sobresaturado. El impacto se calcula únicamente como GS Proyecto − GS Base. No se usan otros porcentajes de la evidencia para clasificar el impacto.")



with tabs[3]:
    sheet = build_arc_sheet(pages)
    if sheet:
        df_sheet = pd.DataFrame(sheet)
        st.caption("Una fila por arco y período. Los valores se vinculan únicamente cuando Base, Proyecto y/o Mitigado fueron extraídos de tablas identificables.")
        st.dataframe(df_sheet, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar ficha consolidada CSV",
            df_sheet.to_csv(index=False).encode("utf-8-sig"),
            file_name="ficha_consolidada_arcos_v18_1.csv",
            mime="text/csv"
        )
    else:
        st.info("No se identificaron tablas de GS suficientes para construir la ficha consolidada.")



with tabs[4]:
    behavior = build_behavior_alerts(pages)
    st.caption("Alertas técnicas por comportamiento anómalo del escenario mitigado. No equivalen automáticamente a incumplimiento normativo.")
    if behavior:
        df_behavior = pd.DataFrame(behavior)
        st.dataframe(df_behavior, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar alertas de comportamiento CSV",
            df_behavior.to_csv(index=False).encode("utf-8-sig"),
            file_name="alertas_comportamiento_v18_1.csv",
            mime="text/csv"
        )
    else:
        st.success("No se detectaron aumentos del GS entre Proyecto y Mitigado.")

with tabs[5]:
    arithmetic = arithmetic_summary
    st.caption("Recalculo determinístico de totales. Una diferencia aritmética se clasifica como observación confirmada; no depende de interpretación normativa.")
    if arithmetic:
        df_arith = pd.DataFrame(arithmetic)
        st.dataframe(df_arith, use_container_width=True, hide_index=True)
        confirmed_arith = df_arith[df_arith["Clasificación"] == "OBSERVACIÓN CONFIRMADA"]
        st.metric("Errores aritméticos confirmados", len(confirmed_arith))
        st.download_button(
            "Descargar comprobación aritmética CSV",
            df_arith.to_csv(index=False).encode("utf-8-sig"),
            file_name="comprobacion_aritmetica_v19_5.csv",
            mime="text/csv"
        )
    else:
        st.info("No se identificaron las tablas 9.12 a 9.15 con estructura suficiente para recalcular.")

with tabs[6]:
    matrix = build_consultant_matrix(pages)
    st.caption("Matriz reglamentaria de GS. Sólo incluye observaciones normativas o casos sin trazabilidad suficiente; las alertas internas no se convierten automáticamente en incumplimientos.")
    if matrix:
        df_matrix = pd.DataFrame(matrix)
        st.dataframe(df_matrix, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar matriz de observaciones CSV",
            df_matrix.to_csv(index=False).encode("utf-8-sig"),
            file_name="matriz_normativa_consultor_v18_1.csv",
            mime="text/csv"
        )
    else:
        st.success("No se generaron observaciones de GS para remitir al consultor con los criterios actuales.")

