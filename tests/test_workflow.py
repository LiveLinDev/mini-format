"""Application-level proofs: exact JSON, preserved lines and blocked bad data."""
import importlib.util
import asyncio
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from minifmt.domain import build_bundle, encode
from minifmt.integration import prepare
from minifmt.workflow import Workflow, WorkflowError
from test_onboarding import _wizard


@pytest.fixture
def kit(tmp_path):
    sample = [{"id": 1, "titulo": "Acceso"}, {"id": 2, "titulo": "Factura"}]
    bundle = tmp_path / ".mini"
    contract = build_bundle([sample], "ticket", bundle)
    return bundle, contract, sample


def test_selective_repair_preserves_good_lines_and_returns_exact_json(kit):
    bundle, contract, sample = kit
    valid = encode(sample, contract, shared=False, dictionaries=False)
    lines = valid.splitlines()
    raw = "```mini\r\n" + valid.replace("2|Factura", "dos|Factura").replace("\n", "\r\n") + "\r\n```"
    prompts = []
    def generate(prompt):
        prompts.append(prompt)
        return raw if len(prompts) == 1 else json.dumps({"3": lines[2]})
    flow = Workflow(bundle)
    assert flow.run(generate, "Classify support", expected_records=2) == sample
    assert flow.last_run["mini"] == valid
    assert len(prompts) == 2 and "prompt" not in flow.last_run
    assert "Classify support" in prompts[1] and contract["schema_id"] in prompts[1]
    assert flow.last_run["trace"][2]["changes"] == ["normalized CRLF to LF", "removed complete Markdown code fence"]


def test_missing_records_are_blocked_without_changing_count(kit):
    bundle, contract, sample = kit
    flow = Workflow(bundle)
    wire = encode(sample[:1], contract)
    calls = []
    def generate(prompt):
        calls.append(prompt)
        return wire
    with pytest.raises(WorkflowError):
        flow.run(generate, "Need two", expected_records=2)
    assert len(calls) == 2
    assert not flow.last_run["ok"] and "data" not in flow.last_run
    assert flow.last_run["diagnostics"]["errors"][0]["code"] == "D_EXPECTED_COUNT"


def test_repair_cannot_replace_valid_lines(kit):
    bundle, contract, sample = kit
    wire = encode(sample, contract, shared=False, dictionaries=False)
    replies = iter([wire.replace("2|Factura", "dos|Factura"), json.dumps({"2": "1|Alterado", "3": "2|Factura"})])
    flow = Workflow(bundle)
    with pytest.raises(WorkflowError):
        flow.run(lambda _: next(replies), "Classify")
    assert "data" not in flow.last_run
    assert flow.last_run["diagnostics"]["errors"][0]["code"] == "D_REPAIR"


