# Resumen del experimento generativo — import_todos

> **MATERIAL ASISTIDO POR IA.** Las respuestas las produjo una IA en sesión (sin usage ni factura de API); los tokens, si aparecen, son un conteo local aproximado. Sirve para probar el análisis, no es una corrida de API ni se presenta como tal.

Muestras: 1241 · commit: `` · adaptador: importado · procedencia: asistido_ia

Estado del estudio: **parcial** · celdas {'hecha': 1241, 'pendiente': 19, 'bloqueado': 0, 'no_aplicable': 0, 'error_tecnico': 0} · gasto {'gastado_usd': '0', 'incierto_usd': '0', 'llamadas': 0}

Validez final = registros válidos / registros SOLICITADOS (los ausentes cuentan como no válidos). IC 95 %: bootstrap de conglomerados por solicitud (nunca por registro o campo). Sintaxis: IC de Wilson por muestra. Los costos dependen de tarifas verificadas; sin ellas son «tarifa no verificada».

## Por brazo

| exp. | tipo | brazo | muestras | sintaxis analizable % [IC95] | cumple contrato % (de los aceptados) | exactitud de contenido % [IC95 solic.] | validez final % [IC95 solic.] | incorrectos sin aviso % | perdidos sin aviso % | perdidos con aviso % | tok. entrada | tok. salida | latencia mediana s | p95 s | n | USD / 1000 válidos |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v2 | extraccion | A | 150 | 100.0 [97.5–100.0] | 79.95 | 79.7 [73.7–86.4] | 79.8 [73.8–86.4] | 20.06 | 0.24 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | A+1 | 150 | 100.0 [97.5–100.0] | 100.0 | 85.7 [79.7–90.7] | 88.4 [83.1–92.7] | 2.73 | 0.24 | 11.33 | — | — | — | — | 0 | — |
| v2 | extraccion | B | 150 | 100.0 [97.5–100.0] | 100.0 | 100.0 [100.0–100.0] | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | B+1 | 150 | 100.0 [97.5–100.0] | 100.0 | 100.0 [100.0–100.0] | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | D | 150 | 100.0 [97.5–100.0] | 100.0 | 98.7 [98.1–99.3] | 99.9 [99.8–100.0] | 1.21 | 0.0 | 0.06 | — | — | — | — | 0 | — |
| v2 | extraccion | D+1 | 150 | 100.0 [97.5–100.0] | 100.0 | 98.8 [98.2–99.4] | 100.0 [100.0–100.0] | 1.21 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | generativa | A | 60 | 95.0 [86.3–98.3] | 10.53 | — | 10.0 [3.3–20.0] | 85.0 | 0.0 | 5.0 | — | — | — | — | 0 | — |
| v2 | generativa | A+1 | 46 | 100.0 [92.3–100.0] | 100.0 | — | 21.7 [10.9–34.8] | 0.0 | 0.0 | 78.26 | — | — | — | — | 0 | — |
| v2 | generativa | B | 60 | 96.7 [88.6–99.1] | 99.37 | — | 96.1 [90.9–99.7] | 0.61 | 0.0 | 3.33 | — | — | — | — | 0 | — |
| v2 | generativa | B+1 | 59 | 100.0 [93.9–100.0] | 100.0 | — | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | generativa | D | 60 | 100.0 [94.0–100.0] | 100.0 | — | 97.0 [93.6–98.9] | 0.0 | 0.0 | 3.03 | — | — | — | — | 0 | — |
| v2 | generativa | D+1 | 56 | 100.0 [93.6–100.0] | 100.0 | — | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |

## Por brazo y modelo

