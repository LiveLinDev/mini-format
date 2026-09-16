# Versiones y compatibilidad

mini-format **1.1.0** distribuye el perfil base **SPEC 1.0** y el toolkit de dominio generado **`mini-domain/1`**. La versión del paquete identifica las herramientas; la versión del contrato identifica los datos que puede leer cada parser.

## Campos añadidos al final

En el perfil base, un lector acepta campos finales desconocidos únicamente cuando el prefijo coincide y la cabecera declara `v` mayor que la versión del contrato. Valida los campos conocidos y descarta la cola desconocida del objeto canónico. Los escapes de la línea siguen teniendo que ser válidos.

Con la misma versión, demasiados campos producen `E05`. Un cambio del núcleo o un prefijo diferente requiere otro contrato. La compatibilidad no sustituye a una migración entre dominios.

## Diagnósticos

Los errores del perfil base incluyen código, línea, campo y mensaje. Estos identificadores permiten conservar los registros válidos y dirigir el reintento al dato rechazado.

## Toolkit generado

El contrato, el prompt y las herramientas generadas forman una unidad. Reutiliza esa unidad y controla sus versiones junto con tu aplicación. Cuando cambies las muestras, genera y verifica una versión nueva antes de incorporarla al flujo. La [guía del toolkit](/docs/build/) distingue sus capacidades de las del perfil base.

## Distribución

[Toolkit ZIP](/downloads/mini-format-1.1.0.zip), [wheel Python](/downloads/mini_format-1.1.0-py3-none-any.whl), [paquete TypeScript](/downloads/mini-format-core-1.1.0.tgz) y [código fuente](/downloads/mini-format-1.1.0-source.zip). Estas descargas no requieren una cuenta ni acceso a un repositorio privado.
