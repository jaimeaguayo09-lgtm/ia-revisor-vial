
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
st.title("🛣️ IA Revisor Vial — Prototipo 0.3")
st.caption("Revisión trazable: una observación solo se emite cuando la evidencia automática es suficientemente específica.")

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

def analyze(pages,selected):
    obs=[]
    if "Consistencia documental" in selected:
        concepts=extract_concepts(pages)
        for concept,hits in concepts.items():
            vals=sorted(set(h["value"] for h in hits))
            # High-confidence gate: require at least 2 explicit, independent statements
            # and show evidence for every competing value.
            byval=defaultdict(list)
            for h in hits: byval[h["value"]].append(h)
            if len(vals)>1 and all(byval[v] for v in vals):
                evidence=[]
                pageset=set()
                for v in vals:
                    h=byval[v][0]
                    pageset.add(h["page"])
                    evidence.append(f"Valor {v} — pág. {h['page']}: {h['evidence']}")
                obs.append(obsrow(
                    len(obs)+1,"Consistencia documental",
                    ", ".join(map(str,sorted(pageset))),
                    f"Se identificaron declaraciones explícitas con valores distintos para «{concept}»: {vals}.",
                    "\n\n".join(evidence),
                    "Comparación entre expresiones explícitas del mismo concepto. Se muestra evidencia independiente para cada valor.",
                    "INCONSISTENCIA",
                    "Verificar el valor correcto y uniformar el documento y sus anexos."
                ))
    return obs

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
    st.session_state["obs03"]=analyze(pages,selected)

obs=st.session_state.get("obs03",[])
st.subheader("Matriz de observaciones")
if obs:
    df=pd.DataFrame(obs)
    st.dataframe(df[["ID","Página","Materia","Hallazgo","Comprobación","Clasificación"]],use_container_width=True,hide_index=True)
    c1,c2=st.columns(2)
    c1.download_button("Exportar CSV",df.to_csv(index=False).encode("utf-8-sig"),"observaciones_revisor_vial.csv","text/csv")
    c2.download_button("📄 Generar Informe de Observaciones (PDF)",make_pdf(project,up.name,len(pages),obs),
                       "informe_observaciones_revisor_vial.pdf","application/pdf")
    st.subheader("Auditor")
    chosen=st.selectbox("Observación",[x["ID"] for x in obs])
    x=next(y for y in obs if y["ID"]==chosen)
    st.markdown(f"**Hallazgo:** {x['Hallazgo']}")
    st.markdown(f"**Página(s):** {x['Página']}")
    st.markdown(f"**Clasificación:** {x['Clasificación']}")
    st.markdown("**Evidencia utilizada para sostener la observación:**")
    st.code(x["Evidencia"])
    st.markdown(f"**Comprobación:** {x['Comprobación']}")
    st.markdown(f"**Acción requerida:** {x['Acción requerida']}")
else:
    st.success("No se generaron observaciones automáticas con el umbral de evidencia actual.")
    st.caption("Esto no significa que el estudio esté aprobado: solo que las reglas automáticas activas no demostraron una inconsistencia con evidencia suficiente.")
