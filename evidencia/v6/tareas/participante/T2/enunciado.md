# T2 · diagnosticar y reparar un registro inválido · tope 15 minutos

**Situación.** El modelo devolvió una respuesta `.mini` con 12 tickets (contrato `contrato_tk.json`) y el
validador la rechaza. Hay **un** registro defectuoso.

**Qué recibes**

- `respuesta.mini`: la respuesta del modelo.
- `contrato_tk.json`: el contrato.
- `correccion_modelo.mini`: lo que respondió el modelo cuando se le pidió corregir solo la línea defectuosa
  (respuesta ya obtenida; no hay que volver a llamar a ningún modelo).
- `../guia_mini.md`: la guía.

**Qué debes hacer**

1. **Diagnosticar**: indica el código de error y el número de línea del registro defectuoso
   (la cabecera es la línea 1).
2. **Reparar**: produce un documento `.mini` corregido que valide contra el contrato. Los otros 11 registros
   deben quedar exactamente como estaban. Puedes corregir a mano o usar la corrección del modelo, pero no
   inventes valores.

**Entrega**

- `entrega/T2_diagnostico.json` con la forma `{"codigo_error": "E00", "linea": 0}` (con tus valores).
- `entrega/T2_corregido.mini`.
