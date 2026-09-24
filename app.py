import streamlit as st
from pathlib import Path
import re, json
import fitz
import pandas as pd

st.set_page_config(page_title="IA Revisor Vial", page_icon="🚦", layout="wide")

CATEGORIES = [
    "Antecedentes", "Aforos", "Demanda", "Capacidad y saturación",
    "Modelación", "Geometría", "Señalización y demarcación",
    "Consistencia documental", "Medidas de mitigación"
]

def extract_pdf(uploaded):
    doc = fitz.open(stream=uploaded.read(), filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        pages.append({"page": i+1, "text": page.get_text("text")})
    return pages

def find_numbers(text):
    vals = []
    for m in re.finditer(r'(?<!\w)(\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?)(?!\w)', text):
        vals.append((m.group(0), m.start()))
    return vals

def audit(pages):
    findings = []
    oid = 1
    full = "\n".join(p["text"] for p in pages)

    # 1) Detect explicit flow/capacity/saturation statements and recalculate when nearby.
    for p in pages:
        t = p["text"]
        low = t.lower()
        if "capacidad" in low and ("saturación" in low or "saturacion" in low):
            # Conservative extraction: only flag if labels and values are on same page.
            flow = re.search(r'(?:flujo|demanda)[^\d]{0,35}([\d\.,]+)', t, re.I)
            cap = re.search(r'capacidad[^\d]{0,35}([\d\.,]+)', t, re.I)
            sat = re.search(r'(?:grado de saturaci[oó]n|saturaci[oó]n)[^\d]{0,35}([\d\.,]+)', t, re.I)
            if flow and cap and sat:
                def num(s):
                    s=s.replace(" ","")
                    if "," in s and "." in s: s=s.replace(".","").replace(",",".")
                    elif "," in s: s=s.replace(",",".")
                    return float(s)
                try:
                    q,c,x = num(flow.group(1)),num(cap.group(1)),num(sat.group(1))
                    if c>0:
                        xr=q/c
                        if abs(xr-x)>0.02:
                            findings.append({
                                "ID":f"RV-{oid:03d}","Página":p["page"],
                                "Materia":"Capacidad y saturación",
                                "Hallazgo":f"El grado de saturación informado ({x:.3f}) no coincide con q/c ({xr:.3f}).",
                                "Comprobación":f"{q:g} / {c:g} = {xr:.3f}",
                                "Clasificación":"ERROR DE CÁLCULO",
                                "Estado":"Pendiente"
                            }); oid+=1
                except Exception: pass

    # 2) Cross-document consistency: key project quantities.
    patterns = {
        "estacionamientos vehículos": r'(\d+)\s+estacionamientos[^.\n]{0,80}(?:veh[ií]culos|vehiculares|livianos)',
        "estacionamientos bicicletas": r'(\d+)\s+estacionamientos[^.\n]{0,40}bicicletas',
        "niveles": r'(?:total de\s+)?(\d+)\s+niveles',
    }
    for label, pat in patterns.items():
        vals=[]
        for p in pages:
            for m in re.finditer(pat,p["text"],re.I):
                vals.append((int(m.group(1)),p["page"]))
        distinct=sorted(set(v for v,_ in vals))
        if len(distinct)>1:
            findings.append({
                "ID":f"RV-{oid:03d}","Página":", ".join(map(str,sorted(set(pg for _,pg in vals)))),
                "Materia":"Consistencia documental",
                "Hallazgo":f"Se encontraron valores distintos para {label}: {distinct}.",
                "Comprobación":"Comparación automática de menciones en el documento.",
                "Clasificación":"INCONSISTENCIA","Estado":"Pendiente"
            }); oid+=1

    # 3) Presence checks for an IMIV review workflow.
    required = {
        "Mediciones de flujo vehicular":["mediciones de flujo vehicular"],
        "Mediciones de flujo peatonal":["mediciones de flujo peatonal"],
        "Longitud de cola":["longitud de cola"],
        "Modelación":["modelación","modelacion"],
        "Situación base":["situación base","situacion base"],
        "Situación con proyecto":["situación con proyecto","situacion con proyecto"],
        "Medidas de mitigación":["medidas de mitigación","medidas de mitigacion"],
    }
    for item, terms in required.items():
        if not any(term in full.lower() for term in terms):
            findings.append({
                "ID":f"RV-{oid:03d}","Página":"—","Materia":"Antecedentes",
                "Hallazgo":f"No se localizó una sección identificable sobre: {item}.",
                "Comprobación":"Búsqueda textual en el documento.",
                "Clasificación":"FALTA DE ANTECEDENTES","Estado":"Pendiente"
            }); oid+=1

    if not findings:
        findings.append({
            "ID":"RV-001","Página":"—","Materia":"Auditoría",
            "Hallazgo":"La revisión automática básica no detectó errores determinísticos con las reglas actualmente implementadas.",
            "Comprobación":"Esto no equivale a aprobación técnica; se requiere revisión normativa y profesional.",
            "Clasificación":"REQUIERE REVISIÓN PROFESIONAL","Estado":"Pendiente"
        })
    return pd.DataFrame(findings)

st.title("IA REVISOR VIAL")
st.caption("Prototipo 0.1 · Revisión asistida de estudios de tránsito y transporte")

with st.sidebar:
    st.header("Proyecto")
    project = st.text_input("Nombre", "Caso Piloto 001")
    st.header("Módulos")
    selected = [x for x in CATEGORIES if st.checkbox(x, True)]
    st.info("El prototipo no declara incumplimientos normativos sin una biblioteca técnica verificable.")

uploaded = st.file_uploader("Cargar estudio vial", type=["pdf"])
if uploaded:
    with st.spinner("Extrayendo y estructurando el documento…"):
        pages = extract_pdf(uploaded)
    st.success(f"Documento cargado: {len(pages)} páginas")

    c1,c2,c3 = st.columns(3)
    c1.metric("Páginas", len(pages))
    c2.metric("Módulos seleccionados", len(selected))
    c3.metric("Proyecto", project)

    if st.button("Analizar estudio", type="primary"):
        df = audit(pages)
        st.session_state["findings"] = df

    if "findings" in st.session_state:
        df = st.session_state["findings"]
        st.subheader("Matriz de observaciones")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "Exportar CSV",
            df.to_csv(index=False).encode("utf-8-sig"),
            "matriz_observaciones.csv","text/csv"
        )

        st.subheader("Auditor")
        oid = st.selectbox("Observación", df["ID"].tolist())
        row = df[df["ID"]==oid].iloc[0]
        st.write("**Hallazgo:**", row["Hallazgo"])
        st.write("**Comprobación:**", row["Comprobación"])
        st.write("**Clasificación:**", row["Clasificación"])
        st.warning("Validar por un ingeniero antes de emitir una observación formal.")
else:
    st.info("Carga un PDF para iniciar la revisión.")