def test_generated_cli_runs_under_isolated_python_without_package(kit, tmp_path):
    bundle, contract, sample = kit
    wire = "```mini\n" + encode(sample, contract) + "\n```"
    result = subprocess.run([sys.executable, "-I", str(bundle / "workflow.py"), "-", "--expected-records", "2"],
                            input=wire, text=True, encoding="utf-8", capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == sample
    bad = subprocess.run([sys.executable, "-I", str(bundle / "workflow.py"), "-", "--out", str(tmp_path / "bad.json")],
                         input="ticket|n=20\n", text=True, encoding="utf-8", capture_output=True, cwd=tmp_path)
    assert bad.returncode == 1 and not (tmp_path / "bad.json").exists()


def test_auto_integration_executes_original_sdk_callback_and_removes_json_mode(kit, tmp_path):
    bundle, contract, sample = kit
    source = tmp_path / "app.py"
    source.write_text('import json\ndef get_tickets(client):\n    response = client.chat.completions.create(model="existing", messages=[{"role":"user","content":"Extract tickets"}], response_format={"type":"json_object"})\n    data = json.loads(response.choices[0].message.content)\n    return data\n', encoding="utf-8")
    original = source.read_bytes()
    prepared = prepare(source, bundle)
    assert prepared["supported"] and not prepared["applied"] and source.read_bytes() == original
    applied = prepare(source, bundle, apply=True)
    assert applied["applied"] and Path(applied["backup"]).read_bytes() == original
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        text = "```mini\n" + encode(sample, contract) + "\n```"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    sys.path.insert(0, str(tmp_path))
    try:
        spec = importlib.util.spec_from_file_location("patched_app", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        assert module.get_tickets(client) == sample
    finally:
        sys.path.remove(str(tmp_path))
    assert len(calls) == 1 and calls[0]["model"] == "existing"
    assert "response_format" not in calls[0]
    assert calls[0]["messages"][0]["content"] == "Extract tickets"
    assert contract["schema_id"] in calls[0]["messages"][-1]["content"]


def test_unsupported_application_is_untouched_and_gets_a_real_plan(kit, tmp_path):
    bundle, _, _ = kit
    source = tmp_path / "app.ts"
    source.write_text('const data = JSON.parse(await provider.generateContent(task));', encoding="utf-8")
    original = source.read_bytes()
    report = prepare(source, bundle, lang="en")
    plan = Path(report["plan"]).read_text(encoding="utf-8")
    assert str(source) in plan and str(bundle / "prompt.en.md") in plan
    assert not report["supported"] and source.read_bytes() == original
    with pytest.raises(ValueError, match="automatic patch unavailable"):
        prepare(source, bundle, apply=True)
    assert source.read_bytes() == original


def test_english_setup_selects_english_prompt_and_prepares_integration(tmp_path):
    source = tmp_path / "app.ts"
    source.write_text("const data = JSON.parse(response);", encoding="utf-8")
    bundle = tmp_path / "toolkit"
    code, output = _wizard(["en", "4", "ticket", str(bundle), "2", str(source)])
    assert code == 0 and "Toolkit created" in output
    assert Workflow(bundle).lang == "en"
    prompt = (bundle / "try-prompt.md").read_text(encoding="utf-8")
    assert "Generate exactly 20" in prompt and Workflow(bundle).contract["schema_id"] in prompt
    assert "Integrate .mini" in (bundle / "integration/INTEGRATE.md").read_text(encoding="utf-8")
    # A later integration command keeps the language chosen at setup.
    assert "Integrate .mini" in Path(prepare(source, bundle)["plan"]).read_text(encoding="utf-8")


def test_recorded_20_ticket_run_is_reproducible():
    path = ROOT / "examples/flujo-soporte/run.py"
    spec = importlib.util.spec_from_file_location("support_replay", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    live_replay = module.execute()
    saved = json.loads((path.parent / "history.json").read_text(encoding="utf-8"))
    assert live_replay == saved and len(saved["data"]) == 20


def test_async_python_callback_uses_the_same_repair_pipeline(kit):
    bundle, contract, sample = kit
    valid = encode(sample, contract, shared=False, dictionaries=False)
    replies = iter([valid.replace("2|Factura", "dos|Factura"), json.dumps({"3": valid.splitlines()[2]})])
    async def generate(prompt):
        await asyncio.sleep(0)
        return next(replies)
    flow = Workflow(bundle)
    assert asyncio.run(flow.run_async(generate, "Classify", expected_records=2)) == sample
    assert flow.last_run["ok"]


def test_node_async_provider_repairs_and_returns_exact_json(kit, tmp_path):
    bundle, contract, sample = kit
    valid = encode(sample, contract, shared=False, dictionaries=False)
    script = tmp_path / "app.mjs"
    script.write_text(f"""import {{ Workflow }} from {json.dumps((bundle / 'workflow.mjs').as_uri())};
const replies = [{json.dumps(valid.replace('2|Factura', 'dos|Factura'))}, {json.dumps(json.dumps({'3':valid.splitlines()[2]}))}];
const flow = new Workflow({{python: {json.dumps(sys.executable)}}});
const data = await flow.run(async prompt => replies.shift(), 'Classify', {{expectedRecords:2}});
if (replies.length !== 0 || !flow.lastRun.ok) throw Error('repair did not run');
console.log(JSON.stringify(data));
""", encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == sample


def test_auto_patch_rejects_shared_line_statements(kit, tmp_path):
    bundle, _, _ = kit
    source = tmp_path / "app.py"
    source.write_text('import json\ndef fetch(client):\n    response = client.chat.completions.create(model="x", messages=[])\n    data = json.loads(response.choices[0].message.content); use(data)\n', encoding="utf-8")
    original = source.read_bytes()
    assert not prepare(source, bundle)["supported"]
    assert source.read_bytes() == original


def test_live_example_uses_the_prompt_and_never_stores_the_key(monkeypatch):
    path = ROOT / "examples/flujo-soporte/run.py"
    spec = importlib.util.spec_from_file_location("support_live_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = path.parent
    from minifmt.domain import infer_contract
    data = json.loads((base / "expected.json").read_text(encoding="utf-8"))
    wire = encode(data, infer_contract([data], "ticket"))
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({"choices":[{"message":{"content":wire}}]}).encode()
    requests = []
    def open_request(request, **kwargs):
        requests.append(request)
        return Response()
    monkeypatch.setattr(module.urllib.request, "urlopen", open_request)
    report = module.execute(key="fixture-key-keep-in-memory", model="fixture-model")
    assert report["mode"] == "live" and len(report["data"]) == 20
    assert "fixture-key" not in json.dumps(report)
    assert requests[0].full_url == "https://api.openai.com/v1/chat/completions"
    payload = json.loads(requests[0].data)
    assert payload["model"] == "fixture-model" and "20 mensajes" in payload["messages"][0]["content"]
    assert "mini-domain/1" in payload["messages"][0]["content"]
