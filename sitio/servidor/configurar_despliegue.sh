#!/usr/bin/env bash
# Configuración ÚNICA del despliegue automático. La ejecuta Erick en su PC (Git Bash):
#
#   & "C:\Program Files\Git\bin\bash.exe" D:/Tesis/mini-format/sitio/servidor/configurar_despliegue.sh
#
# 1) Crea una llave nueva SOLO para desplegar (~/.ssh/mini_deploy_ed25519), sin frase.
# 2) Con tu llave personal instala en el servidor el receptor y autoriza la llave nueva
#    con `restrict,command=`: esa llave no abre shell, solo puede publicar o revertir el sitio.
# 3) Imprime los dos valores que hay que pegar como secretos en GitHub.
# No toca nada de SIMA ni de Luna. No requiere sudo.
set -euo pipefail

HOST="erick@162.243.33.172"; PUERTO=2222
PERSONAL="${1:-$HOME/.ssh/id_ed25519}"
DEPLOY="$HOME/.ssh/mini_deploy_ed25519"
AQUI="$(cd "$(dirname "$0")" && pwd)"
SSH=(ssh -i "$PERSONAL" -p "$PUERTO" -o IdentitiesOnly=yes "$HOST")

echo "== 1/4 Llave de despliegue"
if [ -f "$DEPLOY" ]; then echo "  ya existe $DEPLOY, se reutiliza"
else ssh-keygen -t ed25519 -N "" -C "despliegue mini-format (GitHub Actions)" -f "$DEPLOY" >/dev/null; echo "  creada $DEPLOY"; fi
PUB="$(cat "$DEPLOY.pub")"

echo "== 2/4 Receptor en el servidor (~/bin/recibir-sitio-mini)"
"${SSH[@]}" 'mkdir -p ~/bin && cat > ~/bin/recibir-sitio-mini && chmod 755 ~/bin/recibir-sitio-mini && echo "  instalado"' < "$AQUI/recibir-sitio.sh"

echo "== 3/4 Autorización restringida de la llave"
HOME_REMOTO="$("${SSH[@]}" 'printf %s "$HOME"')"
# la línea viaja por stdin: sin comillas anidadas ni expansiones remotas
printf 'restrict,command="%s/bin/recibir-sitio-mini" %s\n' "$HOME_REMOTO" "$PUB" | "${SSH[@]}" '
  set -e; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys
  IFS= read -r L
  K=$(printf "%s" "$L" | awk "{print \$3}")
  if grep -qF "$K" ~/.ssh/authorized_keys; then echo "  ya estaba autorizada"
  else printf "%s\n" "$L" >> ~/.ssh/authorized_keys; echo "  autorizada"; fi'

echo "== 4/4 Prueba: la llave nueva NO debe abrir shell"
RESP="$(ssh -i "$DEPLOY" -p "$PUERTO" -o IdentitiesOnly=yes -o BatchMode=yes "$HOST" "id" 2>&1 || true)"
if printf '%s' "$RESP" | grep -q "comando no permitido"; then
  echo "  correcto: la llave solo admite desplegar/revertir"
else
  echo "  ATENCIÓN: respuesta inesperada del servidor:"; printf '%s\n' "$RESP" | sed 's/^/    | /'
  echo "  Ejecuta sitio/servidor/diagnosticar_despliegue.sh y comparte la salida."; exit 1
fi

cat <<FIN

================================================================================
Ahora en GitHub: LiveLinDev/mini-format → Settings → Environments → New environment
  nombre: produccion      (opcional: "Deployment branches" = solo main)
y dentro, "Add environment secret" dos veces:

  SITIO_SSH_KEY      = todo el contenido de  $DEPLOY
                       (incluidas las líneas BEGIN/END; se copia con:  clip < "$DEPLOY")

  SITIO_KNOWN_HOSTS  = la línea siguiente:
$(ssh-keyscan -p "$PUERTO" -t ed25519 162.243.33.172 2>/dev/null)

Luego: Actions → sitio → Run workflow, o cualquier push a main que toque sitio/.
================================================================================
FIN
