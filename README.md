# IA Revisor Vial — Versión 1.9.3

- Corrige el encabezado visible a 1.9.3.
- Integra errores aritméticos confirmados al contador superior.
- Usa patrones específicos y seguros para los Cuadros 9.12–9.15.
- Excluye los costos monetarios del recálculo.
- No modifica el extractor de grados de saturación.

Control esperado:
9.12 correcto.
9.13: 11+10=21 versus 20 -> 1 error.
9.14: todas las sumas correctas.
9.15:
  PM-L 18+17=35 correcto.
  PT-L 17+15=32 correcto.
  Total Marcha 18+17=35 correcto.
  Total Ralentí 17+15=32 versus 31 -> error.
  Total general 35+32=67 versus 66 -> error.
Total esperado de observaciones aritméticas confirmadas: 3.
