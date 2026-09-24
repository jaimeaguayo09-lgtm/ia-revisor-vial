# IA Revisor Vial — Versión 1.4.2

Corrección del ValueError detectado en 1.4.1.

Causa:
`build_arc_sheet()` espera desempaquetar dos valores:
`scenarios, _ = _strict_scenario_tables(pages)`,
pero la función estricta devolvía solamente el diccionario de escenarios.

Corrección:
`_strict_scenario_tables()` vuelve a respetar el contrato original y retorna:
`(escenarios, comparativas)`.

Se mantiene la validación de trazabilidad y el objetivo:
- 1312 PM-L: 1,19 → 1,19 → 0,54
- 1312 PT-L: 1,18 → 1,18 → 0,58
