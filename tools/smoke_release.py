"""Verify downloadable artifacts offline, outside the repository checkout.

Run after build_release.py: python tools/smoke_release.py --directory dist
Only the wheel/tarball under test are installed, into disposable directories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import venv
import zipfile


def run(args, cwd, *, expected=0, input_text=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            encoding="utf-8", errors="replace", input=input_text)
    if result.returncode != expected:
        raise AssertionError(f"{args}: exit {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main(directory):
    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    for entry in manifest["files"]:
        data = (directory / entry["name"]).read_bytes()
        assert len(data) == entry["bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["name"]
    with tempfile.TemporaryDirectory(prefix="mini_install_test_") as td:
        work = Path(td)
        with zipfile.ZipFile(directory / f"mini-format-{version}.zip") as archive:
            archive.extractall(work)
        kit = work / f"mini-format-{version}"
        venv.EnvBuilder(with_pip=True).create(work / "env")
        bindir = work / "env" / ("Scripts" if os.name == "nt" else "bin")
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        mini = bindir / ("mini.exe" if os.name == "nt" else "mini")
        run([python, "-m", "pip", "install", "--no-index", kit / f"mini_format-{version}-py3-none-any.whl"], work)
        assert "mini setup" in run([mini], work, input_text="")
        (work / "incidentes.csv").write_text("id,titulo\n101,Error de acceso\n", encoding="utf-8")
        guide = run([mini, "setup"], work, input_text="1\nincidentes.csv\ninc\nmi-formato\n")
        assert "Toolkit creado" in guide
        assert (work / "mi-formato/GUIA.md").is_file()
        run([python, work / "mi-formato/validator.py", work / "mi-formato/example.mini"], work)
        assert "No contracts loaded" in run([mini, "forks"], work)
        with zipfile.ZipFile(directory / f"mini-format-{version}-example-families.zip") as archive:
            archive.extractall(work / "optional")
        forks = work / "optional" / "forks"
        run([mini, "check-forks", forks], work)
        run([mini, "build", kit / "examples/phones.json", kit / "examples/phones-extra.json",
             "--prefix", "phone", "--out", work / ".mini"], work)
        contract = work / ".mini/contract.json"
        run([mini, "from-json", kit / "examples/phones.json", "--contract", contract, "--out", "phones.mini"], work)
        run([mini, "validate", "phones.mini", "--contract", contract], work)
        run([mini, "to-json", "phones.mini", "--contract", contract, "--out", "roundtrip.json"], work)
        original = json.loads((kit / "examples/phones.json").read_text(encoding="utf-8"))
        assert json.loads((work / "roundtrip.json").read_text(encoding="utf-8")) == original
        # Remove the installed package. The generated runtime must still work.
        run([python, "-m", "pip", "uninstall", "-y", "mini-format"], work)
        parser = work / ".mini/parser.py"
        run([python, parser, "decode", "phones.mini", "--out", "standalone.json"], work)
        assert json.loads((work / "standalone.json").read_text(encoding="utf-8")) == original
        text = (work / "phones.mini").read_text(encoding="utf-8")
        (work / "fenced.mini").write_text("```mini\n" + text.rstrip("\n") + "\n```", encoding="utf-8")
        run([python, parser, "repair", "fenced.mini", "--out", "repaired.mini"], work)
        run([python, work / ".mini/validator.py", "repaired.mini"], work)
        invalid = text.splitlines()
        invalid[1] += "|EXTRA"
        (work / "invalid.mini").write_bytes("\n".join(invalid).encode("utf-8"))
        report = json.loads(run([python, parser, "diagnose", "invalid.mini"], work, expected=1))
        assert not report["ok"] and 2 in report["invalid_lines"]
        (work / "corrections.json").write_text(json.dumps({"2": text.splitlines()[1]}), encoding="utf-8")
        run([python, parser, "apply", "invalid.mini", "corrections.json", "--out", "corrected.mini"], work)
        run([python, parser, "validate", "corrected.mini"], work)

        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        # Proyecto npm propio: sin él, npm busca un package.json en carpetas superiores
        # (p. ej. el directorio personal) e instala el paquete allí.
        (work / "package.json").write_text('{"name": "mini-install-test", "private": true}\n', encoding="utf-8")
        run([npm, "install", "--offline", "--no-audit", "--no-fund", "--ignore-scripts",
             kit / f"mini-format-core-{version}.tgz"], work)
        # Exercise compiled ESM with the optional sample families and streaming.
        code = """
import { readFileSync } from 'node:fs';
import { Registry, parse, createReader, VERSION } from '@mini-format/core';
if (Registry.load().size !== 0) throw Error('Core package should not bundle example families');
const c = Registry.load('optional/forks').get('a');
const text = readFileSync('optional/forks/a/fixtures/valid.mini', 'utf8');
const doc = parse(text, c);
if (doc.records.length !== 12) throw Error('Expected 12 records');
const reader = createReader(c);
for (const char of text) reader.push(char);
if (JSON.stringify(reader.end().document.toCanonical()) !== JSON.stringify(doc.toCanonical())) throw Error('Streaming mismatch');
console.log('Installed ESM and streaming OK', VERSION);
"""
        run(["node", "--input-type=module", "-e", code], work)
    print("PASS: checksums, offline wheel + npm install, first-run wizard, optional families, JSON round-trip, standalone runtime, safe repair, selective repair, ESM streaming")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("dist"))
    main(parser.parse_args().directory)
