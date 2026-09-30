# T4 · adaptar un contrato de otro dominio · tope 15 minutos

**Situación.** Tienes el contrato de un dominio distinto (catálogo de productos, `contrato_origen_cat.json`)
y necesitas el de **solicitudes de cambio** de TI, con el prefijo `chg`. Adáptalo: los nombres,
el orden y las reglas de los campos son los de esta tabla.

| # | Campo | Tipo | Regla |
|---|---|---|---|
| 1 | `codigo` | cadena | único en el documento |
| 2 | `titulo` | cadena | texto libre |
| 3 | `tipo` | enumeración | estandar | normal | emergencia |
| 4 | `riesgo` | enumeración | bajo | medio | alto |
| 5 | `ventana_min` | entero | de 15 a 480 (minutos de la ventana de cambio) |
| 6 | `sistemas` | lista de cadenas | de 1 a 5 elementos |
| 7 | `puntaje` | decimal, opcional | de 0 a 10 (puntaje de riesgo; puede faltar) |

La cabecera solo necesita `n`.

**Qué recibes**

- `contrato_origen_cat.json`: el contrato de partida.
- `caso_positivo.mini`: un documento que tu contrato debe **aceptar**.
- `caso_negativo.mini`: un documento que tu contrato debe **rechazar** (tiene un valor que rompe una regla).
- `../guia_mini.md`: la guía (incluye cómo generar un contrato desde un JSON Schema).

**Qué debes hacer.** Produce el contrato de solicitudes de cambio. Compruébalo con los dos documentos.

**Entrega.** `entrega/contrato_cambios.json`.
