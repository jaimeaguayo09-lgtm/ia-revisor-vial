
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
st.title("🛣️ IA Revisor Vial — Prototipo 0.4")
st.caption("Revisión técnica trazable: separa observaciones confirmadas, alertas para revisión profesional y comprobaciones conformes.")

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

def technical_checks(pages, selected):
    confirmed, alerts, conforms = [], [], []

    # 1) Consistencia documental: reutiliza extracción contextual estricta.
    if "Consistencia documental" in selected:
        concepts = extract_concepts(pages)
        for concept, hits in concepts.items():
            vals = sorted(set(h["value"] for h in hits))
            byval = defaultdict(list)
            for h in hits: byval[h["value"]].append(h)
            if len(vals) > 1:
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
                    "Comprobación": "Comparación entre expresiones explícitas referidas al mismo concepto.",
                    "Clasificación": "INCONSISTENCIA",
                    "Acción requerida": "Verificar el valor correcto y uniformar el estudio y sus anexos."
                })

    # 2) Trazabilidad de grados de saturación.
    # No supone que un valor >85% sea incumplimiento: lo trata como alerta técnica.
    if "Capacidad y saturación" in selected or "Modelación" in selected:
        sat_re = re.compile(
            r"(?:grado(?:s)?\s+de\s+saturaci[oó]n|saturaci[oó]n)"
            r".{0,220}?(?P<v>\d{1,3}(?:[.,]\d+)?)\s*%",
            re.I
        )
        seen = set()
        for p in pages:
            txt = p["text"]
            for m in sat_re.finditer(txt):
                v = _pct(m.group("v"))
                if v is None: continue
                key = (p["page"], round(v,2))
                if key in seen: continue
                seen.add(key)
                ev = snippet(txt, m.start(), m.end(), 180)
                if v > 100:
                    alerts.append({
                        "Página": str(p["page"]), "Materia": "Capacidad y saturación",
                        "Hallazgo": f"Se identificó un grado de saturación de {v:g}%, superior a 100%.",
                        "Evidencia": ev,
                        "Comprobación": "Detección de valor porcentual explícitamente asociado a grado de saturación.",
                        "Clasificación": "ALERTA TÉCNICA",
                        "Acción requerida": "Revisar el arco/período, su modelación y la respuesta de las medidas de mitigación."
                    })
                elif v > 85:
                    alerts.append({
                        "Página": str(p["page"]), "Materia": "Capacidad y saturación",
                        "Hallazgo": f"Se identificó un grado de saturación de {v:g}%, que requiere seguimiento en la revisión técnica.",
                        "Evidencia": ev,
                        "Comprobación": "Detección de valor porcentual explícitamente asociado a grado de saturación. No se declara incumplimiento normativo.",
                        "Clasificación": "ALERTA TÉCNICA",
                        "Acción requerida": "Contrastar con situación base, con proyecto y mitigada, y verificar la conclusión del estudio."
                    })

    # 3) dq/d2: solo declara conforme cuando la propia fila/contexto contiene ambos
    # valores y la comparación numérica es inequívoca.
    if "Geometría" in selected or "Medidas de mitigación" in selected:
        pair_re = re.compile(
            r"(?:dq|d[qQ])\s*[/\-]\s*(?:d2|D2)?.{0,100}?"
            r"(?P<a>\d{1,3}(?:[.,]\d+)?)\s*(?:m)?\s*[/\-]\s*"
            r"(?P<b>\d{1,3}(?:[.,]\d+)?)\s*m?",
            re.I
        )
        for p in pages:
            for m in pair_re.finditer(p["text"]):
                a, b = _pct(m.group("a")), _pct(m.group("b"))
                if a is None or b is None: continue
                conforms.append({
                    "Página": str(p["page"]), "Materia": "Geometría / dq-d2",
                    "Hallazgo": f"Se identificó un par de distancias dq/d2 = {a:g}/{b:g} m para trazabilidad.",
                    "Evidencia": snippet(p["text"], m.start(), m.end(), 180),
                    "Comprobación": "Extracción numérica del par dq/d2. La conformidad normativa no se afirma sin biblioteca normativa verificada.",
                    "Clasificación": "COMPROBACIÓN TRAZADA",
                    "Acción requerida": "Mantener como antecedente para comparación normativa posterior."
                })

    # 4) Presencia estructural de capítulos clave: si el documento no ofrece
    # texto identificable, se genera alerta, no 'error'.
    whole = " ".join(p["text"].lower() for p in pages)
    expected = {
        "Aforos": ["aforo", "conteo vehicular"],
        "Demanda": ["generación de viajes", "generacion de viajes", "demanda"],
        "Modelación": ["modelación", "modelacion", "transyt"],
        "Medidas de mitigación": ["medidas de mitigación", "medidas de mitigacion", "mitigación", "mitigacion"],
    }
    for module, terms in expected.items():
        if module in selected:
            if any(t in whole for t in terms):
                conforms.append({
                    "Página": "—", "Materia": module,
                    "Hallazgo": f"Se identificó contenido textual asociado al módulo «{module}».",
                    "Evidencia": "Presencia documental detectada.",
                    "Comprobación": "Control de presencia; no equivale a validación técnica del contenido.",
                    "Clasificación": "COMPROBACIÓN DOCUMENTAL",
                    "Acción requerida": "Continuar con las comprobaciones específicas del módulo."
                })
            else:
                alerts.append({
                    "Página": "—", "Materia": module,
                    "Hallazgo": f"No se identificó automáticamente contenido textual suficiente asociado a «{module}».",
                    "Evidencia": "Búsqueda textual en el PDF.",
                    "Comprobación": "Control de presencia documental.",
                    "Clasificación": "ALERTA TÉCNICA",
                    "Acción requerida": "Revisar anexos, planos o contenido no extraíble como texto."
                })

    # IDs separados por tipo para que el informe sea legible.
    for prefix, rows in [("OBS", confirmed), ("ALT", alerts), ("CHK", conforms)]:
        for i, row in enumerate(rows, 1):
            row["ID"] = f"{prefix}-{i:03d}"
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

tabs = st.tabs(["🔴 Observaciones confirmadas", "🟠 Alertas para revisión", "🟢 Comprobaciones"])

def show_rows(rows, empty_msg):
    if not rows:
        st.info(empty_msg)
        return
    df = pd.DataFrame(rows)
    st.dataframe(df[["ID","Página","Materia","Hallazgo","Comprobación","Clasificación"]],
                 use_container_width=True, hide_index=True)
    chosen = st.selectbox("Ver detalle", [x["ID"] for x in rows], key="detail_"+rows[0]["ID"][:3])
    x = next(y for y in rows if y["ID"] == chosen)
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

st.caption("La herramienta apoya la revisión profesional. Una alerta no equivale a incumplimiento normativo y una comprobación documental no equivale a aprobación integral.")

