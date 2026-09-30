# Economía de .mini frente a JSON

Cálculo **exacto** de ahorro, costo por categorías, costo por mil registros válidos, escenarios A y B y
punto de equilibrio. Una sola biblioteca de referencia en Python (`calculo.py`, solo biblioteca estándar) y un
espejo en JavaScript (`sitio/economia-calculo.js`, sin DOM) que dan **las mismas cadenas** para las mismas
entradas: los dos se prueban contra `evidencia/vectores/economia.json`
(`tests/test_infra_economia.py` y `node tests/test_economia_js.mjs`).

## Política numérica

* Aritmética racional exacta con enteros; ningún `float`/`Number` no entero entra en una cuenta (los
  decimales se pasan como **cadenas**: `"0.075"`). Un `float` se rechaza con `TypeError`.
* El redondeo ocurre **una sola vez por cifra de salida**, sobre el valor exacto, con **ROUND_HALF_UP**
  (los empates van a la mayor magnitud: `0.0000005` -> `0.000001`). Decimales: USD 6 (USD 9 en los
  diferenciales por registro del punto de equilibrio), porcentajes 4, razones 6, lotes fraccionarios 4, tokens y
  registros contables 0.
* Las cantidades contables (lotes posibles, registros útiles, tokens de capacidad) se redondean **hacia abajo**:
  no se prometen lotes ni registros parciales. Los lotes se calculan con el costo exacto por lote, no con el
  costo ya redondeado que se muestra.
* Nada se inventa: sin tarifa verificada, o con un precio ausente para una categoría que sí se usó, el costo es
  `None` con `estado` y `motivo` (`tarifa_no_verificada`); un dato de usage ausente es `None`
  (`usage_no_informado`), nunca 0. Con 0 registros válidos el costo por 1000 válidos es **no definido**
  (`None`) y se informa el costo incurrido.

## Entradas

`tarifa` (una por modelo; la consulta es por `(proveedor, modelo_api_id)` y acepta `alias`):

```json
{"proveedor": "OpenAI", "modelo_api_id": "gpt-5.4-mini", "moneda": "USD",
 "entrada_sin_cache_por_millon": "0.75", "entrada_cache_lectura_por_millon": "0.075",
 "entrada_cache_escritura_por_millon": null, "salida_por_millon": "4.5",
 "estado": "verificada", "fecha_consulta_utc": "2026-09-30T18:10:00Z", "url_oficial": "https://..."}
```

`solicitud` (la estructura acordada con el arnés; `grupo` = id de la solicitud **original**; si falta, `grupo = id`):

```json
{"id": "g1", "grupo": "g1", "registros_solicitados": 10, "registros_validos_finales": 10,
 "intentos": [{"fase": "generacion|reparacion|validacion|otro", "modelo": "gpt-5.4-mini", "proveedor": "OpenAI", "latencia_s": "1.2",
   "usage": {"entrada_sin_cache": 1000, "entrada_cache_lectura": 0, "entrada_cache_escritura": 0, "salida": 400,
             "razonamiento": 0, "razonamiento_incluido_en_salida": true, "otros_usd": {"busqueda_web": "0.01"}}}]}
```

Reglas de agrupación: el costo total suma **todos** los intentos de **todas** las solicitudes (incluidas las
reparaciones) y se agrupa por `grupo`. Los registros solicitados y válidos finales de un grupo son los de la
solicitud original (`id == grupo`); si no hay original, todas las que los declaran deben coincidir (si no, error).
Así una reparación nunca suma dos veces los válidos.

`perfil` de un formato (para los escenarios y el punto de equilibrio): `tokens_instruccion`, `instruccion_en_cache`,
`tokens_entrada_por_registro`, `tokens_salida_por_registro`, `tokens_salida_fijos`, `fraccion_validos`,
`reintentos_por_lote`, `fraccion_reparada` (un reintento reenvía la entrada y regenera esa fracción de la salida).

## Fórmulas

Sea `M = 1 000 000`, `p_e`, `p_c`, `p_w`, `p_s` los precios por millón (entrada sin caché, lectura y escritura de caché,
salida), `T_MINI` y `T_JSON` los tokens de salida medidos.

