"""Build downloadable, installable artifacts from a clean source staging directory.

    python -m pip install -e ".[release]"
    python tools/build_release.py --output sitio/downloads

No credentials, repository history, server configuration or private model runs
are copied. Node >=22.13 is used at build time to strip TypeScript to plain ESM.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
SPEC_VERSION = re.search(r'^SPEC_VERSION = "([^"]+)"', (ROOT / "src/minifmt/__init__.py").read_text(encoding="utf-8"), re.M).group(1)
DOCS = ("README.md", "README.es.md", "SPEC.md", "SPEC.es.md", "FORKING.md", "FORKING.es.md",
        "CONTRIBUTING.md", "CONTRIBUTING.es.md", "LICENSE", "BUILD_GUIDE.md", "BUILD_GUIDE.es.md",
        "DOMAIN_PROFILE.md", "DOMAIN_PROFILE.es.md", "CHANGELOG.md")
SOURCE_DIRS = ("src", "forks", "ts/src", "ts/test", "js", "tests", "conformance", "examples",
               "benchmark/public", "benchmark/toon_ref", "benchmark/vocab", "benchmark/results",
               "experiments/v1_tokens", "experiments/v4_costos", "experiments/v5_ancho",
               "experiments/v7_escalamiento", "experiments/v8_sima", "generative",
               "playground", "docs", "evidencia", "sitio/content", "sitio/i18n", "sitio/assets")
# Carpetas que NUNCA van a ningún archivo publicado aunque estén dentro de una de SOURCE_DIRS (datos restringidos).
EXCLUDED_TREES = ("evidencia/restringida",)
SOURCE_FILES = ("benchmark/formats.py", "benchmark/domains.py", "benchmark/run_benchmark.py",
                "benchmark/make_forks.py", "benchmark/make_figures.py",
                "experiments/README.md", "experiments/README.en.md", "experiments/comun.py",
                "tools/build_node.mjs", "tools/build_release.py", "tools/smoke_release.py", "tools/check_site.py",
                "tools/verificar_publicacion.py")
# Build inputs of the website: every source file at the top of sitio/ (the generator and its modules,
# styles, scripts, translation maps, 404.html...), so that a new module can never be forgotten here and the
# source archive can always rebuild the site. Not deployment tools (sitio/servidor, desplegar.sh) and not
# generated output (version.json, sitemap.xml, robots.txt, search-index.json, app.en.js).
# publicar.py assembles local evidence links, locales and SEO; it does not deploy.
SITE_SUFFIXES = {".py", ".css", ".js", ".json", ".svg", ".html", ".md"}
SITE_GENERATED = {"version.json", "robots.txt", "sitemap.xml", "search-index.json", "app.en.js"}


def site_files() -> list[str]:
    return sorted(p.name for p in (ROOT / "sitio").iterdir()
                  if p.is_file() and p.suffix in SITE_SUFFIXES and p.name not in SITE_GENERATED)


BUILD_EPOCH = 1767225600  # 2026-01-01 UTC, also used by the deterministic ZIP entries.
SKIP_PARTS = {"__pycache__", "node_modules", ".git", ".venv", "dist", "build", ".pytest_cache"}


def copy_file(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)


def is_excluded_tree(path: Path) -> bool:
    try:
        rel = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return False
    return any(rel == tree or rel.startswith(tree + "/") for tree in EXCLUDED_TREES)


def files_under(root: Path):
    for p in sorted(root.rglob("*")):
        if (p.is_file() and not any(x in SKIP_PARTS or x.endswith(".egg-info") for x in p.relative_to(root).parts)
                and p.suffix != ".pyc" and not is_excluded_tree(p)):
            yield p


def copy_tree(source: Path, dest: Path) -> None:
    if source.exists():
        for p in files_under(source):
            copy_file(p, dest / p.relative_to(source))


def zip_tree(source: Path, output: Path, prefix: str) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(source.rglob("*")):
            if not p.is_file():
                continue
            entry = zipfile.ZipInfo(f"{prefix}/{p.relative_to(source).as_posix()}", (2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            z.writestr(entry, p.read_bytes())


def npm_tar(source: Path, output: Path) -> None:
    with output.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as archive:
            for p in sorted(source.rglob("*")):
                if not p.is_file():
                    continue
                data = p.read_bytes()
                entry = tarfile.TarInfo("package/" + p.relative_to(source).as_posix())
                entry.size, entry.mode, entry.mtime = len(data), 0o644, 0
                archive.addfile(entry, io.BytesIO(data))


def build(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mini_release_") as td:
        stage = Path(td)
        source = stage / "source"
        for name in (*DOCS, ".gitattributes", "pyproject.toml", "setup.py", "MANIFEST.in", "ts/package.json", "ts/package-lock.json",
                     "ts/tsconfig.json", "ts/tsconfig.test.json", "ts/README.md", "ts/README.en.md"):
            p = ROOT / name
            if p.is_file():
                copy_file(p, source / name)
        for name in SOURCE_DIRS:
            copy_tree(ROOT / name, source / name)
        for name in SOURCE_FILES:
            copy_file(ROOT / name, source / name)
        # Website sources only: never ship SSH/deployment/server configuration,
        # generated downloads or recursive copies of release archives.
        for name in site_files():
            copy_file(ROOT / "sitio" / name, source / "sitio" / name)
        wheels = stage / "wheels"
        build_env = dict(os.environ, SOURCE_DATE_EPOCH=str(BUILD_EPOCH))
        built = subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(wheels), str(source)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=build_env)
        if built.returncode:
            raise RuntimeError(built.stdout + "\n" + built.stderr)
        wheel = next(wheels.glob("*.whl"))
        copy_file(wheel, output / wheel.name)

        node = stage / "node"
        copy_tree(ROOT / "ts/src", node / "src")
        copy_tree(ROOT / "forks", node / "forks")
        for name in ("package.json", "README.md", "README.en.md"):
            copy_file(ROOT / "ts" / name, node / name)
        copy_file(ROOT / "LICENSE", node / "LICENSE")
        subprocess.run(["node", "--no-warnings", str(ROOT / "tools/build_node.mjs"), str(node / "dist")], check=True)
        node_name = f"mini-format-core-{VERSION}.tgz"
        npm_tar(node, output / node_name)

        kit = stage / "toolkit"
        copy_file(wheel, kit / wheel.name)
        copy_file(output / node_name, kit / node_name)
        copy_tree(ROOT / "examples", kit / "examples")
        for name in DOCS:
            if (ROOT / name).is_file():
                copy_file(ROOT / name, kit / name)
        (kit / "INSTALL.txt").write_text(
            "mini-format " + VERSION + "\n\nPython >=3.9 (offline, no runtime dependencies):\n"
            f"  python -m pip install --no-index {wheel.name}\n"
            "  mini build examples/phones.json examples/phones-extra.json --prefix phone --out .mini\n\n"
            "Node >=22.6 (offline, no runtime dependencies):\n"
            f"  npm install ./{node_name}\n\n"
            "See BUILD_GUIDE.md / BUILD_GUIDE.es.md. The generated Python parser is standalone.\n"
            f"Software release {VERSION}; core SPEC {SPEC_VERSION}; generated domain profile mini-domain/1.\n", encoding="utf-8")
        zip_name = f"mini-format-{VERSION}.zip"
        source_name = f"mini-format-{VERSION}-source.zip"
        zip_tree(kit, output / zip_name, f"mini-format-{VERSION}")
        # Wheel construction may have emitted build metadata; the source archive
        # comes only from the explicit original-source allowlist above.
        clean_source = stage / "clean-source"
        copy_tree(source, clean_source)
        zip_tree(clean_source, output / source_name, f"mini-format-{VERSION}")

    names = [wheel.name, node_name, zip_name, source_name]
    manifest = {"version": VERSION, "spec": SPEC_VERSION, "domain_profile": "mini-domain/1", "files": []}
    for name in names:
        p = output / name
        manifest["files"].append({"name": name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS.txt").write_text("".join(f"{f['sha256']}  {f['name']}\n" for f in manifest["files"]), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    build(args.output.resolve())
