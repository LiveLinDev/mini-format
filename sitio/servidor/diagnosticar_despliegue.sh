#!/usr/bin/env bash
# Diagnóstico del despliegue restringido. Solo lectura: no publica ni modifica nada.
#
#   & "C:\Program Files\Git\bin\bash.exe" D:/Tesis/mini-format/sitio/servidor/diagnosticar_despliegue.sh
#
# No imprime llaves privadas. De la llave pública muestra solo el tipo y 12 caracteres.
HOST="erick@162.243.33.172"; PUERTO=2222
PERSONAL="$HOME/.ssh/id_ed25519"; DEPLOY="$HOME/.ssh/mini_deploy_ed25519"

echo "== A. Local"
ls -la "$DEPLOY" "$DEPLOY.pub" 2>&1 | sed 's/^/  /'
echo "  huella: $(ssh-keygen -lf "$DEPLOY.pub" 2>&1)"
ssh -V 2>&1 | sed 's/^/  ssh: /'

echo; echo "== B. Conexión con la llave de despliegue (comando 'id', debe responder 'comando no permitido')"
ssh -v -i "$DEPLOY" -p "$PUERTO" -o IdentitiesOnly=yes -o BatchMode=yes "$HOST" id 2>&1 \
  | grep -E "Offering public key|Server accepts key|Authenticated|Permission denied|publickey|Exit status|comando|No such file|bad interpreter|env:|restrict|Remote:|^[0-9]{4}-" \
  | grep -v "^debug1: Will attempt" | sed 's/^/  /'
echo "  código de salida: ${PIPESTATUS[0]}"

echo; echo "== C. Estado en el servidor (con la llave personal, solo lectura)"
ssh -i "$PERSONAL" -p "$PUERTO" -o IdentitiesOnly=yes "$HOST" 'bash -s' <<'REMOTO' 2>&1 | sed 's/^/  /'
echo "HOME=$HOME  SHELL=$SHELL"
echo "--- ~/bin/recibir-sitio-mini"
ls -la ~/bin/recibir-sitio-mini 2>&1
head -1 ~/bin/recibir-sitio-mini 2>&1 | od -c | head -2
echo "--- líneas de authorized_keys con 'recibir-sitio' (llave recortada)"
grep -n "recibir-sitio" ~/.ssh/authorized_keys | sed -E 's/(ssh-ed25519 [A-Za-z0-9+\/]{12})[A-Za-z0-9+\/=]*/\1…/'
echo "--- permisos"
ls -ld ~ ~/.ssh ~/.ssh/authorized_keys ~/bin 2>&1
echo "--- ejecución directa del receptor con un comando ajeno"
SSH_ORIGINAL_COMMAND=id ~/bin/recibir-sitio-mini; echo "salida=$?"
echo "--- ¿algo en el arranque del shell imprime texto?"
out=$(bash -c 'true' 2>&1); [ -z "$out" ] && echo "(nada)" || echo "$out" | head -5
echo "--- sshd (lo legible sin sudo)"
grep -hiE "^\s*(AuthorizedKeysFile|ForceCommand|AllowUsers|PubkeyAuthentication|AuthenticationMethods|Match)" /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null || echo "(no legible o sin directivas relevantes)"
REMOTO