| exp. | tipo | brazo | modelo | muestras | sintaxis analizable % [IC95] | cumple contrato % (de los aceptados) | exactitud de contenido % [IC95 solic.] | validez final % [IC95 solic.] | incorrectos sin aviso % | perdidos sin aviso % | perdidos con aviso % | tok. entrada | tok. salida | latencia mediana s | p95 s | n | USD / 1000 válidos |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v2 | extraccion | A | asistido_ia:claude-haiku-5-5 | 50 | 100.0 [92.9–100.0] | 80.0 | 80.0 [70.0–90.0] | 80.0 [70.0–90.0] | 20.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | A | asistido_ia:claude-opus-5-5 | 50 | 100.0 [92.9–100.0] | 80.0 | 80.0 [70.0–90.0] | 80.0 [70.0–90.0] | 20.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | A | asistido_ia:kimi-k3.1-pro | 50 | 100.0 [92.9–100.0] | 79.85 | 79.1 [68.2–89.1] | 79.3 [68.5–89.3] | 20.18 | 0.73 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | A+1 | asistido_ia:claude-haiku-5-5 | 50 | 100.0 [92.9–100.0] | 100.0 | 84.0 [72.0–94.0] | 84.0 [72.0–94.0] | 0.0 | 0.0 | 16.0 | — | — | — | — | 0 | — |
| v2 | extraccion | A+1 | asistido_ia:claude-opus-5-5 | 50 | 100.0 [92.9–100.0] | 100.0 | 90.0 [80.0–96.0] | 98.0 [92.0–100.0] | 8.0 | 0.0 | 2.0 | — | — | — | — | 0 | — |
| v2 | extraccion | A+1 | asistido_ia:kimi-k3.1-pro | 50 | 100.0 [92.9–100.0] | 100.0 | 83.1 [71.1–92.2] | 83.3 [71.3–92.5] | 0.18 | 0.73 | 16.0 | — | — | — | — | 0 | — |
| v2 | extraccion | B | asistido_ia:claude-haiku-5-5 | 50 | 100.0 [92.9–100.0] | 100.0 | 100.0 [100.0–100.0] | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | B | asistido_ia:claude-opus-5-5 | 50 | 100.0 [92.9–100.0] | 100.0 | 100.0 [100.0–100.0] | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | B | asistido_ia:kimi-k3.1-pro | 50 | 100.0 [92.9–100.0] | 100.0 | 100.0 [100.0–100.0] | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | B+1 | asistido_ia:claude-haiku-5-5 | 50 | 100.0 [92.9–100.0] | 100.0 | 100.0 [100.0–100.0] | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | B+1 | asistido_ia:claude-opus-5-5 | 50 | 100.0 [92.9–100.0] | 100.0 | 100.0 [100.0–100.0] | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | B+1 | asistido_ia:kimi-k3.1-pro | 50 | 100.0 [92.9–100.0] | 100.0 | 100.0 [100.0–100.0] | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | D | asistido_ia:claude-haiku-5-5 | 50 | 100.0 [92.9–100.0] | 100.0 | 97.5 [95.8–98.7] | 100.0 [100.0–100.0] | 2.55 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | D | asistido_ia:claude-opus-5-5 | 50 | 100.0 [92.9–100.0] | 100.0 | 100.0 [100.0–100.0] | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | D | asistido_ia:kimi-k3.1-pro | 50 | 100.0 [92.9–100.0] | 100.0 | 98.7 [98.0–99.6] | 99.8 [99.5–100.0] | 1.09 | 0.0 | 0.18 | — | — | — | — | 0 | — |
| v2 | extraccion | D+1 | asistido_ia:claude-haiku-5-5 | 50 | 100.0 [92.9–100.0] | 100.0 | 97.5 [95.8–98.7] | 100.0 [100.0–100.0] | 2.55 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | D+1 | asistido_ia:claude-opus-5-5 | 50 | 100.0 [92.9–100.0] | 100.0 | 100.0 [100.0–100.0] | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | extraccion | D+1 | asistido_ia:kimi-k3.1-pro | 50 | 100.0 [92.9–100.0] | 100.0 | 98.9 [98.0–99.6] | 100.0 [100.0–100.0] | 1.09 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | generativa | A | asistido_ia:claude-haiku-5-5 | 20 | 90.0 [69.9–97.2] | 22.22 | — | 20.0 [5.0–40.0] | 70.0 | 0.0 | 10.0 | — | — | — | — | 0 | — |
| v2 | generativa | A | asistido_ia:claude-opus-5-5 | 20 | 95.0 [76.4–99.1] | 10.53 | — | 10.0 [0.0–25.0] | 85.0 | 0.0 | 5.0 | — | — | — | — | 0 | — |
| v2 | generativa | A | asistido_ia:kimi-k3.1-pro | 20 | 100.0 [83.9–100.0] | 0.0 | — | 0.0 [0.0–0.0] | 100.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | generativa | A+1 | asistido_ia:claude-haiku-5-5 | 20 | 100.0 [83.9–100.0] | 100.0 | — | 25.0 [5.0–45.0] | 0.0 | 0.0 | 75.0 | — | — | — | — | 0 | — |
| v2 | generativa | A+1 | asistido_ia:claude-opus-5-5 | 20 | 100.0 [83.9–100.0] | 100.0 | — | 25.0 [5.0–45.0] | 0.0 | 0.0 | 75.0 | — | — | — | — | 0 | — |
| v2 | generativa | A+1 | asistido_ia:kimi-k3.1-pro | 6 | 100.0 [61.0–100.0] | — | — | 0.0 [0.0–0.0] | 0.0 | 0.0 | 100.0 | — | — | — | — | 0 | — |
| v2 | generativa | B | asistido_ia:claude-haiku-5-5 | 20 | 95.0 [76.4–99.1] | 99.04 | — | 94.1 [83.6–100.0] | 0.91 | 0.0 | 5.0 | — | — | — | — | 0 | — |
| v2 | generativa | B | asistido_ia:claude-opus-5-5 | 20 | 100.0 [83.9–100.0] | 99.09 | — | 99.1 [97.3–100.0] | 0.91 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | generativa | B | asistido_ia:kimi-k3.1-pro | 20 | 95.0 [76.4–99.1] | 100.0 | — | 95.0 [85.0–100.0] | 0.0 | 0.0 | 5.0 | — | — | — | — | 0 | — |
| v2 | generativa | B+1 | asistido_ia:claude-haiku-5-5 | 20 | 100.0 [83.9–100.0] | 100.0 | — | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | generativa | B+1 | asistido_ia:claude-opus-5-5 | 20 | 100.0 [83.9–100.0] | 100.0 | — | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | generativa | B+1 | asistido_ia:kimi-k3.1-pro | 19 | 100.0 [83.2–100.0] | 100.0 | — | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | generativa | D | asistido_ia:claude-haiku-5-5 | 20 | 100.0 [83.9–100.0] | 100.0 | — | 94.1 [87.7–100.0] | 0.0 | 0.0 | 5.91 | — | — | — | — | 0 | — |
| v2 | generativa | D | asistido_ia:claude-opus-5-5 | 20 | 100.0 [83.9–100.0] | 100.0 | — | 99.5 [98.6–100.0] | 0.0 | 0.0 | 0.45 | — | — | — | — | 0 | — |
| v2 | generativa | D | asistido_ia:kimi-k3.1-pro | 20 | 100.0 [83.9–100.0] | 100.0 | — | 97.3 [94.1–99.5] | 0.0 | 0.0 | 2.73 | — | — | — | — | 0 | — |
| v2 | generativa | D+1 | asistido_ia:claude-haiku-5-5 | 20 | 100.0 [83.9–100.0] | 100.0 | — | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | generativa | D+1 | asistido_ia:claude-opus-5-5 | 20 | 100.0 [83.9–100.0] | 100.0 | — | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |
| v2 | generativa | D+1 | asistido_ia:kimi-k3.1-pro | 16 | 100.0 [80.6–100.0] | 100.0 | — | 100.0 [100.0–100.0] | 0.0 | 0.0 | 0.0 | — | — | — | — | 0 | — |

