# HISTÓRICO — no es el piloto vigente y NO se reproduce a HEAD

Estos archivos los generó el arnés ANTERIOR (brazos A «pipe» escrito a mano, B, C, D y D+R) en el commit `0cfa477`,
con el adaptador **simulado**. Se conservan solo como registro de cómo era el arnés; no se citan como resultados.

Por qué ya no se reproduce:

* Reejecutado en `d10eb6e` (HEAD de la auditoría) el piloto da A, B y C idénticos pero **D y D+R distintos**
  (p. ej. extracción D: incorrectos sin aviso 4,04 % pasa a 2,53 %; llamadas de reparación en V2, de 29 a 36).
  La causa no es el arnés sino el núcleo: entre `0cfa477` y HEAD cambiaron `parser.py`, `values.py`,
  `serializer.py`, `codec.py` y `contract.py` (SPEC 1.1), y el lector .mini forma parte del tratamiento del brazo D.
* El diseño cambió (Plan de Validación v3): el brazo A es ahora JSON con instrucción mínima, D+R se llama D+1 y
  cada formato tiene su reparación (A+1, B+1, C+1, D+1). Las métricas separan sintaxis, contrato y exactitud.

El piloto vigente está en `../piloto/` y su corrida emitida en `evidencia/corridas/v2-simulado-piloto/`.
El manifiesto nuevo guarda hashes del núcleo (`nucleo_minifmt_sha256`) para que un cambio del lector se vea.