| Magnitud | Fórmula |
|---|---|
| Razón | `r = T_MINI / T_JSON` (con `T_JSON = 0`: no definida) |
| Ahorro de salida | `ahorro_salida_pct = 100 x (1 - r)` (negativo si .mini es más largo) |
| Costo de salida | `costo_salida = T x p_s / M` |
| Costo de un intento, por categorías **no solapadas** | `entrada_sin_cache x p_e/M + entrada_cache_lectura x p_c/M + entrada_cache_escritura x p_w/M + salida x p_s/M + razonamiento_aparte x p_s/M + otros_usd` |
| Razonamiento sin doble conteo | si `razonamiento_incluido_en_salida = true`, `razonamiento_aparte = 0` (ya está en `salida`); si `false`, se factura aparte al precio de salida |
| Costo total | suma de todos los intentos de todas las solicitudes, por grupo original |
| Costo por 1000 válidos | `1000 x costo_total / registros_validos_finales` (0 válidos: no definido + costo incurrido) |
| Costo de un lote de `k` registros | `entrada = (I x p_instr + k x e x p_e)/M` ; `salida = (o x k + c) x p_s/M` ; `reintentos = R x (entrada + fr x salida)` ; `costo_lote = entrada + salida + reintentos` (`p_instr = p_c` si la instrucción va en caché) |
| Escenario A, solo salida | `costo_JSON = Tref x p_s/M` ; `costo_MINI = Tref x r x p_s/M` (`Tref` = 1 000 000 tokens JSON de referencia) |
| Escenario A, total | `lotes = Tref / tokens_salida_lote_JSON` ; `costo_formato = lotes x costo_lote_formato` (mismos lotes y registros: el mismo trabajo) |
| Escenario B | `lotes = floor(presupuesto / costo_lote)` ; `registros_utiles = floor(lotes x k x fraccion_validos)` ; variante `solo_salida`: `costo_lote = (o x k + c) x p_s/M` (sin instrucción, entrada ni reintentos) |
| Punto de equilibrio | `costo(k) = A + B k` (lineal); `Delta(k) = costo_JSON(k) - costo_MINI(k) = a k + b`; ahorro neto si `Delta(k) > 0` (un empate no cuenta) |

Punto de equilibrio: `a > 0` y `Delta(1) > 0` -> ahorra desde 1 registro; `a > 0` y `Delta(1) <= 0` -> ahorra desde
`k* = floor(-b/a) + 1`; `a < 0` y `Delta(1) > 0` -> ahorra solo hasta `ceil(b/(-a)) - 1`; en los demás casos **no hay
ahorro neto** y el resultado lo dice con `estado = "sin_ahorro_neto"` y un mensaje explícito (ES/EN). Se calcula en
dos variantes: `solo_salida` y `total` (instrucción + entrada + salida + reintentos).

## Ejemplo comprobado a mano

Tarifa gpt-5.4-mini: `p_e = 0.75`, `p_c = 0.075`, `p_s = 4.5` USD por millón. JSON compacto: `I = 289`, `o = 40`, `c = 6`,
`R = 0.1`, `fr = 1`, válidos 96 %; `.mini`: `I = 416`, `o = 26`, `c = 2`, `R = 0.05`, `fr = 0.1`, válidos 99 %; lote de `k = 25`.

| Paso | Cuenta | Resultado |
|---|---|---|
| Razón con 650 frente a 1000 tokens | `650 / 1000` | `r = 0.650000`, ahorro `35.0000 %` |
| A, solo salida, JSON | `1 000 000 x 4.5 / 1 000 000` | `4.500000` USD |
| A, solo salida, .mini | `650 000 x 4.5 / 1 000 000` | `2.925000` USD (ahorro `1.575000` USD = 35 %) |
| Lote JSON: entrada | `289 x 0.75 / 1e6` | `0.00021675` |
| Lote JSON: salida | `(40 x 25 + 6) = 1006` tokens `x 4.5 / 1e6` | `0.004527` |
| Lote JSON: reintentos | `0.1 x (0.00021675 + 0.004527)` | `0.000474375` |
| Lote JSON total | suma | `0.005218125` -> `0.005218` USD |
| Lote .mini: entrada / salida / reintentos | `416 x 0.75 / 1e6` ; `(26 x 25 + 2) = 652` x `4.5 / 1e6` ; `0.05 x (0.000312 + 0.1 x 0.002934)` | `0.000312` ; `0.002934` ; `0.00003027` |
| Lote .mini total | suma | `0.00327627` -> `0.003276` USD |
| B con US$ 1 000 (ilustrativo) | `floor(1000 / 0.005218125)` ; `floor(1000 / 0.00327627)` | `191 639` y `305 225` lotes |
| Registros útiles | `floor(191 639 x 25 x 0.96)` ; `floor(305 225 x 25 x 0.99)` | `4 599 336` y `7 554 318` (+64.2480 %) |
| A, total | `lotes = 1e6 / 1006 = 994.0358` ; `x 0.005218125` ; `x 0.00327627` | `5.187003` y `3.256730` USD (ahorro 37.2137 %) |

Las cifras anteriores están en `evidencia/vectores/economia.json` y las repitió un oráculo independiente
(`decimal.Decimal`, ROUND_HALF_UP) en las pruebas.

## Supuestos que conviene recordar

* El costo de un lote es lineal en `k`. Los perfiles salen de tokens **medidos**; este módulo no mide tokens.
* Los tokens locales (tiktoken) son una **aproximación** fuera de OpenAI en texto plano (ver la nota de tokenizadores
  en `evidencia/tarifas/tarifas.json`); para costo real se usan los `usage` de las respuestas.
* La tarifa de DeepSeek es la de horario pico; fuera de pico es la mitad. Las tarifas con fecha de vigencia (Gemini Flash
  promocional hasta 2026-12-31) están fechadas en `tarifas.json`.
* US$ 1 000 es un presupuesto **ilustrativo** de la interfaz: no autoriza gastar nada.
