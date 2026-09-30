#!/usr/bin/env bash
# Receptor del despliegue de mini-format.pmoluna.com.
#
# Se instala en el servidor como ~/bin/recibir-sitio-mini y se ata a la llave de
# despliegue con `restrict,command="..."` en ~/.ssh/authorized_keys. Esa llave
# NO abre shell: cualquier conexión con ella ejecuta solo este script, que lee un
# .tar.gz por la entrada estándar y lo publica en /var/www/mini-format.
#
# Comandos admitidos (SSH_ORIGINAL_COMMAND):
#   desplegar   (por defecto)  publica el tar recibido
#   revertir                   vuelve a la versión anterior
set -euo pipefail
umask 022

RAIZ=/var/www/mini-format
NUEVO="$RAIZ/.nuevo"          # Nginx niega rutas con punto: nunca se sirven
ANTERIOR="$RAIZ/.anterior"
RESPALDOS="$HOME/respaldos"
MAX_BYTES=$((60 * 1024 * 1024))

log(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }

intercambiar(){  # mueve el contenido visible de $1 a $2 (renombres: ventana de milisegundos)
  local desde="$1" hacia="$2" e
  shopt -s nullglob
  for e in "$desde"/*; do mv "$e" "$hacia"/; done
  shopt -u nullglob
}

case "${SSH_ORIGINAL_COMMAND:-desplegar}" in
  desplegar) ;;
  revertir)
    [ -d "$ANTERIOR" ] && [ -n "$(ls -A "$ANTERIOR")" ] || { log "no hay versión anterior"; exit 1; }
    rm -rf "$NUEVO"; mkdir "$NUEVO"
    intercambiar "$RAIZ" "$NUEVO"
    intercambiar "$ANTERIOR" "$RAIZ"
    rm -rf "$ANTERIOR"; mv "$NUEVO" "$ANTERIOR"
    log "revertido a la versión anterior"; exit 0 ;;
  *) log "comando no permitido"; exit 2 ;;
esac

# 1) recibir en zona de preparación (mismo sistema de archivos que RAIZ)
rm -rf "$NUEVO"; mkdir "$NUEVO"
head -c "$MAX_BYTES" | tar xzf - -C "$NUEVO" --no-same-owner --no-same-permissions

# 2) comprobaciones: nada de enlaces simbólicos, estructura mínima presente
if [ -n "$(find "$NUEVO" -type l -print -quit)" ]; then rm -rf "$NUEVO"; log "rechazado: contiene enlaces simbólicos"; exit 3; fi
for f in index.html 404.html base.css app.js playground/index.html docs/index.html; do
  [ -f "$NUEVO/$f" ] || { rm -rf "$NUEVO"; log "rechazado: falta $f"; exit 3; }
done
find "$NUEVO" -type d -exec chmod 755 {} + ; find "$NUEVO" -type f -exec chmod 644 {} +

# 3) respaldo comprimido de lo que está publicado (se guardan los 10 últimos)
mkdir -p "$RESPALDOS"
tar czf "$RESPALDOS/mini-format-$(date +%Y%m%d-%H%M%S).tgz" -C "$RAIZ" --exclude='./.nuevo' --exclude='./.anterior' .
ls -1t "$RESPALDOS"/mini-format-*.tgz 2>/dev/null | tail -n +11 | xargs -r rm -f

# 4) intercambio: lo publicado pasa a .anterior, lo nuevo pasa a la raíz
rm -rf "$ANTERIOR"; mkdir "$ANTERIOR"
intercambiar "$RAIZ" "$ANTERIOR"
intercambiar "$NUEVO" "$RAIZ"
rmdir "$NUEVO"
log "publicado: $(find "$RAIZ" -path "$RAIZ/.anterior" -prune -o -type f -print | wc -l) archivos"
