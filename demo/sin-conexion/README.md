# Demostración sin conexión

Reproduce el flujo de integración de mini-format sin acceso a la red: contrato, instrucción generada desde el
contrato, lectura en streaming de una respuesta real archivada (`generative/raw/e1/haiku/mini/1.txt`,
modelo `claude-haiku-4-5-20251001`), validación con código y línea, reparación selectiva y objetos tipados.

```bash
python demo/sin-conexion/demo.py            # con pausas breves para exponer el streaming
python demo/sin-conexion/demo.py --rapido   # sin pausas
```

La red se bloquea durante la ejecución. Para mostrar la reparación, la demostración altera deliberadamente dos
líneas de la respuesta grabada y reproduce la respuesta de reparación con las líneas originales; no se invoca
ningún modelo. La prueba `tests/test_demo_sin_conexion.py` verifica el flujo completo y el límite de 3 minutos.
English: [README.en.md](README.en.md).
