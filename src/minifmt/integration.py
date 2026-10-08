"""Locate structured-output code and prepare an integration for its toolkit.

Automatic edits are limited to a provable synchronous Python chat/JSON pair.
Other languages/providers receive a concrete prompt for the user's coding AI.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import re

SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".mini"}


def locate(project):
    root = Path(project).resolve()
    if not root.exists():
        raise ValueError("project path does not exist")

    def source_files():
        if root.is_file():
            yield root
            return
        for directory, folders, files in os.walk(root):
            folders[:] = sorted(f for f in folders if f not in SKIP and not f.startswith("."))
            for file in sorted(files):
                yield Path(directory) / file

    hits = []
    for path in source_files():
        if not path.is_file() or path.suffix not in (".py", ".js", ".ts", ".mjs", ".tsx"):
            continue
        if any(part in SKIP or part.startswith(".") for part in path.relative_to(root.parent if root.is_file() else root).parts):
            continue
        if path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeError, OSError):
            continue
        lines = [i for i, line in enumerate(text.splitlines(), 1)
                 if re.search(r"json\.loads|JSON\.parse|response_format|chat\.completions|responses\.create|generateContent", line)]
        if lines:
            hits.append({"file": str(path), "lines": lines})
        if len(hits) >= 30:
            break
    return hits


def _python_patch(source, bridge_name):
    tree = ast.parse(source)
    # One narrowly supported pattern. No async, streaming, tools or extra uses
    # of the response object; those need an application-specific adapter.
    pairs = []
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.Module, ast.FunctionDef)):
            continue
        for request, decode in zip(scope.body, scope.body[1:]):
            if not (isinstance(request, ast.Assign) and len(request.targets) == 1 and isinstance(request.targets[0], ast.Name)
                    and isinstance(request.value, ast.Call) and isinstance(decode, ast.Assign) and len(decode.targets) == 1):
                continue
            call, name = request.value, request.targets[0].id
            if not ast.unparse(call.func).endswith(".chat.completions.create") or call.args:
                continue
            options = {keyword.arg: keyword.value for keyword in call.keywords}
            if None in options or "messages" not in options or "model" not in options:
                continue
            if any(key in options for key in ("stream", "tools", "functions", "n")):
                continue
            value = decode.value
            if not (isinstance(value, ast.Call) and ast.unparse(value.func) == "json.loads" and len(value.args) == 1 and not value.keywords
                    and ast.unparse(value.args[0]) == f"{name}.choices[0].message.content"):
                continue
            uses = [node for node in ast.walk(scope) if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load)]
            if len(uses) != 1:
                continue
            pairs.append((request, decode))
    if len(pairs) != 1:
        return None
    request, decode = pairs[0]
    lines = source.splitlines(keepends=True)
    if request.lineno == decode.lineno:
        return None
    for statement in (request, decode):
        first = lines[statement.lineno - 1].encode("utf-8")[:statement.col_offset]
        suffix = lines[statement.end_lineno - 1].encode("utf-8")[statement.end_col_offset:].strip()
        if first.strip() or (suffix and not suffix.startswith(b"#")):
            return None
    # AST columns are UTF-8 byte offsets, so never slice Python characters by them.
    call = request.value
    keywords = [f"{kw.arg}={ast.get_source_segment(source, kw.value)}" for kw in call.keywords if kw.arg != "response_format"]
    target = ast.get_source_segment(source, decode.targets[0])
    replacement = f"{target} = {bridge_name}.complete({ast.get_source_segment(source, call.func)}, " + ", ".join(keywords) + ")"
    if any(line.strip() for line in lines[request.end_lineno:decode.lineno - 1]):
        return None
    indent = lines[request.lineno - 1][:len(lines[request.lineno - 1]) - len(lines[request.lineno - 1].lstrip())]
    lines[request.lineno - 1:decode.end_lineno] = [indent + replacement + "\n"]
    result = "".join(lines)
    # Insert after docstring / future imports, preserving Python's import rules.
    top = tree.body
    insertion = 0
    for node in top:
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)) or (
                isinstance(node, ast.ImportFrom) and node.module == "__future__"):
            insertion = node.end_lineno
        else:
            break
    edited = result.splitlines(keepends=True)
    edited.insert(insertion, f"import {bridge_name}\n")
    result = "".join(edited)
    ast.parse(result)
    return result


def _json_mode_chat(node):
    """A dict literal for an OpenAI-compatible chat request that asks for JSON mode."""
    if not isinstance(node, ast.Dict):
        return False
    keys = {key.value for key in node.keys if isinstance(key, ast.Constant)}
    stream = next((value for key, value in zip(node.keys, node.values) if isinstance(key, ast.Constant) and key.value == "stream"), None)
    return {"messages", "response_format"} <= keys and not (isinstance(stream, ast.Constant) and stream.value)


def _python_http_patch(source, bridge_name):
    """Second supported pattern: ``requests.post``/``httpx.post`` to a chat endpoint with a JSON-mode payload.

    Only the call itself changes (``requests.post`` -> ``<bridge>.post``) plus one import, so the application keeps
    its URL, headers, timeout, error handling and the code that reads ``choices[0].message.content``.
    """
    tree = ast.parse(source)
    targets = {}
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        payloads = {node.targets[0].id for node in ast.walk(function)
                    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and _json_mode_chat(node.value)}
        for node in ast.walk(function):
            if not (isinstance(node, ast.Call) and ast.unparse(node.func) in ("requests.post", "httpx.post")):
                continue
            body = {keyword.arg: keyword.value for keyword in node.keywords}.get("json")
            if (isinstance(body, ast.Name) and body.id in payloads) or _json_mode_chat(body):
                targets[(node.lineno, node.col_offset)] = node  # nested functions are walked twice
    if len(targets) != 1:
        return None
    call = next(iter(targets.values()))
    library = ast.unparse(call.func).split(".")[0]
    newline = "\r\n" if "\r\n" in source else "\n"
    lines = source.splitlines(keepends=True)
    if call.func.lineno != call.func.end_lineno:
        return None
    row = lines[call.func.lineno - 1].encode("utf-8")
    start, end = call.func.col_offset, call.func.end_col_offset
    if row[start:end] != f"{library}.post".encode():
        return None
    lines[call.func.lineno - 1] = (row[:start] + f"{bridge_name}.post".encode() + row[end:]).decode("utf-8")
    insertion = 0
    for node in tree.body:
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)) or (
                isinstance(node, ast.ImportFrom) and node.module == "__future__"):
            insertion = node.end_lineno
        else:
            break
    lines.insert(insertion, f"import {bridge_name}{newline}")
    result = "".join(lines)
    ast.parse(result)
    return result, library


def _bridge(kind, relative, lang):
    head = ("from pathlib import Path\nimport importlib.util\n"
            f"BUNDLE = (Path(__file__).resolve().parent / {relative!r}).resolve()\n"
            "spec = importlib.util.spec_from_file_location('_app_mini_workflow', BUNDLE / 'workflow.py')\n"
            "module = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\n")
    if kind == "sdk":
        return head + f"def complete(create, **kwargs):\n    return module.Workflow(BUNDLE, lang={lang!r}).complete(create, **kwargs)\n"
    return ("import sys\nimport " + kind + " as _http\n" + head +
            "\n\ndef post(url, **kwargs):\n"
            "    \"\"\"Same call as " + kind + ".post; JSON-mode chat requests answer in .mini and return validated JSON.\"\"\"\n"
            f"    flow = module.Workflow(BUNDLE, lang={lang!r})\n"
            "    response = flow.post(_http.post, url, **kwargs)\n"
            "    if getattr(response, 'mini_summary', None):\n"
            "        print(response.mini_summary, file=sys.stderr)\n"
            "    return response\n")


def prepare(project, bundle=".mini", *, lang=None, apply=False):
    bundle = Path(bundle).resolve()
    if not (bundle / "workflow.py").is_file():
        raise ValueError("build a toolkit first; workflow.py is missing")
    if lang is None:
        settings = bundle / "setup.json"
        lang = json.loads(settings.read_text(encoding="utf-8"))["language"] if settings.is_file() else "es"
    if lang not in ("es", "en"):
        raise ValueError("lang must be es or en")
    project = Path(project).resolve()
    hits = locate(project)
    out = bundle / "integration"
    out.mkdir(exist_ok=True)
    title = "Integra .mini en este proyecto" if lang == "es" else "Integrate .mini into this project"
    instruction = ("Localiza la llamada que pide JSON a la IA. Conserva proveedor, modelo, credenciales y lógica de negocio. "
                   "Sustituye la instrucción JSON por el contenido del prompt indicado y desactiva el modo JSON de la API. "
                   "Conecta el resultado a Workflow.run: generar → validar → reparar → volver a validar → JSON. "
                   "Pasa la misma llamada como callback para corregir líneas; máximo un reintento. No inventes valores ni aceptes lotes incompletos. "
                   "Adapta el código al SDK, al lenguaje y al esquema reales; prueba el flujo antes de usarlo."
                   if lang == "es" else
                   "Locate the AI call that requests JSON. Keep the provider, model, credentials and business logic. "
                   "Replace JSON instructions with the indicated prompt and disable API JSON mode. "
                   "Connect Workflow.run: generate → validate → repair → revalidate → JSON. "
                   "Pass the same model callback for selective repair; at most one retry. Never invent values or accept incomplete batches. "
                   "Adapt to the actual SDK, language and schema; test the entire workflow.")
    candidates = "\n".join(f"- `{hit['file']}`: {', '.join(map(str, hit['lines']))}" for hit in hits) or "No candidates found / No se encontraron candidatos."
    plan = f"# {title}\n\n{instruction}\n\nPrompt: `{bundle / f'prompt.{lang}.md'}`\nRuntime: `{bundle / 'workflow.py'}`\n\n## Candidates / Candidatos\n\n{candidates}\n\n"
    plan += ("Python: importa Workflow desde workflow.py y usa `Workflow(bundle).run(tu_llamada, tarea)` "
             "o `await Workflow(bundle).run_async(tu_llamada, tarea)`. "
             "Node: importa Workflow desde workflow.mjs y usa `await flow.run(tu_llamada, tarea)` (requiere Python). "
             "Otros lenguajes: ejecuta `python workflow.py -` con la respuesta por stdin y lee JSON por stdout; "
             "si falla, lee los diagnósticos de stderr y conecta el reintento a tu proveedor. "
             "No entregues datos a la aplicación si el proceso devuelve un código distinto de 0.\n" if lang == "es" else
             "Python: import Workflow from workflow.py and use `Workflow(bundle).run(your_call, task)` "
             "or `await Workflow(bundle).run_async(your_call, task)`. "
             "Node: import Workflow from workflow.mjs and use `await flow.run(your_call, task)` (requires Python). "
             "Other languages: pipe the response to `python workflow.py -` and read JSON from stdout; "
             "on failure, read diagnostics from stderr and connect the retry to your provider. "
             "Never deliver data to your application when the process exits with a nonzero code.\n")
    (out / "INTEGRATE.md").write_bytes(plan.encode("utf-8"))
    report = {"candidates": hits, "plan": str(out / "INTEGRATE.md"), "applied": False, "supported": False}
    target = project if project.is_file() else Path(hits[0]["file"]) if len(hits) == 1 else None
    if target and target.suffix == ".py":
        original_bytes = target.read_bytes()
        source = original_bytes.decode("utf-8-sig")
        bridge_name = "mini_bridge_" + hashlib.sha256(str(bundle).encode()).hexdigest()[:8]
        try:
            patched, kind = _python_patch(source, bridge_name), "sdk"
            if not patched:
                patched, kind = _python_http_patch(source, bridge_name) or (None, None)
        except SyntaxError:
            patched = None
        if patched:
            try:
                relative = Path(os.path.relpath(bundle, target.parent)).as_posix()
            except ValueError:  # Windows projects and toolkits may live on different drives.
                relative = bundle.as_posix()
            bridge = _bridge(kind, relative, lang)
            bridge_path = target.with_name(bridge_name + ".py")
            patch = "".join(difflib.unified_diff(source.splitlines(True), patched.splitlines(True), fromfile=str(target), tofile=str(target)))
            (out / "change.diff").write_bytes(patch.encode("utf-8"))
            report.update(supported=True, pattern="openai-sdk" if kind == "sdk" else f"{kind}-chat-json", diff=str(out / "change.diff"), file=str(target))
            if apply:
                backup = out / (target.name + ".before")
                if backup.exists() or bridge_path.exists():
                    raise ValueError("an integration backup or bridge already exists; review it before applying again")
                if target.read_bytes() != original_bytes:
                    raise ValueError("source changed during preparation; run integration again")
                backup.write_bytes(original_bytes)
                bridge_path.write_bytes(bridge.encode("utf-8"))
                target.write_bytes(patched.encode("utf-8"))
                report.update(applied=True, backup=str(backup), bridge=str(bridge_path))
    (out / "report.json").write_bytes((json.dumps(report, indent=2) + "\n").encode("utf-8"))
    if apply and not report["supported"]:
        raise ValueError(f"automatic patch unavailable for this code; use the prepared coding-AI instructions: {out / 'INTEGRATE.md'}")
    return report
