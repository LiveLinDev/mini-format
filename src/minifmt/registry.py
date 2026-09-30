"""Fork registry: discovers contracts in ``forks/<prefix>/contract.json``.

The registry enforces the fork invariants that can be checked mechanically:
unique prefixes, valid contracts, and — when a contract declares a
``parent`` — that the child keeps the parent's fields (names, order, types)
and only appends new ones (invariants I3 and I4 of the forking protocol).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from .contract import Contract
from .errors import E_FORK, MiniError

PACKAGE_FORKS_DIR = Path(__file__).resolve().parent / "forks"
REPO_FORKS_DIR = Path(__file__).resolve().parent.parent.parent / "forks"


def default_forks_dir() -> Optional[Path]:
    """Use repository fixtures while developing; installed core has no families."""
    if (PACKAGE_FORKS_DIR / "registry.json").is_file():
        return PACKAGE_FORKS_DIR
    if (REPO_FORKS_DIR / "registry.json").is_file():
        return REPO_FORKS_DIR
    return None


DEFAULT_FORKS_DIR = default_forks_dir()


class Registry:
    def __init__(self, contracts: Optional[Dict[str, Contract]] = None):
        self.contracts: Dict[str, Contract] = contracts or {}
        self.paths: Dict[str, Path] = {}

    # ---------------------------------------------------------------- load
    @classmethod
    def load(cls, forks_dir: Path | str | None = None) -> "Registry":
        reg = cls()
        if forks_dir is None:
            forks_dir = DEFAULT_FORKS_DIR
        if forks_dir is None:
            return reg
        forks_dir = Path(forks_dir)
        if not forks_dir.is_dir():
            raise FileNotFoundError(f"forks directory not found: {forks_dir}")
        for cpath in sorted(forks_dir.glob("*/contract.json")):
            c = Contract.load(cpath)
            if c.prefix in reg.contracts:
                raise MiniError(E_FORK, 0, f"prefix '{c.prefix}' is registered twice ({cpath})")
            if cpath.parent.name != c.prefix:
                raise MiniError(E_FORK, 0, f"folder '{cpath.parent.name}' must be named after prefix '{c.prefix}'")
            reg.contracts[c.prefix] = c
            reg.paths[c.prefix] = cpath.parent
        return reg

    def add(self, contract: Contract) -> None:
        if contract.prefix in self.contracts:
            raise MiniError(E_FORK, 0, f"prefix '{contract.prefix}' already registered")
        self.contracts[contract.prefix] = contract

    def get(self, prefix: str) -> Contract:
        try:
            return self.contracts[prefix]
        except KeyError:
            raise MiniError(E_FORK, 0, f"unknown prefix '{prefix}'") from None

    def __contains__(self, prefix: str) -> bool:
        return prefix in self.contracts

    def __iter__(self) -> Iterator[Contract]:
        return iter(self.contracts.values())

    # ------------------------------------------------------------ checking
    def check(self) -> List[MiniError]:
        """Check every fork against its parent; returns the list of violations."""
        errs: List[MiniError] = []
        for c in self.contracts.values():
            if c.parent:
                if c.parent not in self.contracts:
                    errs.append(MiniError(E_FORK, 0, f"fork '{c.prefix}' declares unknown parent '{c.parent}'"))
                    continue
                errs.extend(c.check_fork_of(self.contracts[c.parent]))
        return errs

    def lineage(self, prefix: str) -> List[str]:
        out = [prefix]
        c = self.get(prefix)
        while c.parent:
            out.append(c.parent)
            c = self.get(c.parent)
        return out

    def to_index(self) -> List[dict]:
        return [{"prefix": c.prefix, "version": c.version, "name": c.name, "parent": c.parent,
                 "domain": c.domain, "arity": c.arity, "extensions": len(c.extensions),
                 "signature": c.signature()} for c in self.contracts.values()]

    def write_index(self, path: Path | str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_index(), fh, ensure_ascii=False, indent=2)
