# ADR 0008. Motor del playground generado desde la biblioteca TypeScript

* Estado: aceptada
* Fecha: 2026-09-17 (herramientas 1.2.0, SPEC 1.1)
* Especificación: [SPEC.md](../../SPEC.md) §2 (conformidad); suite en [conformance/](../../conformance/README.md)

## Contexto y problema

El playground (`playground/index.html` y su versión del sitio) validaba documentos con
`js/mini.js`, un port JavaScript escrito a mano de la referencia Python. Ese port no
ejecutaba la suite de conformidad y [ts/README.md](../../ts/README.md) registraba
diferencias de comportamiento con la referencia (documento vacío en modo tolerante,
escapes inválidos en la cabecera y en registros tolerantes, reserva de valores
`unique` en líneas rechazadas, validación de contratos, formato de flotantes, entre
otras). Un desarrollador podía obtener en el navegador un resultado distinto del de
la biblioteca.

## Alternativas consideradas

1. **Corregir el port manual** hasta aprobar la suite y añadirle un runner: mantiene tres
   implementaciones (Python, TypeScript y JavaScript) que deben evolucionar a la par.
2. **Generar `js/mini.js` desde la biblioteca TypeScript** (`ts/src`), que ya aprueba la
   suite, y verificar el resultado con toda la suite.
3. **Cargar el ESM de `ts/dist` en el playground** con `<script type="module">`: exige
   servir varios archivos y rompe el playground autocontenido de un solo HTML.

## Decisión

Se adopta la alternativa 2. [tools/build_js.mjs](../../tools/build_js.mjs) elimina los tipos de
cada módulo de `ts/src` con `stripTypeScriptTypes` de Node, los enlaza en orden
topológico dentro de ámbitos propios y produce un UMD sin dependencias que expone el
global `MINI`. El archivo generado se versiona para que `playground/build.py` y
`sitio/construir.py` lo incrusten sin cambios. [conformance/run_js.mjs](../../conformance/run_js.mjs)
ejecuta la suite contra el motor, y [tests/test_js_port.mjs](../../tests/test_js_port.mjs)
falla si `js/mini.js` no coincide con la generación actual o si algún caso falla.

## Consecuencias

* Existe un único comportamiento verificable en JavaScript: el del navegador es el de la
  biblioteca TypeScript.
* `js/mini.js` no se edita a mano; todo cambio se hace en `ts/src` y se regenera.
* El paquete solo incluye módulos alcanzables desde los de núcleo (`registry.ts` usa
  `import.meta` y `node:fs`, inexistentes en un script clásico del navegador).
* La API del objeto `MINI` conserva los nombres usados por el playground (`parse`,
  `dumps`, `specBlock`, `checkFork`, `normalizeContract`, `signature`,
  `Document.canonical()`) y añade el resto de la API pública de la biblioteca.

## Evidencia

* Diferencias previas del port manual: sección «Decisiones donde `js/mini.js`, la
  referencia Python y la SPEC difieren» de `ts/README.md` en la revisión `d4a1d44`.
* [tests/test_js_port.mjs](../../tests/test_js_port.mjs): comprobación de actualización y
  ejecución de los 372 casos de la suite 1.1 contra `js/mini.js`.
* [conformance/README.md](../../conformance/README.md): semántica común de los runners.
