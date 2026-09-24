
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
st.title("🛣️ IA Revisor Vial — Prototipo 0.8")
st.caption("Revisión operacional: usa GS ≤ 0,85 como umbral aceptable y separa estado operacional del impacto incremental del proyecto.")

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
    scenarios = {"ACTUAL": {}, "BASE": {}, "PROYECTO": {}, "MITIGADO": {}}
    source_pages = {}
    for p in pages:
        t = p["text"]
        tl = t.lower()
        scen = None
        if "grados de saturación - situación actual" in tl or "grados de saturacion - situacion actual" in tl:
            scen = "ACTUAL"
        elif "grados de saturación - situación base" in tl or "grados de saturacion - situacion base" in tl:
            scen = "BASE"
        elif ("situación con proyecto mitigado" in tl or "situacion con proyecto mitigado" in tl) and \
             ("grados de saturación" in tl or "grados de saturacion" in tl):
            scen = "MITIGADO"
        elif "grados de saturación - situación proyecto" in tl or "grados de saturacion - situacion proyecto" in tl:
            # Pages explicitly headed as mitigated take precedence.
            scen = "MITIGADO" if ("proyecto mitigado" in tl) else "PROYECTO"

        if scen:
            rows = _rows_after_header(
                t, r"grados?\s+de\s+saturaci[oó]n\s*-\s*situaci[oó]n\s+(?:actual|base|proyecto)"
            )
            for arc, pm, pt in rows:
                scenarios[scen][arc] = {"PM-L": pm, "PT-L": pt, "page": p["page"]}
            source_pages.setdefault(scen, set()).add(p["page"])
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
                            "Acción requerida": "Revisar la incidencia atribuible al proyecto y vincular la variación con la medida de mitigación correspondiente."
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
                            "Acción requerida": "Revisar la suficiencia de la medida para este arco/período."
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

    # Criterio de trabajo definido para este revisor:
    # GS <= 0,85: aceptable; GS > 0,85: alerta; GS > 1,00: sobresaturado.
    # Se separa el estado operacional del impacto incremental Base→Proyecto.
    for row in alerts:
        txt = (row.get("Hallazgo","") + " " + row.get("Evidencia","")).lower()
        nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,3})\s*%", txt)]
        deltas = [abs(int(x)) for x in re.findall(r"([+-]\d+)\s+puntos", txt)]
        maxpct = max(nums) if nums else 0
        maxdelta = max(deltas) if deltas else 0

        if maxpct > 100:
            row["Estado operacional"] = "SOBRESATURADO (>1,00)"
        elif maxpct > 85:
            row["Estado operacional"] = "SOBRE UMBRAL (>0,85)"
        else:
            row["Estado operacional"] = "ACEPTABLE (≤0,85)"

        if maxdelta >= 10:
            row["Impacto incremental"] = "ALTO (≥10 pp)"
        elif maxdelta >= 5:
            row["Impacto incremental"] = "MEDIO (5–9 pp)"
        elif maxdelta > 0:
            row["Impacto incremental"] = "BAJO (1–4 pp)"
        else:
            row["Impacto incremental"] = "SIN AUMENTO DETECTADO"

        # Prioridad de revisión combina ambos ejes, pero no los confunde.
        if maxpct > 100 or maxdelta >= 10:
            row["Prioridad"] = "ALTA"
        elif maxpct > 85 or maxdelta >= 5:
            row["Prioridad"] = "MEDIA"
        else:
            row["Prioridad"] = "REVISIÓN"

    for row in confirmed:
        row["Prioridad"] = "ALTA"
        row["Estado operacional"] = "—"
        row["Impacto incremental"] = "—"
    for row in conforms:
        row["Prioridad"] = "—"
        row["Estado operacional"] = "—"
        row["Impacto incremental"] = "—"

    for prefix, rows in [("OBS",confirmed),("ALT",alerts),("CHK",conforms)]:
        for i,row in enumerate(rows,1):
            row["ID"]=f"{prefix}-{i:03d}"
    return confirmed, alerts, conforms

def analyze(pages, selected):
    return technical_checks(pages, selected)

