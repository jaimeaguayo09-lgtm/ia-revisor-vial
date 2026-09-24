# IA Revisor Vial — Versión 1.5

Se reemplaza la heurística de 1.4 por un extractor estructural.

## Cambio clave
El parser reconoce expresamente las variantes de encabezado:
- Situación Actual
- Situación Base
- Situación Proyecto
- Situación con Proyecto
- Situación Proyecto Mitigado
- Situación con Proyecto Mitigado

Primero identifica el escenario por el encabezado de la tabla y después extrae
Arco / PM-L / PT-L. No mueve valores entre escenarios ni infiere valores faltantes.

Esto corrige la omisión de tablas tituladas “Situación con Proyecto”, que el
parser anterior no reconocía como PROYECTO.

## Control del piloto
La validación esperada para arco 1312 es:
- PM-L: Base 1,19 → Proyecto 1,19 → Mitigado 0,54
- PT-L: Base 1,18 → Proyecto 1,18 → Mitigado 0,58
