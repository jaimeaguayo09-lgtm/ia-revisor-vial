# IA Revisor Vial — Versión 1.4

## Corrección principal
Se agrega una capa de trazabilidad estricta para impedir que un valor del escenario
MITIGADO sea asignado a PROYECTO cuando faltan o se mezclan tablas comparativas.

- La consolidación se hace por arco + período + escenario.
- Las tablas fuente tienen prioridad sobre tablas comparativas posteriores.
- Si no se puede reconstruir un escenario de forma inequívoca, se conserva como
  dato faltante y se solicita revisión profesional.
- Para patrones del piloto en que Base > 0,85 y el supuesto Proyecto cae fuertemente
  sin existir Mitigado, el valor se trata como candidato a Mitigado.
- Proyecto sólo se recupera como igual a Base cuando existe evidencia textual conjunta
  en una página del documento; de lo contrario no se inventa.
- Se mantiene la evaluación reglamentaria implementada en 1.3.

Objetivo de validación del piloto:
- Arco 1312 PM-L: Base 1,19 → Proyecto 1,19 → Mitigado 0,54.
- Arco 1312 PT-L: Base 1,18 → Proyecto 1,18 → Mitigado 0,58.
