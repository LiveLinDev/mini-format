# Flujo de Git

Este repositorio usa una sola rama, `main`. Trabaja en la copia canónica sobre esa rama y publica en `origin/main` mediante un push normal.

Antes de editar, revisa el estado de la copia y ejecuta `git fetch --prune origin`. Si `main` solo está atrasada, sincronízala con `git merge --ff-only origin/main`. Si las dos copias tienen commits propios, integra ambos historiales en `main` y valida la fusión antes de publicar. Preserva las ediciones de otras sesiones.

Al terminar un envío, comprueba que `main` y `origin/main` apunten al mismo commit.
