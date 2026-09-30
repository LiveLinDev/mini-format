"""First-run flows against the generated toolkit, not only prompt strings."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from minifmt import cli
from minifmt.onboarding import _read_sample


def _wizard(answers):
    output = io.StringIO()
    with mock.patch("builtins.input", side_effect=answers), contextlib.redirect_stdout(output):
        result = cli.main(["init"])
    return result, output.getvalue()


def test_existing_data_builds_a_valid_guide_and_toolkit(tmp_path):
    source = tmp_path / "incidentes.json"
    source.write_text(json.dumps({"incidentes": [{"id": 101, "titulo": "No puedo entrar"}]}), encoding="utf-8")
    destination = tmp_path / "mi-kit"
    result, output = _wizard(["1", str(source), "inc", str(destination)])
    assert result == 0
    assert "Toolkit creado" in output
    guide = (destination / "GUIA.md").read_text(encoding="utf-8")
    assert '"mi-kit/validator.py"' in guide
    assert "D_ENVELOPE" in guide
    assert "GUIA.md" in json.loads((destination / "manifest.json").read_text(encoding="utf-8"))["files"]
    validation = subprocess.run([sys.executable, str(destination / "validator.py"), str(destination / "example.mini")],
                                capture_output=True, text=True, cwd=tmp_path)
    assert validation.returncode == 0, validation.stderr
    assert json.loads(validation.stdout)["ok"] is True


def test_no_data_flow_creates_own_fields(tmp_path):
    destination = tmp_path / ".mini"
    result, _ = _wizard(["2", "incidentes", "id", "2", "101", "titulo", "1", "Error de acceso", "", "inc", str(destination)])
    assert result == 0
    assert json.loads((destination / "example.json").read_text(encoding="utf-8")) == {
        "incidentes": [{"id": 101, "titulo": "Error de acceso"}]}
    assert "inc|" in (destination / "example.mini").read_text(encoding="utf-8")


def test_csv_and_xml_are_accepted_as_source_data(tmp_path):
    csv_file = tmp_path / "tickets.csv"
    csv_file.write_text("id,titulo\n001,Error\n002,Lento\n", encoding="utf-8")
    assert _read_sample(csv_file) == [{"id": "001", "titulo": "Error"}, {"id": "002", "titulo": "Lento"}]
    xml_file = tmp_path / "tickets.xml"
    xml_file.write_text("<tickets><ticket><id>1</id><titulo>Error</titulo></ticket><ticket><id>2</id><titulo>Lento</titulo></ticket></tickets>", encoding="utf-8")
    assert _read_sample(xml_file) == {"ticket": [{"id": "1", "titulo": "Error"}, {"id": "2", "titulo": "Lento"}]}


def test_existing_toolkit_is_not_overwritten(tmp_path):
    source = tmp_path / "data.json"
    source.write_text('[{"id": 1}]', encoding="utf-8")
    destination = tmp_path / ".mini"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with mock.patch("builtins.input", side_effect=["1", str(source), "data", str(destination)]), contextlib.redirect_stdout(io.StringIO()):
        assert cli.main(["init"]) == 2
    assert marker.read_text(encoding="utf-8") == "keep"


def test_plain_invocation_in_a_pipe_and_help_alias():
    output = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO()), contextlib.redirect_stdout(output):
        assert cli.main([]) == 0
    assert "mini init" in output.getvalue()
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert cli.main(["help"]) == 0
    assert "init" in output.getvalue()
