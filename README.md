# IA Revisor Vial — Prototipo 0.9

Corrección del motor de saturación.

- Estado operacional: usa exclusivamente GS del escenario Proyecto.
- Umbral de trabajo: GS <= 0,85 aceptable; GS > 0,85 sobre umbral; GS > 1,00 sobresaturado.
- Impacto incremental: se calcula exclusivamente como GS Proyecto - GS Base.
- La tabla muestra GS Base, GS Proyecto y delta Proyecto-Base.
- No se extraen porcentajes del texto para clasificar el impacto.
- Si falta Base o Proyecto, el impacto queda como NO CALCULABLE.

Bandas internas de triage del impacto:
- Bajo: +0,01 a +0,04
- Medio: +0,05 a +0,09
- Alto: >= +0,10

Estas bandas son reglas internas del prototipo y no una declaración normativa.