## Desenlaces de la respuesta (recuento de muestras)

| experimento | tipo tarea | brazo | muestras | ok | formato invalido | vacia | truncada | negativa | error tecnico |
|---|---|---|---|---|---|---|---|---|---|
| v2 | extraccion | A | 150 | 150 | 0 | 0 | 0 | 0 | 0 |
| v2 | extraccion | A+1 | 150 | 150 | 0 | 0 | 0 | 0 | 0 |
| v2 | extraccion | B | 150 | 150 | 0 | 0 | 0 | 0 | 0 |
| v2 | extraccion | B+1 | 150 | 150 | 0 | 0 | 0 | 0 | 0 |
| v2 | extraccion | D | 150 | 149 | 1 | 0 | 0 | 0 | 0 |
| v2 | extraccion | D+1 | 150 | 149 | 1 | 0 | 0 | 0 | 0 |
| v2 | generativa | A | 60 | 57 | 3 | 0 | 0 | 0 | 0 |
| v2 | generativa | A+1 | 46 | 43 | 3 | 0 | 0 | 0 | 0 |
| v2 | generativa | B | 60 | 58 | 2 | 0 | 0 | 0 | 0 |
| v2 | generativa | B+1 | 59 | 58 | 1 | 0 | 0 | 0 | 0 |
| v2 | generativa | D | 60 | 52 | 8 | 0 | 0 | 0 | 0 |
| v2 | generativa | D+1 | 56 | 52 | 4 | 0 | 0 | 0 | 0 |

