"""AI-facing helpers for .mini: selective repair and generation adapters.

>>> from minifmt.ai import repair_request, merge_repair
>>> req = repair_request(model_answer, contract, "es")
>>> if req.needed:
...     answer = adapter.generate(req.system, req.user, max_tokens=req.max_tokens_hint * 2, temperature=0)
...     merged = merge_repair(model_answer, answer["text"], contract, req)
"""
from __future__ import annotations

from .repair import (MergeResult, RepairItem, RepairRequest, extract_document, invalid_items, lenient_parse,
                     merge_repair, repair_request)

__all__ = ["repair_request", "merge_repair", "extract_document", "invalid_items", "lenient_parse",
           "RepairRequest", "RepairItem", "MergeResult"]
