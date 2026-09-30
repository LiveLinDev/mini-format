# T1 (.mini) · variante A · tope 30 minutos

**Situación.** Una aplicación de mesa de ayuda recibe la respuesta de un modelo de lenguaje con tickets y debe
usarla. Tu trabajo es completar un cliente pequeño que lea la respuesta, la valide contra el contrato y
entregue los registros buenos aunque alguno venga mal.

**Qué recibes**

- `respuesta.mini`: Una respuesta de un modelo en formato `.mini`: una línea de cabecera y un ticket de soporte por línea.
- `contrato_tk.json`: el contrato que la aplicación ya tenía.
- `cliente.py`: esqueleto con la función `procesar(texto)` por completar. Puedes escribir tu cliente en Python
  o en TypeScript; lo único que se comprueba es el archivo de salida.

**Qué debe hacer `procesar`**

1. Leer la respuesta y validar **cada registro** contra el contrato.
2. Devolver `{"validos": [...], "rechazados": [...]}`.
3. `validos`: los registros que cumplen el contrato, **tal como vienen** (mismos valores, mismos tipos, mismo
   orden). No se corrige ni se adivina ningún valor.
4. `rechazados`: un elemento `{"posicion": N, "motivo": "..."}` por cada registro que incumple el contrato.
   `posicion` es el número de orden del registro dentro de la respuesta, empezando en 1. El motivo es texto libre.
5. Un registro inválido **no** debe tumbar ni alterar a los válidos.

**Entrega.** Ejecuta tu cliente sobre `respuesta.mini` y guarda el resultado en `entrega/salida_T1.json`.

**Herramientas.** La biblioteca `minifmt` (ya instalada) y la guía `../guia_mini.md`. Puedes usar la documentación que quieras.

**Terminas** cuando el observador confirme que tu entrega cumple el criterio, o cuando se acabe el tope.
No hay puntos por estilo: importa que el resultado sea correcto.