## Comparaciones pareadas (EXPLORATORIAS: sin corrección por comparaciones múltiples)

| exp. | y − x | qué compara | pares | misma respuesta | validez x % | validez y % | dif. pp | IC solic. inf | IC solic. sup | IC doc. inf | IC doc. sup |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v2 | D − B | formato: JSON con contrato frente a .mini | 210 | False | 98.87 | 99.09 | 0.22 | -1.13 | 1.99 | -2.25 | 2.55 |
| v2 | D − A | formato: JSON mínimo frente a .mini | 210 | False | 59.83 | 99.09 | 39.26 | 32.81 | 45.06 | 13.42 | 60.95 |
| v2 | D+1 − B+1 | formato con reparación en ambos: JSON con contrato frente a .mini | 205 | False | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| v2 | D+1 − A+1 | formato con reparación en ambos: JSON mínimo frente a .mini | 196 | False | 72.77 | 100.0 | 27.23 | 21.43 | 33.53 | 6.17 | 50.77 |
| v2 | B − A | contrato en el prompt: A frente a B | 210 | False | 59.83 | 98.87 | 39.05 | 32.16 | 45.11 | 13.81 | 62.55 |
| v2 | A+1 − A | estrategia: reparar JSON mínimo | 196 | True | 64.1 | 72.77 | 8.67 | 5.1 | 12.76 | 0.0 | 18.33 |
| v2 | B+1 − B | estrategia: reparar JSON con contrato | 209 | True | 99.35 | 100.0 | 0.65 | 0.0 | 1.96 | 0.0 | 1.61 |
| v2 | D+1 − D | estrategia: reparar .mini | 206 | True | 99.34 | 100.0 | 0.66 | 0.09 | 1.41 | 0.0 | 2.0 |

## Reparación selectiva (X frente a X+1, sobre la misma respuesta)

| experimento | tipo tarea | brazo base | brazo reparado | pares | muestras reparadas | llamadas reparacion | registros validos ganados | registros correctos ganados | cambio incorrectos sin aviso | muestras con cambio adverso | registros adversos | lineas no recuperadas | validos sobrescritos | identidades duplicadas finales | identidades inventadas | correcciones rechazadas identidad | reparaciones auditadas | exactas base | exactas reparadas | tokens reparacion total | tokens por registro ganado | salida reparacion vs generacion pct | costo reparacion usd |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v2 | extraccion | A | A+1 | 150 | 30 | 30 | 143 | 99 | -286 | 0 | 0 | 187 | 0 | 0 | 0 | 0 | 30 | 119 | 128 | 0 | 0.0 | — | — |
| v2 | extraccion | B | B+1 | 150 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | — | 0 | 150 | 150 | 0 | — | — | — |
| v2 | extraccion | D | D+1 | 150 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | 1 | 132 | 133 | 0 | 0.0 | — | — |
| v2 | generativa | A | A+1 | 46 | 40 | 40 | 44 | 44 | -407 | 0 | 0 | 396 | 0 | 0 | 0 | 0 | 40 | 6 | 10 | 0 | 0.0 | — | — |
| v2 | generativa | B | B+1 | 59 | 4 | 4 | 15 | 15 | -4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 55 | 59 | 0 | 0.0 | — | — |
| v2 | generativa | D | D+1 | 56 | 4 | 4 | 14 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | 4 | 52 | 56 | 0 | 0.0 | — | — |

