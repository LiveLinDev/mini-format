# Fixtures de prueba de V6b

**Fixture de prueba, no son datos de participantes.** Son sesiones escritas a mano para probar
`tools/analizar_v6.py` (`tests/test_v6_analisis.py`). Ninguna persona participó; ningún valor es un resultado ni
debe citarse como tal.

| Archivo | Contenido |
|---|---|
| `sesiones_fixture.json` | 12 sesiones inventadas en la forma que exporta `herramienta/sesion.html`: 9 de estudio, 2 pilotos (`PIL-01`, `PIL-02`) y 1 sesión no válida (`EST-10`) |
| `sesiones_fixture.csv` | Las mismas 12 en la forma plana (una fila por participante) |

Todas llevan `tipo_datos = "fixture_de_prueba"`. El análisis se niega a mezclarlas con datos reales y se niega a
registrarlas como corrida.

Los pilotos y `EST-10` tienen valores llamativos a propósito (todas las tareas en 1 minuto, SUS 100): si alguna vez
entraran en una cifra del estudio, las pruebas lo detectarían. Los valores esperados de cada cálculo están
escritos a mano en `tests/test_v6_analisis.py` (por ejemplo, SUS de referencia, medianas con censura y tasas).
