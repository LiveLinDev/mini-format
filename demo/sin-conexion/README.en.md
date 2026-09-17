# Offline demonstration

Replays the mini-format integration flow without network access: contract, instruction generated from the
contract, streaming read of a real archived answer (`generative/raw/e1/haiku/mini/1.txt`, model
`claude-haiku-4-5-20251001`), validation with code and line, selective repair and typed objects.

```bash
python demo/sin-conexion/demo.py            # short pauses to show streaming
python demo/sin-conexion/demo.py --rapido   # no pauses
```

Network access is blocked while it runs. To show repair, the demo deliberately alters two lines of the recorded
answer and replays the repair answer with the original lines; no model is called.
`tests/test_demo_sin_conexion.py` checks the whole flow and the 3-minute limit.
