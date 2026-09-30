# T3 · tratar una respuesta incompleta · tope 10 minutos

**Situación.** El modelo llegó al límite de salida y la respuesta `.mini` se cortó. La aplicación no debe
descartar todo: debe quedarse con lo que llegó completo y saber qué falta.

**Qué recibes**

- `respuesta_cortada.mini`: la respuesta truncada (contrato `contrato_tk.json`).
- `../guia_mini.md`: la guía.

**Qué debes hacer**

1. Recupera los registros que llegaron **completos** y válidos.
2. Indica cuántos de los registros declarados en la cabecera **no** pudiste recuperar y cuál es la posición
   del primero (posición = número de orden del registro, empezando en 1).

**Entrega.** `entrega/T3_recuperado.json` con la forma
`{"recuperados": [ ...registros como objetos... ], "sin_recuperar": 0, "primer_no_recuperado": 0}`
(con tus valores). Un registro cortado a medias **no** cuenta como recuperado.
