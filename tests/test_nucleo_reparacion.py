"""Defectos de reparación y de bloque de instrucciones (auditoría V5, D-3 y D-6).

Las expectativas están escritas a mano desde SPEC §6 («un campo `unique` no puede repetir su valor»)
y §9, no calculadas con el código bajo prueba.
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import Contract, Registry, parse, spec_block  # noqa: E402
from minifmt.ai import merge_repair, repair_request  # noqa: E402

CLS = Registry.load(ROOT / "forks").get("cls")
TAIL = "|question*,feedback,bug,request,praise,other|0.9|"


def rec(i, text="texto"):
    return f"m{i}|{text}{TAIL}"


ROTA = "m2|registro roto sin campos suficientes"
DOC = "\n".join(["cls|n=3|k=6", rec(1), ROTA, rec(3, "tercero")])  # la línea 3 es la inválida


def merge(answer, doc=DOC):
    return merge_repair(doc, answer, CLS, repair_request(doc, CLS, "es"))


class UniqueValuesSurviveRepair(unittest.TestCase):
    """D-3: una corrección no puede quitarle a otro registro válido el valor de su campo `unique`."""

    def test_the_request_only_asks_for_the_broken_line(self):
        req = repair_request(DOC, CLS, "es")
        self.assertEqual([it.line for it in req.items], [3])

    def test_correction_repeating_a_later_valid_id_is_left_unresolved(self):
        m = merge("cls|n=1\n" + rec(3, "corregido"))
        self.assertEqual(m.replaced, [])
        self.assertEqual(m.unresolved, [3])
        self.assertEqual(m.text, DOC, "el documento no cambia: la línea original queda donde estaba")
        self.assertEqual([r["id"] for r in m.document.records], ["m1", "m3"], "ningún registro válido se pierde")
        self.assertTrue(any("unique" in n for n in m.notes))

    def test_correction_repeating_an_earlier_valid_id_is_left_unresolved(self):
        m = merge("cls|n=1\n" + rec(1, "corregido"))
        self.assertEqual((m.replaced, m.unresolved), ([], [3]))
        self.assertEqual(m.text, DOC)

    def test_a_new_id_is_accepted(self):
        m = merge("cls|n=1\n" + rec(9, "corregido"))
        self.assertEqual((m.replaced, m.unresolved), ([3], []))
        self.assertTrue(m.ok)
        self.assertEqual([r["id"] for r in m.document.records], ["m1", "m9", "m3"])

    def test_the_corrected_line_may_keep_its_own_id(self):
        # el id de la línea rota (m2) no pertenece a ningún registro válido
        m = merge("cls|n=1\n" + rec(2, "corregido"))
        self.assertEqual((m.replaced, m.unresolved), ([3], []))
        self.assertTrue(m.ok)

    def test_whole_reply_preserves_the_valid_records(self):
        full = DOC.replace(ROTA, rec(2, "corregido"))
        accepted = merge(full)
        self.assertTrue(accepted.ok)
        self.assertEqual((accepted.text, accepted.replaced, accepted.dropped), (full, [3], []))
        for ambiguous in (full.replace(rec(1), rec(1, "otro")), full.replace("n=3", "n=4")):
            refused = merge(ambiguous)
            self.assertFalse(refused.ok)
            self.assertEqual((refused.text, refused.replaced, refused.unresolved), (DOC, [], [3]))

    def test_whole_reply_requires_a_terminator_on_the_last_corrected_line(self):
        doc = "\n".join(["cls|n=2|k=6", rec(1), ROTA])
        full = doc.replace(ROTA, rec(2, "corregido"))
        self.assertEqual(merge(full, doc).unresolved, [3])
        self.assertTrue(merge(full + "\n", doc).ok)

    def test_two_corrections_cannot_claim_the_same_new_id(self):
        doc = "\n".join(["cls|n=4|k=6", rec(1), ROTA, "otra línea rota", rec(4)])
        m = merge_repair(doc, "cls|n=2\n" + rec(9, "uno") + "\n" + rec(9, "dos"), CLS, repair_request(doc, CLS, "es"))
        self.assertEqual((m.replaced, m.unresolved), ([3], [4]))
        self.assertEqual([r["id"] for r in m.document.records], ["m1", "m9", "m4"])

    def test_invariant_valid_records_are_never_lost_by_a_merge(self):
        """Propiedad con semilla fija: sea cual sea la respuesta, las líneas válidas del original siguen ahí."""
        rng = random.Random(20260930)
        pool = [rec(i, f"t{j}") for i in range(1, 8) for j in range(2)] + ["-", "basura", "m1|x"]
        for _ in range(300):
            ids = rng.sample(range(1, 9), rng.randint(3, 6))
            lines = [rec(i) for i in ids]
            broken = rng.sample(range(len(lines)), rng.randint(1, 2))
            for b in broken:
                lines[b] = "roto" + str(b)
            doc = "\n".join([f"cls|n={len(lines)}|k=6"] + lines)
            req = repair_request(doc, CLS, "es")
            answer = "\n".join([f"cls|n={len(req.items)}"] + [rng.choice(pool) for _ in req.items])
            m = merge_repair(doc, answer, CLS, req)
            originally_valid = {lines[i] for i in range(len(lines)) if i not in broken}
            kept = set(m.text.split("\n"))
            self.assertTrue(originally_valid <= kept, (doc, answer, m.text))
            valid_ids = {(f"m{ids[i]}", "texto") for i in range(len(lines)) if i not in broken}
            ids_after = {(r["id"], r["text"]) for r in m.document.records}
            self.assertTrue(valid_ids <= ids_after, ("un registro válido salió del documento", doc, answer, m.text))


class ListBoundZeroInPrompt(unittest.TestCase):
    """D-6: `max: 0` se describe como 0, no como «sin límite»."""

    def test_max_zero_is_not_infinity(self):
        c = Contract.from_dict({"prefix": "z", "core": [
            {"name": "id", "type": "str"}, {"name": "tags", "type": "list", "item": "str", "optional": True, "min": 0, "max": 0}]})
        en, es = spec_block(c, "en"), spec_block(c, "es")
        self.assertIn("0 to 0 elements", en)
        self.assertIn("entre 0 y 0 elementos", es)
        self.assertNotIn("∞", en + es)

    def test_absent_max_is_still_unbounded(self):
        c = Contract.from_dict({"prefix": "z", "core": [
            {"name": "id", "type": "str"}, {"name": "tags", "type": "list", "item": "str", "min": 1}]})
        self.assertIn("1 to ∞ elements", spec_block(c, "en"))


class EqualRowsSurviveRepair(unittest.TestCase):
    def test_repeated_rows_follow_the_contract(self):
        for extensions in ([], [{"name": "tag", "type": "str", "optional": True, "unique": True}]):
            contract = Contract.from_dict({
                "prefix": "event",
                "header": {"required": ["n"], "keys": {"n": {"type": "int"}}},
                "core": [{"name": "text", "type": "str"}],
                "extensions": extensions,
            })
            for kept in ("mismo evento", "incompleto|con|campos|sobrantes"):
                broken = "\n".join(["event|n=2", kept, "incompleto|con|demasiados|campos"])
                count = 1 if kept == "mismo evento" else 2
                answer = "\n".join([f"event|n={count}"] + ["mismo evento"] * count)
                merged = merge_repair(broken, answer, contract)
                self.assertEqual(merged.text, "event|n=2\nmismo evento\nmismo evento")
                self.assertTrue(merged.ok)
                self.assertEqual(merged.dropped, [])


if __name__ == "__main__":
    unittest.main()
