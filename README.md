# IA Revisor Vial — Versión 1.4.1

Corrección de error de ejecución de la versión 1.4.

Causa:
`_scenario_tables()` devuelve una tupla y la capa `_strict_scenario_tables()`
la estaba tratando directamente como diccionario, produciendo:
`AttributeError: 'tuple' object has no attribute 'items'`.

Corrección:
se toma explícitamente el primer elemento de la tupla como diccionario de
escenarios antes de aplicar la validación Base → Proyecto → Mitigado.

Se mantiene el objetivo de validación:
- 1312 PM-L: 1,19 → 1,19 → 0,54
- 1312 PT-L: 1,18 → 1,18 → 0,58