## V4 · latencia del flujo completo y costo

| experimento | brazo | modelo completo | muestras | latencia flujo mediana s | latencia flujo p95 s | latencia n | latencia excluidas error tecnico | latencia origen | costo usd total | costo solicitud mediana usd | costo por 1000 validos usd | costo nota | validos finales | intentos totales | intentos fallidos |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v2 | A | asistido_ia:claude-haiku-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 484 | 70 | 0 |
| v2 | A | asistido_ia:claude-opus-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 462 | 70 | 0 |
| v2 | A | asistido_ia:kimi-k3.1-pro | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 436 | 70 | 0 |
| v2 | A+1 | asistido_ia:claude-haiku-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 517 | 96 | 0 |
| v2 | A+1 | asistido_ia:claude-opus-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 594 | 98 | 0 |
| v2 | A+1 | asistido_ia:kimi-k3.1-pro | 56 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 458 | 72 | 0 |
| v2 | B | asistido_ia:claude-haiku-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 757 | 70 | 0 |
| v2 | B | asistido_ia:claude-opus-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 768 | 70 | 0 |
| v2 | B | asistido_ia:kimi-k3.1-pro | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 759 | 70 | 0 |
| v2 | B+1 | asistido_ia:claude-haiku-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 770 | 73 | 0 |
| v2 | B+1 | asistido_ia:claude-opus-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 770 | 71 | 0 |
| v2 | B+1 | asistido_ia:kimi-k3.1-pro | 69 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 759 | 69 | 0 |
| v2 | D | asistido_ia:claude-haiku-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 757 | 70 | 0 |
| v2 | D | asistido_ia:claude-opus-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 769 | 70 | 0 |
| v2 | D | asistido_ia:kimi-k3.1-pro | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 763 | 70 | 0 |
| v2 | D+1 | asistido_ia:claude-haiku-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 770 | 73 | 0 |
| v2 | D+1 | asistido_ia:claude-opus-5-5 | 70 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 770 | 71 | 0 |
| v2 | D+1 | asistido_ia:kimi-k3.1-pro | 66 | — | — | 0 | 0 | no_medida | — | — | — | sin usage ni factura de API (asistido_ia) | 726 | 67 | 0 |

## Meta V2 (criterio fijado antes de analizar)

Resultado: **no_evaluable**. el material no es api_real (simulado, asistido por IA o mezclado): una meta no se evalúa con él

## V3a heredada (exploratoria) · cortes sobre salidas guardadas

La V3a del Plan (documento canónico, fracciones predefinidas, JSON parcial y JSON Lines) está en `experiments/truncamiento`; esta tabla corta las respuestas guardadas de cada brazo y deja el denominador cero como vacío.

| brazo | cortes | muestras | recuperados media | ideal media | cortes sin ideal | eficiencia media pct | recuperados sobre ideal pct | cero recuperados pct | cero ic inf | cero ic sup | incorrectos sin aviso total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 4200 | 210 | 0.0 | 3.34 | 1682 | 0.0 | 0.1 | 100.0 | 99.9 | 100.0 | 0 |
| B | 4200 | 210 | 0.0 | 5.51 | 40 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 0 |
| D | 4200 | 210 | 5.26 | 5.33 | 4 | 90.3 | 98.6 | 4.7 | 3.9 | 5.5 | 187 |

