"""Empaquetado: las familias oficiales deben viajar dentro del paquete instalado."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import Registry  # noqa: E402
from minifmt import registry as registry_mod  # noqa: E402

try:
    import setuptools  # noqa: F401
    HAVE_SETUPTOOLS = True
except ImportError:  # pragma: no cover
    HAVE_SETUPTOOLS = False


class TestDefaultForksDir(unittest.TestCase):
    def test_source_checkout_uses_repository_forks(self):
        self.assertEqual(registry_mod.default_forks_dir().resolve(), (ROOT / "forks").resolve())
        self.assertEqual(len(Registry.load().contracts), len(list((ROOT / "forks").glob("*/contract.json"))))

    def test_missing_directory_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            Registry.load(ROOT / "no-such-forks-dir")


@unittest.skipUnless(HAVE_SETUPTOOLS, "setuptools not available")
class TestBuiltPackage(unittest.TestCase):
    """Simula una instalación: ``build_py`` a un directorio aislado y carga desde ahí."""

    def test_build_py_ships_forks_and_registry_loads_outside_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib = Path(tmp) / "lib"
            subprocess.run([sys.executable, "setup.py", "-q", "build_py", "-d", str(lib)],
                           cwd=ROOT, check=True, capture_output=True)
            shipped = sorted(p.parent.name for p in (lib / "minifmt" / "forks").glob("*/contract.json"))
            expected = sorted(p.parent.name for p in (ROOT / "forks").glob("*/contract.json"))
            self.assertEqual(shipped, expected)
            self.assertTrue((lib / "minifmt" / "forks" / "registry.json").is_file())
            self.assertTrue((lib / "minifmt" / "forks" / "a" / "fixtures" / "valid.mini").is_file())
            code = ("import minifmt, json; from minifmt import Registry, parse; "
                    "from minifmt.registry import DEFAULT_FORKS_DIR as D; r = Registry.load(); "
                    "t = (r.paths['a'] / 'fixtures' / 'valid.mini').read_text(encoding='utf-8'); "
                    "print(json.dumps([str(D), minifmt.__file__, len(r.contracts), len(parse(t, r.get('a')).records), len(r.check())]))")
            env = dict(os.environ, PYTHONPATH=str(lib))
            out = subprocess.run([sys.executable, "-c", code], cwd=tmp, env=env, check=True,
                                 capture_output=True, text=True).stdout
            import json
            forks_dir, init_file, n_contracts, n_records, n_errs = json.loads(out)
            self.assertTrue(Path(init_file).resolve().is_relative_to(lib.resolve()))
            self.assertEqual(Path(forks_dir).resolve(), (lib / "minifmt" / "forks").resolve())
            self.assertEqual(n_contracts, len(expected))
            self.assertEqual(n_records, 12)
            self.assertEqual(n_errs, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
