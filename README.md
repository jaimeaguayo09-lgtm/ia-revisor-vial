# IA Revisor Vial — Versión 1.0

Base estable del revisor técnico.

Módulos:
- Grado de saturación con umbral de trabajo GS <= 0,85.
- Comparación Base → Proyecto → Mitigado.
- Impacto incremental calculado exclusivamente como GS Proyecto - GS Base.
- Extracción de totales de distribución de flujos inducidos PM-L/PT-L.
- Comprobación aritmética de tiempos de viaje cuando la tabla es inequívoca.
- Control de disponibilidad de longitudes de cola: si no existe evidencia textual suficiente, se marca para revisión profesional y no se inventan datos.
- Informe PDF y CSV con trazabilidad.

Próximos módulos: colas y demoras desde tablas/anexos inequívocos; NDS; biblioteca normativa controlada.
