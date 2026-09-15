# Banco de pruebas .mini

Página autocontenida que procesa la misma extracción de 12 reclamos de clientes con tres enfoques:
un prompt propio leído con `split('|')`, JSON sin modo estructurado y la biblioteca .mini (`js/mini.js`).
Muestra cuatro casos: respuesta completa, separador sin escapar, respuesta cortada y valores fuera del contrato.

Las respuestas son ejemplos construidos para reproducir fallas conocidas; no son salidas registradas de un modelo.

## Regenerar

```bash
python demo/banco-pruebas/datos_demo.py     # contrato, respuestas por caso y conteo de tokens (tiktoken)
python demo/banco-pruebas/build_demo.py     # incrusta js/mini.js, logica.js y los datos en la página
```

Abrir `banco_pruebas_mini.html` en el navegador; funciona sin conexión (las fuentes tipográficas usan una alternativa local si no hay red).

| Archivo | Función |
|---|---|
| `datos_demo.py` | Genera `datos_demo.json` con el contrato `rec`, los datos esperados, las respuestas de cada caso y los tokens. |
| `logica.js` | Clasifica cada registro por enfoque: correcto, incorrecto sin aviso, perdido sin aviso o detectado. |
| `plantilla.html` | Interfaz de la página. |
| `build_demo.py` | Ensambla `banco_pruebas_mini.html`. |
