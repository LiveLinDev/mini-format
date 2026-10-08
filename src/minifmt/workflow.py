"""Provider-independent generate -> validate -> repair -> JSON workflow.

Copied into generated toolkits; Python standard library only. A caller supplies
its own model callback. Credentials and SDK clients never enter the history.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import re
import sys


def _runtime(bundle):
    spec = importlib.util.spec_from_file_location("_mini_workflow_parser", bundle / "parser.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkflowError(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__(".mini response could not be validated; no JSON was delivered")


class Workflow:
    """Wrap any synchronous callable ``generate(prompt: str) -> str``.

    Repair is bounded and does not change the declared count. Bad lines may be
    corrected by the same model, but good lines are preserved and checked again.
    ``last_run`` contains an inspectable history, including unsuccessful runs.
    """

    def __init__(self, bundle=None, lang=None):
        self.bundle = Path(bundle or Path(__file__).resolve().parent).resolve()
        if lang is None:
            settings = self.bundle / "setup.json"
            lang = json.loads(settings.read_text(encoding="utf-8"))["language"] if settings.is_file() else "es"
        if lang not in ("es", "en"):
            raise ValueError("lang must be es or en")
        self.lang = lang
        self.runtime = _runtime(self.bundle)
        self.contract = self.runtime.load_contract(self.bundle / "contract.json")
        self.format_prompt = (self.bundle / f"prompt.{lang}.md").read_text(encoding="utf-8")
        self.last_run = None

    def prompt(self, task, expected_records=None):
        count = "" if expected_records is None else f"\nRequired record count: {expected_records}."
        return f"Task / Tarea:\n{task}{count}\n\nOutput format (replaces JSON instructions):\n{self.format_prompt}"

    def process(self, text, *, generate=None, task="", expected_records=None, max_repairs=1, truncated=None, _round=0):
        """Validate, repair and decode one response.

        ``truncated`` tells whether the provider stopped at its output limit (``finish_reason == "length"``);
        ``None`` infers it from the text. A cut response keeps its complete records, and only the missing
        ones are requested again, at most twice. Without ``generate`` nothing is requested.
        """
        if not isinstance(text, str):
            raise ValueError("the model callback must return text")
        if max_repairs not in (0, 1, 2, 3):
            raise ValueError("max_repairs must be between 0 and 3")
        if expected_records is not None and (type(expected_records) is not int or expected_records < 0):
            raise ValueError("expected_records must be a nonnegative integer")
        trace = [{"stage": "generate", "text": text},
                 {"stage": "validate", **self.runtime.diagnose(text, self.contract)}]
        self.last_run = {"ok": False, "trace": trace}
        at_line_end = text.rstrip(" \t").endswith("\n")
        repaired = self.runtime.repair(text, self.contract)
        trace.append({"stage": "repair", "ok": repaired["ok"], "changes": repaired["changes"],
                      "errors": repaired["diagnostics"]["errors"]})
        text = repaired["text"]
        cut = self._cut(text, truncated, at_line_end) if generate is not None and _round < 2 else None
        target = expected_records
        if cut is not None:
            text, declared, kept = cut
            target = expected_records if expected_records is not None else declared
            expected_records = None  # the complete part is validated on its own; the rest is requested below
            trace.append({"stage": "truncation", "declared": declared, "complete_records": kept})
        for attempt in range(max_repairs + 1):
            report = self.runtime.diagnose(text, self.contract)
            if report["ok"] and expected_records is not None and report["records"] != expected_records:
                report = {"ok": False, "invalid_lines": [], "errors": [
                    {"code": "D_EXPECTED_COUNT", "message": f"expected {expected_records} records, received {report['records']}"}],
                    "repair_prompt": "Regenerate the complete document with the required record count. Never invent unavailable facts."}
            if report["ok"]:
                data = self.runtime.decode(text, self.contract)
                trace.append({"stage": "parse", "ok": True, "records": report["records"]})
                if cut is not None:
                    data = self._continue(data, target, generate, task, max_repairs, trace, _round)
                    text = self.runtime.encode(data, self.contract, shared=False, dictionaries=False)
                self.last_run.update(ok=True, mini=text, data=data)
                return data
            if generate is None or attempt == max_repairs:
                self.last_run.update(diagnostics=report, mini=text)
                raise WorkflowError(self.last_run)
            selective = bool(report.get("invalid_lines"))
            correction_prompt = self.prompt(task, expected_records) + "\n\nOriginal response:\n" + text
            correction_prompt += "\n\nCORRECTION REQUEST (overrides output format for this call):\n" + report["repair_prompt"]
            correction = generate(correction_prompt)
            trace.append({"stage": "model_repair", "attempt": attempt + 1, "selective": selective, "text": correction})
            try:
                if selective:
                    text = self.runtime.apply_replacements(text, self.runtime._strict_json(correction), self.contract)
                else:
                    result = self.runtime.repair(correction, self.contract)
                    text = result["text"]
            except (ValueError, TypeError) as exc:
                self.last_run.update(diagnostics={"ok": False, "errors": [{"code": "D_REPAIR", "message": str(exc)}]}, mini=text)
                raise WorkflowError(self.last_run) from exc
            trace.append({"stage": "revalidate", **self.runtime.diagnose(text, self.contract)})
        raise AssertionError("unreachable")

    def _cut(self, text, truncated, at_line_end=False):
        """Return (complete part, declared n, complete records) when the response was cut, else None.

        With ``truncated`` (the provider reported its output limit) the last line is always dropped unless
        the response stopped right after a line break: a cut field can still look valid. Without that signal
        a cut is inferred only from fewer lines than the header declares, or from a last line with fewer cells.
        """
        lines = text.rstrip("\n").split("\n")
        match = re.search(r"\|n=(\d+)(?=\||$)", lines[0])
        if not match or len(lines) < 1:
            return None
        declared = int(match.group(1))
        if truncated:
            keep = lines[1:] if at_line_end else lines[1:-1]
        else:
            report = self.runtime.diagnose(text, self.contract)
            if report["ok"]:
                return None
            errors, last = report.get("errors") or [], len(lines)

            def fewer_cells(error):
                found = re.search(r"expected (\d+) cells, received (\d+)", error.get("message", ""))
                return error.get("code") == "D_ARITY" and bool(found) and int(found.group(2)) < int(found.group(1))

            if [e.get("code") for e in errors] == ["D_COUNT"] and not report.get("invalid_lines"):
                keep = lines[1:]
            elif last >= 2 and report.get("invalid_lines") == [last] and all(
                    e.get("line") == last and fewer_cells(e) for e in errors):
                keep = lines[1:-1]
            else:
                return None
        if len(keep) >= declared:
            return None
        complete = "\n".join([lines[0][:match.start()] + f"|n={len(keep)}" + lines[0][match.end():]] + keep)
        return complete, declared, len(keep)

    def _records(self, data):
        path = self.contract.get("record_path")
        if path is None:
            return None
        for key in path:
            data = data[key]
        return data

    def _continue(self, data, target, generate, task, max_repairs, trace, _round):
        """Request only the records missing after a cut and append them to the complete part."""
        records = self._records(data)
        if records is None:
            return data
        for _ in range(2):
            missing = target - len(records)
            if missing <= 0:
                break
            received = [str(next(iter(r.values()), "") if isinstance(r, dict) else r)[:80] for r in records]
            prompt = (self.prompt(task, missing) +
                      "\n\nCONTINUATION REQUEST (the previous response was cut by the output limit):\n"
                      f"{len(records)} of {target} records were received and kept. Do not repeat them: "
                      f"{json.dumps(received, ensure_ascii=False)}\n"
                      f"Return ONLY the {missing} missing records as a complete .mini document whose header declares n={missing}.")
            continuation = generate(prompt)
            trace.append({"stage": "continuation", "requested": missing, "text": continuation})
            outer = self.last_run
            try:
                more = self.process(continuation, generate=generate, task=task, max_repairs=max_repairs, _round=_round + 1)
            except WorkflowError as exc:
                trace.append({"stage": "continuation_failed", "diagnostics": exc.report.get("diagnostics")})
                break
            finally:
                self.last_run = outer
            new = (self._records(more) or [])[:missing]
            trace.append({"stage": "continuation_parse", "ok": True, "records": len(new)})
            records.extend(new)
        if len(records) != target:
            self.last_run.update(diagnostics={"ok": False, "invalid_lines": [], "errors": [
                {"code": "D_EXPECTED_COUNT", "message": f"expected {target} records, received {len(records)}"}]})
            raise WorkflowError(self.last_run)
        return data

    def save_run(self, folder):
        """Write the last run so it can be inspected with ``mini validate``, ``mini diagnose`` or ``mini to-json``.

        Each model answer is saved exactly as received (``respuesta_N.mini``; a selective correction, which is a
        JSON object of lines, as ``.json``), plus the validated document (``resultado.mini``) and the trace
        (``ejecucion.json``). Earlier files in the folder are replaced. The files contain application data.
        """
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        for old in list(folder.glob("*.mini")) + list(folder.glob("*.json")):
            old.unlink()
        run = self.last_run or {}
        es = self.lang == "es"
        answers = [(step["text"], ".json" if step.get("stage") == "model_repair" and step.get("selective") else ".mini")
                   for step in run.get("trace") or []
                   if step.get("stage") in ("generate", "model_repair", "continuation") and isinstance(step.get("text"), str)]
        for number, (text, suffix) in enumerate(answers, 1):
            (folder / f"{'respuesta' if es else 'response'}_{number}{suffix}").write_bytes(text.encode("utf-8"))
        if run.get("ok") and run.get("mini"):
            (folder / ("resultado.mini" if es else "result.mini")).write_bytes((run["mini"].rstrip("\n") + "\n").encode("utf-8"))
        trace = {key: value for key, value in run.items() if key != "data"}
        (folder / ("ejecucion.json" if es else "run.json")).write_bytes(
            (json.dumps(trace, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return folder

    def summary(self):
        """One line describing the last run, in the toolkit language."""
        run = self.last_run or {}
        trace = run.get("trace") or []
        es = self.lang == "es"
        if not run.get("ok"):
            return ("mini-format: la respuesta no se pudo validar; no se entregó JSON" if es
                    else "mini-format: the response could not be validated; no JSON was delivered")
        records = self._records(run["data"])
        count = len(records) if isinstance(records, list) else 1
        parts = [f"mini-format: {count} registro(s) válidos" if es else f"mini-format: {count} valid record(s)"]
        repaired = sum(1 for step in trace if step.get("stage") == "model_repair")
        cut = next((step for step in trace if step.get("stage") == "truncation"), None)
        local = [c for step in trace if step.get("stage") == "repair" for c in step.get("changes") or []]
        if cut:
            asked = sum(step["requested"] for step in trace if step.get("stage") == "continuation")
            parts.append(f"respuesta cortada: {cut['complete_records']} conservados y {asked} pedidos de nuevo" if es
                         else f"cut response: {cut['complete_records']} kept and {asked} requested again")
        if repaired:
            parts.append(f"{repaired} corrección(es) selectiva(s) del modelo" if es else f"{repaired} selective model correction(s)")
        if local:
            nombres = {"removed UTF-8 BOM": "BOM eliminado", "normalized CRLF to LF": "saltos de línea normalizados",
                       "removed complete Markdown code fence": "bloque Markdown eliminado",
                       "removed unclosed Markdown code fence": "bloque Markdown sin cerrar eliminado"}
            parts.append(("ajustes locales: " if es else "local fixes: ") + ", ".join(nombres.get(c, c) if es else c for c in local))
        return " · ".join(parts)

    def run(self, generate, task, *, expected_records=None, max_repairs=1):
        return self.process(generate(self.prompt(task, expected_records)), generate=generate, task=task,
                            expected_records=expected_records, max_repairs=max_repairs)

    async def run_async(self, generate, task, *, expected_records=None, max_repairs=1):
        """Use the same validated pipeline with an asynchronous model callback."""
        loop = asyncio.get_running_loop()
        text = await generate(self.prompt(task, expected_records))

        def correction(prompt):
            return asyncio.run_coroutine_threadsafe(generate(prompt), loop).result()

        return await asyncio.to_thread(self.process, text, generate=correction, task=task,
                                       expected_records=expected_records, max_repairs=max_repairs)

    def complete(self, create, *, messages, expected_records=None, max_repairs=1, **kwargs):
        """Bridge an existing OpenAI-compatible chat completion SDK call.

        Keep model, client, business messages and other generation parameters.
        JSON response_format is removed because the model now returns .mini.
        """
        kwargs.pop("response_format", None)
        if kwargs.get("stream") or kwargs.get("tools") or kwargs.get("functions") or kwargs.get("n", 1) != 1:
            raise ValueError("use Workflow.run with a text callback for streaming, tools or multiple choices")
        original = [dict(message) for message in messages]

        def generate(prompt):
            response = create(messages=original + [{"role": "system", "content": prompt}], **kwargs)
            if isinstance(response, dict):
                return response["choices"][0]["message"]["content"]
            return response.choices[0].message.content

        return self.run(generate, "Follow the original application messages.", expected_records=expected_records,
                        max_repairs=max_repairs)

    def post(self, send, url, *, json=None, expected_records=None, max_repairs=1, **kwargs):
        """Bridge an HTTP call to an OpenAI-compatible chat/completions endpoint (``requests.post``, ``httpx.post``).

        Only JSON-mode chat requests change: ``response_format`` is removed, the format prompt is added as a last
        system message and the .mini answer is validated, repaired and decoded. The application receives a response
        with the same shape whose ``message.content`` is the validated JSON document, and ``usage`` adds up every
        call. Any other request, and any HTTP error, is returned unchanged.
        """
        payload = json
        if (not isinstance(payload, dict) or "messages" not in payload or "response_format" not in payload
                or payload.get("stream") or payload.get("tools") or payload.get("functions") or payload.get("n", 1) != 1):
            return send(url, json=payload, **kwargs)
        base = {key: value for key, value in payload.items() if key != "response_format"}
        original = [dict(message) for message in base["messages"]]
        calls = []

        class _Failed(Exception):
            def __init__(self, response):
                super().__init__("HTTP error")
                self.response = response

        def generate(prompt):
            response = send(url, json=dict(base, messages=original + [{"role": "system", "content": prompt}]), **kwargs)
            if getattr(response, "status_code", 200) >= 400:
                raise _Failed(response)
            body = response.json()
            calls.append(body)
            choice = (body.get("choices") or [{}])[0]
            return (choice.get("message") or {}).get("content") or ""

        task = "Follow the original application messages."
        try:
            text = generate(self.prompt(task, expected_records))
            truncated = ((calls[-1].get("choices") or [{}])[0].get("finish_reason") == "length")
            data = self.process(text, generate=generate, task=task, expected_records=expected_records,
                                max_repairs=max_repairs, truncated=truncated)
            content = _json.dumps(data, ensure_ascii=False)
        except _Failed as failure:
            return failure.response
        except WorkflowError:
            content = (self.last_run or {}).get("mini") or text  # not JSON: the application keeps its own fallback
        body = copy.deepcopy(calls[-1])
        choice = body["choices"][0]
        choice.setdefault("message", {})["content"] = content
        choice["finish_reason"] = "stop" if self.last_run and self.last_run.get("ok") else choice.get("finish_reason")
        usage = {}
        for call in calls:
            for key, value in (call.get("usage") or {}).items():
                if isinstance(value, int):
                    usage[key] = usage.get(key, 0) + value
        body["usage"] = usage
        summary = self.summary()
        if "completion_tokens" in usage:
            summary += (f" · {usage['completion_tokens']} tokens de salida en {len(calls)} llamada(s)" if self.lang == "es"
                        else f" · {usage['completion_tokens']} output tokens in {len(calls)} call(s)")
        body["mini"] = {"ok": bool(self.last_run and self.last_run.get("ok")), "calls": len(calls), "summary": summary}
        return _Response(body, summary)


_json = json  # ``post`` takes a ``json=`` argument like requests; keep the module reachable


class _Response:
    """Minimal requests-like response returned by ``Workflow.post``."""

    status_code = 200
    ok = True
    reason = "OK"

    def __init__(self, body, summary):
        self._body = body
        self.mini_summary = summary
        self.headers = {"content-type": "application/json"}

    def json(self, **_):
        return copy.deepcopy(self._body)

    @property
    def text(self):
        return _json.dumps(self._body, ensure_ascii=False)

    @property
    def content(self):
        return self.text.encode("utf-8")

    def raise_for_status(self):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate, repair and return JSON in one step (no model call)")
    ap.add_argument("file", help="response .mini file, or - for stdin")
    ap.add_argument("--out")
    ap.add_argument("--history", help="optional local run history; may contain application data")
    ap.add_argument("--expected-records", type=int)
    ap.add_argument("--report", action="store_true", help="return the complete run report instead of only data")
    ap.add_argument("--envelope", action="store_true", help="stdin/file JSON contains text and an optional correction")
    args = ap.parse_args(argv)
    workflow = Workflow()
    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_bytes().decode("utf-8")
    correction = None
    if args.envelope:
        envelope = json.loads(text)
        text, correction = envelope["text"], envelope.get("correction")
    try:
        data = workflow.process(text, generate=(lambda _: correction) if correction is not None else None,
                                expected_records=args.expected_records)
    except WorkflowError as exc:
        print(json.dumps(exc.report, ensure_ascii=False), file=sys.stderr)
        status = 1
    else:
        output = json.dumps(workflow.last_run if args.report else data, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            Path(args.out).write_bytes(output.encode("utf-8"))
        else:
            print(output, end="")
        status = 0
    if args.history:
        Path(args.history).write_bytes((json.dumps(workflow.last_run, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
