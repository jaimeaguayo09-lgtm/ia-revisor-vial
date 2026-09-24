# IA Revisor Vial — Versión 1.7

Se mantiene el extractor validado de la versión 1.6 y se separan tres capas:

1. Cumplimiento normativo:
   Matriz normativa al consultor. Sólo contiene observaciones normativas o falta
   de trazabilidad.

2. Alertas técnicas:
   Nueva pestaña “Alertas comportamiento”. Detecta cuando el escenario Mitigado
   empeora el GS respecto de Proyecto, sin calificarlo automáticamente como
   incumplimiento.

   Prioridad interna:
   - +1 a +4 pp: BAJA
   - +5 a +9 pp: MEDIA
   - >= +10 pp: ALTA

3. Observaciones confirmadas:
   Se mantienen separadas para errores determinísticos comprobados.

Control del piloto:
- Arco 1331 PM-L: 0,37 → 0,53 = +16 pp, alerta ALTA.
- Arco 1331 PT-L: 0,36 → 0,58 = +22 pp, alerta ALTA.
