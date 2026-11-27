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

_UNDECODED = object()


def _runtime(bundle):
    spec = importlib.util.spec_from_file_location("_mini_workflow_parser", bundle / "parser.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unwrap_json_reply(text):
    changes = []
    if text.startswith("\ufeff"):
        text = text[1:]
        changes.append("removed UTF-8 BOM")
    outer = text.strip(" \r\n\t")
    if outer.startswith("```"):
        fence = re.fullmatch(r"```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```", outer, re.IGNORECASE)
        if fence:
            text = fence.group(1)
            changes.append("removed complete Markdown code fence")
    return text, changes


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

    def __init__(self, bundle=None, lang=None, *, prompt_style="full", kv_cache_first=False):
        self.bundle = Path(bundle or Path(__file__).resolve().parent).resolve()
        if lang is None:
            settings = self.bundle / "setup.json"
            lang = json.loads(settings.read_text(encoding="utf-8"))["language"] if settings.is_file() else "es"
        if lang not in ("es", "en"):
            raise ValueError("lang must be es or en")
        if prompt_style not in ("full", "lean"):
            raise ValueError("prompt_style must be full or lean")
        self.lang = lang
        self.prompt_style = prompt_style
        self.kv_cache_first = bool(kv_cache_first)
        self.runtime = _runtime(self.bundle)
        self.contract = self.runtime.load_contract(self.bundle / "contract.json")
        self.full_prompt = (self.bundle / f"prompt.{lang}.md").read_text(encoding="utf-8")
        lean_file = self.bundle / f"prompt.lean.{lang}.md"
        self.lean_prompt = lean_file.read_text(encoding="utf-8") if lean_file.is_file() else self.full_prompt
        self.format_prompt = self.lean_prompt if prompt_style == "lean" else self.full_prompt
        self.last_run = None

    def prompt(self, task, expected_records=None, *, style=None, kv_cache_first=None):
        count = "" if expected_records is None else f"\nRequired record count: {expected_records}."
        if style == "lean":
            fmt = self.lean_prompt
        elif style == "full":
            fmt = self.full_prompt
        else:
            fmt = self.format_prompt
        cache_first = self.kv_cache_first if kv_cache_first is None else kv_cache_first
        if cache_first:
            return f"Output format (replaces JSON instructions):\n{fmt}\n\nTask / Tarea:\n{task}{count}"
        return f"Task / Tarea:\n{task}{count}\n\nOutput format (replaces JSON instructions):\n{fmt}"

    def _csv_pair_for_task(self, task):
        # Retain explicit JSON escaping when the task includes escape sequences other than quotes.
        return self.lang == "es" and re.search(r'\\(?!")|\t', task) is None

    def rows_prompt(self, task, *, last_text_field, expected_records, kv_cache_first=None, known_rows=None):
        projection = {} if known_rows is None else {"known_rows": known_rows}
        if hasattr(self.runtime, "_from_csv_pair"):
            projection["csv_pair"] = self._csv_pair_for_task(task)
        format_prompt = self.runtime.make_rows_prompt(
            self.contract, last_text_field=last_text_field, expected_records=expected_records, lang=self.lang,
            **projection
        )
        return format_prompt + "\n" + task

    def run_compact(self, generate, task, *, last_text_field, expected_records, max_repairs=1):
        """Generate and validate space-delimited compact rows (minimal prompt + output tokens)."""
        prompt = self.rows_prompt(task, last_text_field=last_text_field, expected_records=expected_records)
        reply = generate(prompt)
        return self.process_rows(reply, last_text_field=last_text_field, expected_records=expected_records,
                                 generate=generate, task=task, max_repairs=max_repairs)

    def process_rows(self, text, *, last_text_field, expected_records, generate=None, task="", max_repairs=1,
                     known_rows=None):
        """Validate model rows and store a canonical .mini document in the run history."""
        projection = {} if known_rows is None else {"known_rows": known_rows}
        if hasattr(self.runtime, "_from_csv_pair"):
            projection["csv_pair"] = self._csv_pair_for_task(task)

        def parse(response):
            return self.runtime.decode_rows(response, self.contract, last_text_field=last_text_field,
                                            expected_records=expected_records, **projection)

        def retry(correction):
            prompt = self.rows_prompt(task, last_text_field=last_text_field, expected_records=expected_records,
                                      known_rows=known_rows)
            return generate(prompt + "\n" + correction)

        return self._process_compact(text, parse, retry if generate is not None else None, max_repairs,
                                     {"last_text_field": last_text_field})

    def _process_positional(self, text, expected_records, *, retry=None, max_repairs=1):
        def parse(response):
            changes = []
            if isinstance(response, str):
                response, changes = _unwrap_json_reply(response)
            try:
                data = self.runtime.decode_positional_json(response, self.contract, expected_records=expected_records)
            except self.runtime.DomainError as exc:
                if (exc.code != "D_VALUE" or not isinstance(response, str)
                        or not response.rstrip(" \r\n\t").endswith("]")):
                    raise
                try:
                    # Only complete, correctly typed rows may supply the planned count.
                    data = self.runtime.decode_positional_json(
                        response + "]", self.contract, expected_records=expected_records
                    )
                except self.runtime.DomainError:
                    raise exc from None
                changes.append("closed positional JSON array")
            if changes:
                self.last_run["trace"].append({"stage": "repair", "ok": True, "errors": [],
                                               "changes": changes})
            return data
        return self._process_compact(text, parse, retry, max_repairs, {"positional_json": True})

    def _process_compact(self, text, parse, retry, max_repairs, metadata):
        if max_repairs not in (0, 1, 2, 3):
            raise ValueError("max_repairs must be between 0 and 3")
        trace = [{"stage": "generate", "text": text}]
        self.last_run = {"ok": False, "trace": trace, **metadata}
        for attempt in range(max_repairs + 1):
            try:
                data = parse(text)
            except self.runtime.DomainError as exc:
                correction = ("Devuelve todas las filas de la fuente. Corrige " if self.lang == "es"
                              else "Return every row from the source. Fix ") + exc.message
                report = {"ok": False, "errors": [exc.to_dict()], "invalid_lines": [], "repair_prompt": correction}
                trace.append({"stage": "validate", **report})
                self.last_run.update(diagnostics=report, mini=text)
                if retry is None or attempt == max_repairs or exc.code == "D_COMPACT_SCHEMA":
                    raise WorkflowError(self.last_run) from exc
                text = retry(correction)
                trace.append({"stage": "model_repair", "attempt": attempt + 1, "selective": False, "text": text})
            else:
                mini = self.runtime.encode(data, self.contract)
                trace.append({"stage": "parse", "ok": True, "records": len(data)})
                self.last_run.pop("diagnostics", None)
                self.last_run.update(ok=True, data=data, mini=mini)
                return data

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
        at_line_end = text.rstrip(" \t").endswith("\n")
        repaired, data = self._repair_with_value(text)
        report = repaired["diagnostics"]
        original_report = report if repaired["text"] == text else self.runtime.diagnose(text, self.contract)
        trace = [{"stage": "generate", "text": text},
                 {"stage": "validate", **original_report}]
        self.last_run = {"ok": False, "trace": trace}
        trace.append({"stage": "repair", "ok": repaired["ok"], "changes": repaired["changes"],
                      "errors": report["errors"]})
        if _round == 0 and not report["ok"] and not truncated:
            alternate = self._recover_json_reply(text, expected_records)
            if alternate is not None:
                data, document, count, changes = alternate
                trace[0]["reply_format"] = "json"
                trace[-1] = {"stage": "repair", "ok": True, "changes": changes, "errors": []}
                trace.append({"stage": "parse", "ok": True, "records": count})
                self.last_run.update(ok=True, mini=document, data=data)
                return data
        text = repaired["text"]
        cut = None
        if generate is not None and _round < 2 and (truncated or not report["ok"]):
            cut = self._cut(text, truncated, at_line_end, diagnostics=report)
        target = expected_records
        if cut is not None:
            text, declared, kept = cut
            target = expected_records if expected_records is not None else declared
            expected_records = None  # the complete part is validated on its own; the rest is requested below
            trace.append({"stage": "truncation", "declared": declared, "complete_records": kept})
            report = self.runtime.diagnose(text, self.contract)
            data = _UNDECODED
        for attempt in range(max_repairs + 1):
            if report["ok"] and expected_records is not None and report["records"] != expected_records:
                report = {"ok": False, "invalid_lines": [], "errors": [
                    {"code": "D_EXPECTED_COUNT", "message": f"expected {expected_records} records, received {report['records']}"}],
                    "repair_prompt": "Regenerate the complete document with the required record count. Never invent unavailable facts."}
            if report["ok"]:
                if data is _UNDECODED:
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
            invalid_lines = report.get("invalid_lines")
            selective = bool(invalid_lines)
            correction_prompt = self.prompt(task, expected_records) + "\n\nOriginal response:\n" + text
            correction_prompt += "\n\nCORRECTION REQUEST (overrides output format for this call):\n" + report["repair_prompt"]
            correction = generate(correction_prompt)
            trace.append({"stage": "model_repair", "attempt": attempt + 1, "selective": selective, "text": correction})
            try:
                if selective:
                    text, from_document = self._apply_model_repair(text, correction, invalid_lines)
                    if from_document:
                        trace[-1]["reply_format"] = "mini"
                    report = self.runtime.diagnose(text, self.contract)
                    data = _UNDECODED
                else:
                    result, data = self._repair_with_value(correction)
                    text = result["text"]
                    report = result["diagnostics"]
            except (ValueError, TypeError) as exc:
                self.last_run.update(diagnostics={"ok": False, "errors": [{"code": "D_REPAIR", "message": str(exc)}]}, mini=text)
                raise WorkflowError(self.last_run) from exc
            trace.append({"stage": "revalidate", **report})
        raise AssertionError("unreachable")

    def _repair_with_value(self, text):
        repair = getattr(self.runtime, "_repair_with_value", None)
        if repair is None:
            return self.runtime.repair(text, self.contract), _UNDECODED
        return repair(text, self.contract)

    def _recover_json_reply(self, text, expected_records):
        text, changes = _unwrap_json_reply(text)
        if not text.lstrip(" \r\n\t").startswith(("[", "{")):
            return None
        try:
            data = self.runtime._strict_json(text)
            document = self.runtime.encode(data, self.contract, shared=False, dictionaries=False)
            # Use the same UTF-8 boundary as the CLI and the saved result.
            document.encode("utf-8")
        except (ValueError, RecursionError):
            return None
        records = self._records(data)
        count = 1 if records is None else len(records)
        if expected_records is not None and count != expected_records:
            return None
        changes.append("converted validated JSON to .mini")
        return data, document, count, changes

    def _apply_model_repair(self, text, correction, invalid_lines):
        try:
            replacements = self.runtime._strict_json(correction)
        except ValueError:
            if not isinstance(correction, str):
                raise
            complete = self.runtime.repair(correction, self.contract)
            if not complete["ok"]:
                raise
            old = text.removesuffix("\n").split("\n")
            received = complete["text"].removesuffix("\n").split("\n")
            allowed = set(invalid_lines)
            if len(old) != len(received) or any(
                    number not in allowed and before != after
                    for number, (before, after) in enumerate(zip(old, received), 1)):
                raise self.runtime.DomainError("D_REPAIR", "complete correction changed the header or a validated row")
            if (len(received) in allowed and not complete["text"].endswith("\n")
                    and "removed complete Markdown code fence" not in complete["changes"]):
                raise self.runtime.DomainError("D_REPAIR", "complete correction did not terminate the last repaired row")
            replacements = {str(number): received[number - 1] for number in invalid_lines}
            return self.runtime.apply_replacements(text, replacements, self.contract), True
        return self.runtime.apply_replacements(text, replacements, self.contract), False

    def _cut(self, text, truncated, at_line_end=False, *, diagnostics=None):
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
            report = diagnostics if diagnostics is not None else self.runtime.diagnose(text, self.contract)
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
            new = self._records(more) or []
            if len(new) > missing:
                # A complete restart can supply the suffix after the retained prefix.
                matches_prefix = False
                if len(new) == target:
                    prefix = copy.deepcopy(more)
                    del self._records(prefix)[len(records):]
                    matches_prefix = (json.dumps(prefix, ensure_ascii=False, sort_keys=True)
                                      == json.dumps(data, ensure_ascii=False, sort_keys=True))
                if not matches_prefix:
                    trace.append({"stage": "continuation_rejected", "requested": missing, "received": len(new)})
                    continue
                trace.append({"stage": "continuation_overlap", "records": len(records)})
                new = new[len(records):]
            trace.append({"stage": "continuation_parse", "ok": True, "records": len(new)})
            records.extend(new)
        if len(records) != target:
            self.last_run.update(diagnostics={"ok": False, "invalid_lines": [], "errors": [
                {"code": "D_EXPECTED_COUNT", "message": f"expected {target} records, received {len(records)}"}]})
            raise WorkflowError(self.last_run)
        return data

    def save_run(self, folder):
        """Write the last run so it can be inspected with ``mini validate``, ``mini diagnose`` or ``mini to-json``.

        Each model answer is saved exactly as received. Compact rows use ``.txt`` and JSON replacements use
        ``.json``. Complete documents use ``.mini``. The folder also gets the validated ``resultado.mini``
        and trace ``ejecucion.json``. Earlier files in the folder are replaced. The files contain application data.
        """
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        for old in list(folder.glob("*.mini")) + list(folder.glob("*.json")):
            old.unlink()
        for old in list(folder.glob("respuesta_*.txt")) + list(folder.glob("response_*.txt")):
            if old.stem.rsplit("_", 1)[-1].isdigit():
                old.unlink()
        run = self.last_run or {}
        es = self.lang == "es"
        if run.get("positional_json"):
            raw_suffix = ".json"
        else:
            raw_suffix = ".txt" if run.get("last_text_field") is not None else ".mini"
        answers = [(step["text"], ".json" if step.get("reply_format") == "json" or (
                    step.get("stage") == "model_repair" and step.get("selective")
                    and step.get("reply_format") != "mini") else raw_suffix)
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
        if repaired and (run.get("last_text_field") is not None or run.get("positional_json")):
            parts.append(f"{repaired} corrección(es) del modelo" if es else f"{repaired} model correction(s)")
        elif repaired:
            parts.append(f"{repaired} corrección(es) selectiva(s) del modelo" if es else f"{repaired} selective model correction(s)")
        if local:
            nombres = {"removed UTF-8 BOM": "BOM eliminado", "normalized CRLF to LF": "saltos de línea normalizados",
                       "removed complete Markdown code fence": "bloque Markdown eliminado",
                       "closed positional JSON array": "array JSON posicional cerrado",
                       "converted validated JSON to .mini": "JSON validado convertido a .mini",
                       "removed unclosed Markdown code fence": "bloque Markdown sin cerrar eliminado",
                       "removed trailing blank lines": "líneas vacías finales eliminadas",
                       "removed surplus trailing row separators": "separadores finales sobrantes eliminados"}
            parts.append(("ajustes locales: " if es else "local fixes: ") + ", ".join(nombres.get(c, c) if es else c for c in local))
        return " · ".join(parts)

    def run(self, generate, task, *, expected_records=None, max_repairs=1, last_text_field=None, known_rows=None):
        if known_rows is not None and last_text_field is None:
            raise ValueError("known_rows requires compact rows with a last_text_field")
        if last_text_field is not None:
            if max_repairs not in (0, 1, 2, 3):
                raise ValueError("max_repairs must be between 0 and 3")
            known_rows = copy.deepcopy(known_rows)
            text = generate(self.rows_prompt(task, last_text_field=last_text_field, expected_records=expected_records,
                                             known_rows=known_rows))
            return self.process_rows(text, generate=generate, task=task, last_text_field=last_text_field,
                                     expected_records=expected_records, max_repairs=max_repairs, known_rows=known_rows)
        return self.process(generate(self.prompt(task, expected_records)), generate=generate, task=task,
                            expected_records=expected_records, max_repairs=max_repairs)

    def run_positional(self, generate, task, *, expected_records, max_repairs=1):
        """Call generate(prompt, schema) and validate the provider's positional JSON."""
        if max_repairs not in (0, 1, 2, 3):
            raise ValueError("max_repairs must be between 0 and 3")
        request = self.runtime.positional_json_request(task, self.contract, expected_records=expected_records,
                                                       lang=self.lang)
        prompt, schema = request["prompt"], request["schema"]

        def retry(correction):
            return generate(prompt + "\n" + correction, schema)

        return self._process_positional(generate(prompt, schema), expected_records, retry=retry,
                                        max_repairs=max_repairs)

    async def run_async(self, generate, task, *, expected_records=None, max_repairs=1):
        """Use the same validated pipeline with an asynchronous model callback."""
        loop = asyncio.get_running_loop()
        text = await generate(self.prompt(task, expected_records))

        def correction(prompt):
            return asyncio.run_coroutine_threadsafe(generate(prompt), loop).result()

        return await asyncio.to_thread(self.process, text, generate=correction, task=task,
                                       expected_records=expected_records, max_repairs=max_repairs)

    def complete(self, create, *, messages, expected_records=None, max_repairs=1,
                 kv_cache_first=None, prompt_style=None, **kwargs):
        """Bridge an existing OpenAI-compatible chat completion SDK call.

        Keep model, client, business messages and other generation parameters.
        JSON response_format is removed because the model now returns .mini.
        The initial SDK finish reason signals a response cut by the output limit.
        """
        kwargs.pop("response_format", None)
        if kwargs.get("stream") or kwargs.get("tools") or kwargs.get("functions") or kwargs.get("n", 1) != 1:
            raise ValueError("use Workflow.run with a text callback for streaming, tools or multiple choices")
        original = [dict(message) for message in messages]
        cache_first = self.kv_cache_first if kv_cache_first is None else kv_cache_first

        def request(prompt, *, initial=False):
            if cache_first and initial:
                fmt = self.lean_prompt if prompt_style == "lean" else self.format_prompt
                count = "" if expected_records is None else f"\nRequired record count: {expected_records}."
                msgs = [{"role": "system", "content": fmt}] + original + (
                    [{"role": "system", "content": count.lstrip()}] if count else []
                )
            else:
                msgs = original + [{"role": "system", "content": prompt}]
            response = create(messages=msgs, **kwargs)
            if isinstance(response, dict):
                choice = response["choices"][0]
                return choice["message"]["content"], choice.get("finish_reason")
            choice = response.choices[0]
            return choice.message.content, getattr(choice, "finish_reason", None)

        task = "Follow the original application messages."
        text, finish_reason = request(self.prompt(task, expected_records, style=prompt_style), initial=True)
        return self.process(text, generate=lambda prompt: request(prompt)[0], task=task,
                            expected_records=expected_records, max_repairs=max_repairs,
                            truncated=finish_reason == "length")

    def post(self, send, url, *, json=None, expected_records=None, max_repairs=1,
             kv_cache_first=None, prompt_style=None, **kwargs):
        """Bridge an HTTP call to an OpenAI-compatible chat/completions endpoint (``requests.post``, ``httpx.post``).

        Only JSON-mode chat requests change: ``response_format`` is removed, the format prompt is added as a last
        system message (or prepended as static prefix when ``kv_cache_first=True``) and the .mini answer is validated,
        repaired and decoded. The application receives a response with the same shape whose ``message.content`` is the
        validated JSON document, and ``usage`` adds up every call. Any other request, and any HTTP error, is returned unchanged.
        """
        payload = json
        if (not isinstance(payload, dict) or "messages" not in payload or "response_format" not in payload
                or payload.get("stream") or payload.get("tools") or payload.get("functions") or payload.get("n", 1) != 1):
            return send(url, json=payload, **kwargs)
        base = {key: value for key, value in payload.items() if key != "response_format"}
        original = [dict(message) for message in base["messages"]]
        calls = []
        cache_first = self.kv_cache_first if kv_cache_first is None else kv_cache_first

        class _Failed(Exception):
            def __init__(self, response):
                super().__init__("HTTP error")
                self.response = response

        def generate(prompt, *, initial=False):
            if cache_first and initial:
                fmt = self.lean_prompt if prompt_style == "lean" else self.format_prompt
                count = "" if expected_records is None else f"\nRequired record count: {expected_records}."
                msgs = [{"role": "system", "content": fmt}] + original + (
                    [{"role": "system", "content": count.lstrip()}] if count else []
                )
            else:
                msgs = original + [{"role": "system", "content": prompt}]
            response = send(url, json=dict(base, messages=msgs), **kwargs)
            if getattr(response, "status_code", 200) >= 400:
                raise _Failed(response)
            body = response.json()
            calls.append(body)
            choice = (body.get("choices") or [{}])[0]
            return (choice.get("message") or {}).get("content") or ""

        task = "Follow the original application messages."
        try:
            text = generate(self.prompt(task, expected_records, style=prompt_style), initial=True)
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
    # Match the domain CLI's UTF-8 protocol, including isolated Python on Windows.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Validate, repair and return JSON in one step (no model call)")
    ap.add_argument("file", help="response .mini file, or - for stdin")
    ap.add_argument("--out")
    ap.add_argument("--history", help="optional local run history; may contain application data")
    ap.add_argument("--expected-records", type=int)
    ap.add_argument("--last-text-field", help="read compact rows with this final string column")
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--rows-prompt", action="store_true", help="read the task and emit compact row instructions")
    modes.add_argument("--positional-request", action="store_true", help="read the task and emit a prompt and JSON schema")
    modes.add_argument("--positional-json", action="store_true", help="read compact positional JSON rows")
    ap.add_argument("--lang", choices=("es", "en"))
    ap.add_argument("--report", action="store_true", help="return the complete run report instead of only data")
    ap.add_argument("--envelope", action="store_true", help="read a JSON envelope with the text and optional row context")
    args = ap.parse_args(argv)
    workflow = Workflow(lang=args.lang)
    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_bytes().decode("utf-8")
    if args.positional_request or args.positional_json:
        if args.last_text_field is not None:
            ap.error("positional JSON uses the contract's column order")
        if args.positional_request:
            try:
                request = workflow.runtime.positional_json_request(
                    text, workflow.contract, expected_records=args.expected_records, lang=workflow.lang
                )
            except ValueError as exc:
                ap.error(str(exc))
            print(json.dumps(request, ensure_ascii=False))
            return 0
    if args.rows_prompt:
        try:
            packet = json.loads(text) if args.envelope else {"task": text}
            print(workflow.rows_prompt(packet["task"], last_text_field=args.last_text_field,
                                       expected_records=args.expected_records, known_rows=packet.get("known_rows")),
                  end="")
        except ValueError as exc:
            ap.error(str(exc))
        return 0
    correction = None
    task = ""
    known_rows = None
    if args.envelope:
        envelope = json.loads(text)
        text, correction = envelope["text"], envelope.get("correction")
        known_rows = envelope.get("known_rows")
        task = envelope.get("task", "")
        if known_rows is not None and (args.last_text_field is None or args.positional_json):
            ap.error("known_rows requires --last-text-field")
    try:
        generate = (lambda _: correction) if correction is not None else None
        if args.positional_json:
            data = workflow._process_positional(text, args.expected_records, retry=generate)
        elif args.last_text_field is None:
            data = workflow.process(text, generate=generate, expected_records=args.expected_records)
        else:
            data = workflow.process_rows(text, generate=generate, task=task, last_text_field=args.last_text_field,
                                         expected_records=args.expected_records, known_rows=known_rows)
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
