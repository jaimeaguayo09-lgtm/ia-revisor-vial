
import io
import re
from collections import defaultdict

import fitz
import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)

st.set_page_config(page_title="IA Revisor Vial", page_icon="🛣️", layout="wide")
st.title("🛣️ IA Revisor Vial — Prototipo 0.2")
st.caption("Revisión trazable de estudios viales e IMIV. Cada hallazgo debe poder vincularse con evidencia del documento.")

MODULES = [
    "Antecedentes", "Aforos", "Demanda", "Capacidad y saturación",
    "Modelación", "Geometría", "Señalización y demarcación",
    "Consistencia documental", "Medidas de mitigación"
]

CLASS_ORDER = {
    "ERROR DE CÁLCULO": 1,
    "INCONSISTENCIA": 2,
    "FALTA DE ANTECEDENTES": 3,
    "REQUIERE REVISIÓN PROFESIONAL": 4,
    "CONFORME": 5,
}

def clean_text(s):
    return re.sub(r"\s+", " ", s or "").strip()

@st.cache_data(show_spinner=False)
def extract_pdf(data):
    doc = fitz.open(stream=data, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        pages.append({"page": i + 1, "text": clean_text(page.get_text("text"))})
    return pages

def evidence(text, start, end, radius=160):
    a = max(0, start-radius)
    b = min(len(text), end+radius)
    return clean_text(text[a:b])

def find_quantities(pages):
    """Context-aware extraction. Vehicle and bicycle parking are different concepts."""
    patterns = {
        "Estacionamientos de vehículos": [
            r"(\d{1,4})\s+(?:estacionamientos?|cupos?)\s+(?:para\s+)?(?:vehículos?|vehiculares?|automóviles?)",
            r"(?:estacionamientos?|cupos?)\s+(?:vehiculares?|de\s+vehículos?)\D{0,25}(\d{1,4})",
        ],
        "Estacionamientos de bicicletas": [
            r"(\d{1,4})\s+(?:estacionamientos?|cupos?)\s+(?:para\s+)?bicicletas?",
            r"(?:estacionamientos?|cupos?)\s+(?:de\s+)?bicicletas?\D{0,25}(\d{1,4})",
            r"bicicleteros?\D{0,25}(\d{1,4})",
        ],
        "Estacionamientos PMR": [
            r"(\d{1,3})\s+(?:estacionamientos?|cupos?)\s+(?:para\s+)?(?:personas\s+con\s+movilidad\s+reducida|pmr)",
            r"(?:movilidad\s+reducida|pmr)\D{0,25}(\d{1,3})",
        ],
    }
    found = defaultdict(list)
    for p in pages:
        txt = p["text"]
        for concept, pats in patterns.items():
            for pat in pats:
                for m in re.finditer(pat, txt, flags=re.I):
                    val = int(m.group(1))
                    found[concept].append({
                        "value": val, "page": p["page"],
                        "evidence": evidence(txt, m.start(), m.end())
                    })
    return found

def add_obs(obs, materia, pages, hallazgo, comprobacion, clasificacion, evidencia="", informado="", recalculado="", accion=""):
    obs.append({
        "ID": f"RV-{len(obs)+1:03d}",
        "Página": pages,
        "Materia": materia,
        "Hallazgo": hallazgo,
        "Evidencia": evidencia,
        "Valor informado": informado,
        "Valor recalculado": recalculado,
        "Comprobación": comprobacion,
        "Clasificación": clasificacion,
        "Acción requerida": accion,
    })

def check_contextual_consistency(pages, obs):
    quantities = find_quantities(pages)
    for concept, hits in quantities.items():
        vals = sorted(set(x["value"] for x in hits))
        if len(vals) > 1:
            pg = ", ".join(map(str, sorted(set(x["page"] for x in hits))))
            ev = " | ".join(f"Pág. {x['page']}: {x['evidence']}" for x in hits[:4])
            add_obs(
                obs, "Consistencia documental", pg,
                f"Se encontraron valores distintos para el mismo concepto «{concept}»: {vals}.",
                "Comparación contextual de menciones referidas al mismo concepto.",
                "INCONSISTENCIA", ev,
                accion="Verificar cuál es el valor correcto y uniformar el estudio y sus anexos."
            )

def presence_check(pages, selected, obs):
    whole = " ".join(p["text"].lower() for p in pages)
    checks = {
        "Aforos": ["aforo", "conteo vehicular"],
        "Demanda": ["demanda", "generación de viajes", "generacion de viajes"],
        "Capacidad y saturación": ["grado de saturación", "grado de saturacion", "capacidad"],
        "Modelación": ["modelación", "modelacion", "transyt", "sidra", "vissim", "aimsun"],
        "Geometría": ["geometría", "geometria", "perfil", "planta"],
        "Señalización y demarcación": ["señalización", "señalizacion", "demarcación", "demarcacion"],
        "Medidas de mitigación": ["medidas de mitigación", "medidas de mitigacion", "mitigación", "mitigacion"],
    }
    for module, terms in checks.items():
        if module in selected and not any(t in whole for t in terms):
            add_obs(
                obs, module, "—",
                f"No se identificó automáticamente contenido suficiente asociado al módulo «{module}».",
                "Búsqueda textual preliminar en el documento.",
                "FALTA DE ANTECEDENTES",
                accion="Revisar si el antecedente se encuentra en anexos, planos o documentos no extraíbles como texto."
            )

def saturation_checks(pages, obs):
    # Conservative: only calculate when q, c and q/c are in a short textual neighborhood.
    num = r"([0-9]+(?:[.,][0-9]+)?)"
    qpat = re.compile(r"(?:flujo|q)\s*[:=]\s*" + num, re.I)
    cpat = re.compile(r"(?:capacidad|c)\s*[:=]\s*" + num, re.I)
    spat = re.compile(r"(?:q\s*/\s*c|grado\s+de\s+saturaci[oó]n|x)\s*[:=]\s*" + num, re.I)
    for p in pages:
        txt = p["text"]
        # Search chunks so unrelated values on a page are not mixed.
        for start in range(0, len(txt), 900):
            chunk = txt[start:start+1200]
            qm, cm, sm = qpat.search(chunk), cpat.search(chunk), spat.search(chunk)
            if qm and cm and sm:
                q = float(qm.group(1).replace(",", "."))
                c = float(cm.group(1).replace(",", "."))
                informed = float(sm.group(1).replace(",", "."))
                if c > 0:
                    calc = q/c
                    if abs(calc-informed) > 0.02:
                        add_obs(
                            obs, "Capacidad y saturación", str(p["page"]),
                            "El grado de saturación informado no coincide con el cociente q/c identificado en el mismo contexto.",
                            f"Recalculo determinístico: q/c = {q:g}/{c:g} = {calc:.3f}.",
                            "ERROR DE CÁLCULO",
                            evidence(txt, start, min(len(txt), start+1200), 0),
                            f"{informed:.3f}", f"{calc:.3f}",
                            "Revisar el cálculo y los resultados que dependan de este parámetro."
                        )

def analyze(pages, selected):
    obs = []
    if "Consistencia documental" in selected:
        check_contextual_consistency(pages, obs)
    presence_check(pages, selected, obs)
    if "Capacidad y saturación" in selected:
        saturation_checks(pages, obs)
    obs.sort(key=lambda x: (CLASS_ORDER.get(x["Clasificación"], 99), x["ID"]))
    # Renumber after sort
    for i, row in enumerate(obs, 1):
        row["ID"] = f"RV-{i:03d}"
    return obs

def make_pdf(project, source_name, n_pages, observations):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=1.6*cm, leftMargin=1.6*cm,
        topMargin=1.6*cm, bottomMargin=1.6*cm
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title2", parent=styles["Title"], alignment=TA_CENTER, fontSize=16, leading=20)
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, leading=10)
    body = ParagraphStyle("body2", parent=styles["BodyText"], fontSize=9, leading=12)
    h2 = ParagraphStyle("h2b", parent=styles["Heading2"], fontSize=12, leading=15)

    story = [
        Paragraph("INFORME DE OBSERVACIONES — REVISIÓN AUTOMATIZADA", title),
        Spacer(1, 10),
        Paragraph(f"<b>Proyecto:</b> {project}", body),
        Paragraph(f"<b>Documento revisado:</b> {source_name}", body),
        Paragraph(f"<b>Extensión:</b> {n_pages} páginas", body),
        Paragraph("<b>Alcance:</b> revisión automatizada preliminar. Las conclusiones normativas requieren fuente técnica verificable y revisión profesional cuando corresponda.", body),
        Spacer(1, 12),
        Paragraph("Resumen ejecutivo", h2),
    ]

    if observations:
        counts = pd.Series([x["Clasificación"] for x in observations]).value_counts()
        summary = [["Clasificación", "Cantidad"]] + [[k, str(v)] for k, v in counts.items()]
        t = Table(summary, colWidths=[11*cm, 3*cm])
        t.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), .4, colors.grey),
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        story += [t, Spacer(1, 14), Paragraph("Matriz de observaciones", h2)]
        rows = [["ID", "Pág.", "Materia", "Clasificación", "Observación"]]
        for x in observations:
            rows.append([
                x["ID"], str(x["Página"]),
                Paragraph(x["Materia"], small),
                Paragraph(x["Clasificación"], small),
                Paragraph(x["Hallazgo"], small),
            ])
        mt = Table(rows, colWidths=[1.2*cm, 1.4*cm, 3.2*cm, 3.2*cm, 8.2*cm], repeatRows=1)
        mt.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), .3, colors.grey),
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 7),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        story += [mt, PageBreak(), Paragraph("Detalle de observaciones", h2)]
        for x in observations:
            story += [
                Paragraph(f"{x['ID']} — {x['Materia']}", styles["Heading3"]),
                Paragraph(f"<b>Página(s):</b> {x['Página']}", body),
                Paragraph(f"<b>Clasificación:</b> {x['Clasificación']}", body),
                Paragraph(f"<b>Observación:</b> {x['Hallazgo']}", body),
            ]
            if x["Evidencia"]:
                story.append(Paragraph(f"<b>Evidencia:</b> {x['Evidencia']}", body))
            if x["Valor informado"]:
                story.append(Paragraph(f"<b>Valor informado:</b> {x['Valor informado']}", body))
            if x["Valor recalculado"]:
                story.append(Paragraph(f"<b>Valor recalculado:</b> {x['Valor recalculado']}", body))
            story += [
                Paragraph(f"<b>Comprobación:</b> {x['Comprobación']}", body),
                Paragraph(f"<b>Acción requerida:</b> {x['Acción requerida'] or 'Revisar técnicamente el antecedente.'}", body),
                Spacer(1, 12),
            ]
    else:
        story.append(Paragraph("No se generaron observaciones automáticas con las reglas activas. Esto no equivale a una aprobación técnica integral del estudio.", body))

    doc.build(story)
    return buf.getvalue()

