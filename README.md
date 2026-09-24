# IA Revisor Vial — Versión 1.9.2

Corrección del parser aritmético sin modificar el módulo de grados de saturación.

Cambio:
- Localiza primero cada Cuadro 9.12–9.15.
- Normaliza los saltos de línea del texto extraído.
- Reconstruye PM-L → PT-L → Total por la posición relativa de las etiquetas.
- Exige una aparición inequívoca de cada etiqueta.
- Si la estructura no es inequívoca, no genera observaciones.

Objetivo de control del piloto:
- 9.12: correcto.
- 9.13: 11 + 10 = 21 frente a 20 informado.
- 9.14: sin falsos positivos.
- 9.15: conservar únicamente diferencias aritméticas reales.
