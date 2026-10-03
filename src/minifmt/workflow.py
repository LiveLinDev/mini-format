"""Provider-independent generate -> validate -> repair -> JSON workflow.

Copied into generated toolkits; Python standard library only. A caller supplies
its own model callback. Credentials and SDK clients never enter the history.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
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

    def process(self, text, *, generate=None, task="", expected_records=None, max_repairs=1):
        if not isinstance(text, str):
            raise ValueError("the model callback must return text")
        if max_repairs not in (0, 1, 2, 3):
            raise ValueError("max_repairs must be between 0 and 3")
        if expected_records is not None and (type(expected_records) is not int or expected_records < 0):
            raise ValueError("expected_records must be a nonnegative integer")
        trace = [{"stage": "generate", "text": text},
                 {"stage": "validate", **self.runtime.diagnose(text, self.contract)}]
        self.last_run = {"ok": False, "trace": trace}
        repaired = self.runtime.repair(text, self.contract)
        trace.append({"stage": "repair", "ok": repaired["ok"], "changes": repaired["changes"],
                      "errors": repaired["diagnostics"]["errors"]})
        text = repaired["text"]
        for attempt in range(max_repairs + 1):
            report = self.runtime.diagnose(text, self.contract)
            if report["ok"] and expected_records is not None and report["records"] != expected_records:
                report = {"ok": False, "invalid_lines": [], "errors": [
                    {"code": "D_EXPECTED_COUNT", "message": f"expected {expected_records} records, received {report['records']}"}],
                    "repair_prompt": "Regenerate the complete document with the required record count. Never invent unavailable facts."}
            if report["ok"]:
                data = self.runtime.decode(text, self.contract)
                trace.append({"stage": "parse", "ok": True, "records": report["records"]})
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