with st.sidebar:
    st.header("Caso")
    project = st.text_input("Nombre", "Caso Piloto 001")
    uploaded = st.file_uploader("Estudio PDF", type=["pdf"])
    st.header("Módulos")
    selected = [m for m in MODULES if st.checkbox(m, value=True, key=m)]
    st.info("El sistema no declara incumplimientos normativos sin una biblioteca técnica verificable.")

if not uploaded:
    st.info("Carga un estudio en PDF para comenzar.")
    st.stop()

data = uploaded.getvalue()
with st.spinner("Extrayendo texto del estudio..."):
    pages = extract_pdf(data)

st.success(f"Documento cargado: {len(pages)} páginas")
c1, c2, c3 = st.columns(3)
c1.metric("Páginas", len(pages))
c2.metric("Módulos seleccionados", len(selected))
c3.metric("Proyecto", project)

if st.button("Analizar estudio", type="primary"):
    with st.spinner("Ejecutando comprobaciones..."):
        st.session_state["obs"] = analyze(pages, selected)

observations = st.session_state.get("obs", [])
st.subheader("Matriz de observaciones")

if observations:
    df = pd.DataFrame(observations)
    display_cols = ["ID", "Página", "Materia", "Hallazgo", "Comprobación", "Clasificación"]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

    csv = df.to_csv(index=False).encode("utf-8-sig")
    pdf = make_pdf(project, uploaded.name, len(pages), observations)

    b1, b2 = st.columns(2)
    b1.download_button("Exportar CSV", csv, file_name="observaciones_revisor_vial.csv", mime="text/csv")
    b2.download_button(
        "📄 Generar Informe de Observaciones (PDF)",
        pdf,
        file_name="informe_observaciones_revisor_vial.pdf",
        mime="application/pdf"
    )

    st.subheader("Auditor")
    ids = [x["ID"] for x in observations]
    chosen = st.selectbox("Observación", ids)
    x = next(o for o in observations if o["ID"] == chosen)
    st.markdown(f"**Hallazgo:** {x['Hallazgo']}")
    st.markdown(f"**Página(s):** {x['Página']}")
    st.markdown(f"**Clasificación:** {x['Clasificación']}")
    if x["Evidencia"]:
        st.markdown("**Evidencia extraída:**")
        st.code(x["Evidencia"])
    st.markdown(f"**Comprobación:** {x['Comprobación']}")
    st.markdown(f"**Acción requerida:** {x['Acción requerida']}")
else:
    st.caption("Pulsa «Analizar estudio» para generar la matriz. Si no se generan observaciones, ello no equivale a aprobación técnica integral.")
