# Perfil de dominio generado: mini-domain/1

[English](DOMAIN_PROFILE.md) · [Guía de integración](BUILD_GUIDE.es.md)

Este documento especifica el perfil JSON generado por la versión 1.2.1 del
software. No sustituye la [SPEC 1.1 del núcleo](SPEC.es.md). Las familias clásicas
y sus pruebas mantienen sintaxis y parsers propios. El perfil generado se procesa
con el parser de `mini build` o con `minifmt.domain`.

## Contrato

`contract.json` contiene `profile: "mini-domain/1"`, prefijo, versión `1`, esquema
recursivo, `record_path` (lista de claves de objeto o null) y `schema_id`. La huella
son los primeros doce caracteres hexadecimales SHA-256 del JSON compacto UTF-8
con, en este orden, `profile`, `prefix`, `version`, `schema`, `record_path`.
El orden de campos importa; las cantidades informativas de muestras no cambian
la identidad. Usa contratos de una construcción confiable: la huella es un
control de compatibilidad, no autenticación criptográfica.

Tipos: object, array, string, integer, number, boolean y `json` abierto. Los
objetos tienen campos ordenados `name`, `optional`, `schema`; las listas, `items`;
`nullable` permite null. Las claves desconocidas de objetos son errores. Un nodo
JSON abierto conserva deliberadamente cualquier JSON, incluidas claves nuevas.

La inferencia combina todos los documentos completos. Los miembros ausentes se
vuelven opcionales; null observado permite null. Campos sólo null, elementos de
listas vacías y tipos heterogéneos quedan como JSON abierto. Mezclas numéricas
amplían integer a number. Valores constantes observados nunca se convierten en
valores predeterminados permanentes del dominio.

## Documento transmitido

UTF-8, líneas físicas separadas por LF, con un LF final opcional:

```text
phone|v=1|n=2|h=<schema_id>
<celdas del registro 1>
<celdas del registro 2>
```

Cabecera: prefijo y `v`, `n`, `h` obligatorios; `m`, `d` y `e` opcionales.
Claves desconocidas o duplicadas producen error. `n` coincide exactamente con los
registros. Una huella distinta falla: no se intenta adivinar otro esquema.

Las filas usan celdas separadas por `|`, sin repetir una etiqueta por registro.
Objetos obligatorios no-nullables se aplanan recursivamente en orden del esquema;
objetos vacíos obligatorios se reconstruyen desde éste. Objetos opcionales o
nullables conservan una celda posicional. Registros escalares, listas, JSON abierto
u objetos nullables se representan en una celda completa. Una fila sin columnas
transmitidas se escribe `-`.

Escape de cada celda: `\\` representa barra inversa; `\|`, separador; `\n`, salto
de línea; `\r`, retorno. Otros escapes son inválidos. Los espacios son datos.

## Valores de celda

`?` significa miembro opcional ausente; `~`, null. No equivalen a cadena vacía,
cero o false. Las cadenas normalmente no llevan comillas. Cadena vacía, `?` o
`~` literales, y cadenas que empiezan por comillas se codifican como cadenas JSON;
después se aplica el escape exterior. Se rechazan números no finitos y claves
JSON duplicadas. Los valores numéricos no se convierten a otro tipo.

Objetos anidados son listas JSON posicionales en orden del esquema; `{}` marca
un miembro opcional ausente dentro de esas listas. Un nodo JSON abierto envuelve
su valor no-null como `[valor]`, evitando confundir un objeto vacío real con
ausencia. Las listas transforman sus elementos recursivamente; null sigue siendo
null. Primero se codifica JSON y después se escapa la celda exterior.

Si la colección está dentro de un objeto, `m` transmite todo el envoltorio como
JSON posicional con la colección sustituida por `[]`. Los metadatos viajan en el
documento, no se recuperan de las muestras. Listas raíz no llevan `m`; otras
raíces tienen exactamente un registro y tampoco llevan `m`.

## Optimización explícita por documento

`d` contiene JSON `[[indiceColumna, celdaCodificada], ...]`, índices desde cero.
Esas columnas se omiten de todas las filas y se restauran desde la cabecera.
Se calculan con el documento actual y se validan contra el mismo esquema.

`e` contiene JSON `[[indiceColumna, [celdaCadenaCodificada, ...]], ...]`. Cada
columna con diccionario sigue presente en la fila, mediante un índice decimal
desde cero. Sólo se permite para columnas string. Los diccionarios completos se
transmiten: no hay vocabulario oculto aprendido de las muestras. Una columna no
puede estar en `d` y `e` a la vez. Índices inválidos o duplicados producen error.
El JSON de cabecera recibe el mismo escape exterior.

El codificador aplica estas opciones cuando su estimación de bytes es favorable.
`encode(valor, contrato, shared=False)` desactiva `d`;
`encode(valor, contrato, dictionaries=False)` desactiva `e`. Pasa ambos argumentos
para desactivar las dos optimizaciones. Ahorrar bytes no garantiza ahorrar tokens
con cualquier tokenizador.

## Validación y evolución

Se comprueban identidad, escapes, columnas, tipos, nullabilidad, campos requeridos,
envoltorio y cantidad de registros. Los errores exponen código estable `D_*`,
línea física y ruta JSON. `diagnose` distingue líneas recuperables e inválidas;
`repair` corrige envoltorios de transporte. `apply_replacements` incorpora líneas
corregidas externamente y valida todo el documento.

No se ignoran campos nuevos silenciosamente. Reconstruye en otra carpeta con
ejemplos representativos y distribuye prompt, contrato y parser juntos. Validar
estructura no demuestra veracidad del modelo ni cumplimiento de reglas del negocio.
