#!/usr/bin/env bash
# Publica sitio/ en mini-format.pmoluna.com reemplazando el playground actual.
#
#   bash sitio/desplegar.sh ~/.ssh/LLAVE            # despliega
#   bash sitio/desplegar.sh ~/.ssh/LLAVE --revertir # restaura el último respaldo
#
# Qué hace: (1) respalda /var/www/mini-format en ~/respaldos/ del servidor,
# (2) sube sitio/ (sin los archivos de construcción) con tar por SSH (no hace falta rsync ni sudo:
# /var/www/mini-format ya es escribible por el usuario), (3) verifica por HTTPS.
# Nginx sirve `root /var/www/mini-format` con `try_files $uri $uri/ /index.html` (soft-404: cualquier
# ruta inexistente devuelve la portada con 200). El arreglo vive en el servidor, no aquí: ver
# sitio/servidor/NGINX_404.md. Comprueba después con tools/verificar_publicacion.py.
set -euo pipefail

LLAVE="${1:?Indica la llave SSH, por ejemplo: bash $0 ~/.ssh/lunita}"
MODO="${2:-}"
HOST="erick@162.243.33.172"; PUERTO=2222
REMOTO="/var/www/mini-format"
DOMINIO="https://mini-format.pmoluna.com"
AQUI="$(cd "$(dirname "$0")" && pwd)"
SSH="ssh -i $LLAVE -p $PUERTO -o IdentitiesOnly=yes $HOST"

if [ "$MODO" = "--revertir" ]; then
  echo "== Restaurando el último respaldo"
  $SSH 'set -e; U=$(ls -t ~/respaldos/mini-format-*.tgz | head -1); echo "  $U";
        find '"$REMOTO"' -mindepth 1 -delete; tar xzf "$U" -C '"$REMOTO"''
  echo "== Verificación"; curl -s -o /dev/null -w "  $DOMINIO -> %{http_code}\n" "$DOMINIO/"
  exit 0
fi

[ -f "$AQUI/index.html" ] && [ -f "$AQUI/playground/index.html" ] && [ -d "$AQUI/docs" ] \
  || { echo "Falta contenido en sitio/. Ejecuta antes: python sitio/construir.py"; exit 1; }

echo "== 1/3 Respaldo del sitio actual en el servidor"
$SSH 'set -e; mkdir -p ~/respaldos; F=~/respaldos/mini-format-$(date +%Y%m%d-%H%M%S).tgz;
      tar czf "$F" -C /var/www mini-format; ls -la "$F"'

echo "== 2/3 Subida de sitio/ (sin los archivos de construcción: ver servidor/empaquetar.py)"
python3 "$AQUI/servidor/empaquetar.py" \
  | $SSH 'set -e; find '"$REMOTO"' -mindepth 1 -delete; tar xzf - -C '"$REMOTO"'; du -sh '"$REMOTO"'; ls '"$REMOTO"''

echo "== 3/3 Verificación"
for ruta in "/" "/playground/" "/docs/" "/docs/spec/" "/docs/errors/E06/" "/validacion/" "/economia/" "/base.css" "/app.js"; do
  printf "  %-22s -> " "$ruta"; curl -s -o /dev/null -w "%{http_code}\n" "$DOMINIO$ruta"
done
curl -s "$DOMINIO/" | grep -o "<title>[^<]*</title>" | head -1
curl -s "$DOMINIO/playground/" | grep -o "<title>[^<]*</title>" | head -1
# Informe honesto de lo publicado: commit de version.json y 404 real (advierte del soft-404 de nginx).
python3 "$AQUI/../tools/verificar_publicacion.py" --base "$DOMINIO" || echo "  (revisa el informe de arriba)"
echo "Listo. Para volver atrás: bash $0 $LLAVE --revertir"
