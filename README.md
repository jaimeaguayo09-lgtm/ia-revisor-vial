# IA Revisor Vial — Versión 1.9.1

Corrección puntual del módulo aritmético 1.9.

Problema detectado:
la búsqueda de la etiqueta `Total` no estaba anclada al inicio de la fila,
por lo que podía capturar valores de otra línea y generar falsos positivos.

Corrección:
`PM-L`, `PT-L` y `Total` se reconocen ahora sólo como primer campo de una fila
física del bloque del cuadro.

Resultados esperados del piloto:
- Cuadro 9.12: correcto.
- Cuadro 9.13: 11 + 10 = 21 versus 20 informado -> observación confirmada.
- Cuadro 9.14: sin errores aritméticos.
- Cuadro 9.15: mantener sólo las inconsistencias aritméticas reales del cuadro.

No se modifica el extractor de grados de saturación.
