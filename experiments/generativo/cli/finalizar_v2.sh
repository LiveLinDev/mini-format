#!/usr/bin/env bash
# Cierra la corrida V2 con las CLI: reparaciones, importación conjunta, análisis del arnés y resumen.
# Uso (desde la raíz del repositorio): MINI_CLAUDE_CONFIG_DIR=... bash experiments/generativo/cli/finalizar_v2.sh
set -u
R=experiments/generativo/resultados/cli_2026-11
PY=${PY:-../mini-format-wt/venv-int/Scripts/python.exe}
export PYTHONIOENCODING=utf-8
for m in claude-opus-5-5 claude-haiku-5-5; do
  $PY experiments/generativo/run.py preparar-reparacion $R/respuestas_$m.jsonl --salida $R/prompts_rep_$m.jsonl | tail -1
  $PY experiments/generativo/cli/generar_cli.py $R/prompts_rep_$m.jsonl $R/respuestas_rep_$m.jsonl \
      --herramienta claude --modelo $m --paralelo 4 | tail -1
done
# reparaciones de Kimi que quedaron pendientes por el límite de uso de la suscripción
$PY experiments/generativo/cli/generar_cli.py $R/prompts_rep_kimi-k3.1-pro.jsonl $R/respuestas_rep_kimi-k3.1-pro.jsonl \
    --herramienta kimi --modelo kimi-code/k3.1-pro --declarado kimi-k3.1-pro --paralelo 2 --reintentos 0 | tail -1
rm -rf $R/entrada_todos $R/import_todos
mkdir -p $R/entrada_todos
cp $R/respuestas_*.jsonl $R/entrada_todos/
$PY experiments/generativo/run.py importar $R/entrada_todos --salida $R/import_todos | tail -1
$PY experiments/generativo/analyze.py --resultados $R/import_todos --sin-figuras --bootstrap 300 | tail -3
$PY experiments/generativo/cli/resumir_cli.py $R