def make_pdf(project,source,n_pages,obs):
    b=io.BytesIO()
    doc=SimpleDocTemplate(b,pagesize=A4,rightMargin=1.5*cm,leftMargin=1.5*cm,topMargin=1.5*cm,bottomMargin=1.5*cm)
    ss=getSampleStyleSheet()
    title=ParagraphStyle("t",parent=ss["Title"],alignment=TA_CENTER,fontSize=15,leading=18)
    body=ParagraphStyle("b",parent=ss["BodyText"],fontSize=9,leading=12)
    small=ParagraphStyle("s",parent=ss["BodyText"],fontSize=7,leading=9)
    story=[Paragraph("INFORME DE OBSERVACIONES — REVISIÓN AUTOMATIZADA",title),Spacer(1,10),
           Paragraph(f"<b>Proyecto:</b> {project}",body),
           Paragraph(f"<b>Documento:</b> {source}",body),
           Paragraph(f"<b>Páginas:</b> {n_pages}",body),
           Paragraph("<b>Alcance:</b> hallazgos automáticos con evidencia textual. La ausencia de observaciones no equivale a aprobación técnica integral.",body),
           Spacer(1,12)]
    if not obs:
        story.append(Paragraph("No se generaron observaciones automáticas con el umbral de evidencia de esta versión.",body))
    else:
        rows=[["ID","Pág.","Materia","Clasificación","Observación"]]
        for x in obs:
            rows.append([x["ID"],x["Página"],Paragraph(x["Materia"],small),Paragraph(x["Clasificación"],small),Paragraph(x["Hallazgo"],small)])
        t=Table(rows,colWidths=[1.1*cm,1.3*cm,3.1*cm,3*cm,8.5*cm],repeatRows=1)
        t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                               ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story += [Paragraph("Matriz de observaciones",ss["Heading2"]),t,PageBreak(),Paragraph("Detalle",ss["Heading2"])]
        for x in obs:
            ev=x["Evidencia"].replace("\n\n","<br/><br/>")
            story += [Paragraph(f"{x['ID']} — {x['Materia']}",ss["Heading3"]),
                      Paragraph(f"<b>Página(s):</b> {x['Página']}",body),
                      Paragraph(f"<b>Clasificación:</b> {x['Clasificación']}",body),
                      Paragraph(f"<b>Observación:</b> {x['Hallazgo']}",body),
                      Paragraph(f"<b>Evidencia:</b> {ev}",body),
                      Paragraph(f"<b>Comprobación:</b> {x['Comprobación']}",body),
                      Paragraph(f"<b>Acción requerida:</b> {x['Acción requerida']}",body),Spacer(1,12)]
    doc.build(story); return b.getvalue()

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

if st.button("Analizar estudio",type="primary"):
    with st.spinner("Ejecutando revisión técnica trazable..."):
        st.session_state["review04"] = analyze(pages, selected)

confirmed, alerts, conforms = st.session_state.get("review04", ([], [], []))

m1, m2, m3 = st.columns(3)
m1.metric("Observaciones confirmadas", len(confirmed))
m2.metric("Alertas técnicas", len(alerts))
m3.metric("Comprobaciones", len(conforms))

if alerts:
    pa = sum(1 for x in alerts if x.get("Prioridad") == "ALTA")
    pm = sum(1 for x in alerts if x.get("Prioridad") == "MEDIA")
    pr = sum(1 for x in alerts if x.get("Prioridad") == "REVISIÓN")
    st.caption(f"Prioridad de alertas: Alta {pa} · Media {pm} · Revisión {pr}")

tabs = st.tabs(["🔴 Observaciones confirmadas", "🟠 Alertas para revisión", "🟢 Comprobaciones"])

def show_rows(rows, empty_msg):
    if not rows:
        st.info(empty_msg)
        return
    df = pd.DataFrame(rows)
    cols = ["ID","Prioridad","Estado operacional","Impacto incremental","Página","Materia","Hallazgo","Comprobación","Clasificación"]
    cols = [c for c in cols if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)
    chosen = st.selectbox("Ver detalle", [x["ID"] for x in rows], key="detail_"+rows[0]["ID"][:3])
    x = next(y for y in rows if y["ID"] == chosen)
    if "Prioridad" in x:
        st.markdown(f"**Prioridad de revisión:** {x['Prioridad']}")
    if "Estado operacional" in x and x["Estado operacional"] != "—":
        st.markdown(f"**Estado operacional:** {x['Estado operacional']}")
    if "Impacto incremental" in x and x["Impacto incremental"] != "—":
        st.markdown(f"**Impacto incremental del proyecto:** {x['Impacto incremental']}")
    st.markdown(f"**Página(s):** {x['Página']}")
    st.markdown(f"**Hallazgo:** {x['Hallazgo']}")
    st.markdown(f"**Comprobación:** {x['Comprobación']}")
    st.markdown(f"**Acción requerida:** {x['Acción requerida']}")
    if x["Evidencia"]:
        st.markdown("**Evidencia:**")
        st.code(x["Evidencia"])

with tabs[0]:
    show_rows(confirmed, "No se demostraron observaciones confirmadas con las reglas automáticas activas.")
with tabs[1]:
    show_rows(alerts, "No se generaron alertas técnicas con las reglas automáticas activas.")
with tabs[2]:
    show_rows(conforms, "No se generaron comprobaciones trazables con las reglas automáticas activas.")

# Informe: las observaciones y alertas se incorporan al PDF; las comprobaciones
# quedan en un anexo de trazabilidad.
all_report = confirmed + alerts + conforms
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
        "📄 Generar Informe Técnico de Revisión (PDF)",
        make_pdf(project, up.name, len(pages), all_report),
        "informe_tecnico_revision_vial.pdf", "application/pdf"
    )

st.caption("Criterio de trabajo del revisor: GS ≤ 0,85 aceptable; GS > 0,85 genera alerta; GS > 1,00 se identifica como sobresaturado. El impacto incremental Base→Proyecto se informa por separado. La herramienta apoya la revisión profesional.")

