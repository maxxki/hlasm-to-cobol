#!/usr/bin/env python3

"""
maxxki/plugins/instruction/boolean.py
=======================================
Handles HLASM boolean / bitwise instructions.

Opcodes covered
---------------
AND:  N, NR, NC, NI
OR:   O, OR, OC, OI
XOR:  X, XR, XC, XI

COBOL has no native bitwise operators.
We emit a comment stub with the operation preserved for the reviewer.
Confidence is LOW, risk HIGH for all — these need manual conversion.
"""
from __future__ import annotations

from .base import IInstructionHandler
from core.types import (
    ConversionConfidence,
    ConversionContext,
    ConversionResult,
    ParsedStatement,
    RiskLevel,
)

_OP_NAME = {
    "N": "AND", "NR": "AND", "NC": "AND", "NI": "AND",
    "O": "OR",  "OR": "OR",  "OC": "OR",  "OI": "OR",
    "X": "XOR", "XR": "XOR", "XC": "XOR", "XI": "XOR",
}


class BooleanHandler(IInstructionHandler):

    HANDLER_NAME = "BooleanHandler"

    OPCODES = frozenset(_OP_NAME.keys())

    def _convert(
        self,
        op:   str,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> ConversionResult:
        prefix   = self._label_prefix(stmt)
        verb     = _OP_NAME.get(op, op)
        r1       = self._map_register(self._op(stmt, 0), ctx)  # Map register
        r2       = self._map_register(self._op(stmt, 1), ctx)  # Map register

        cobol = (
            f"{prefix}"
            f"      *> {verb}: {r1} {op} {r2} — "
            f"no direct COBOL bitwise operator; use CALL or custom routine."
        )
        return self._result(
            stmt, cobol,
            confidence = ConversionConfidence.LOW,
            risk       = RiskLevel.HIGH,
            warnings   = [
                f"{op} ({verb}): COBOL has no native bitwise ops — "
                "implement via CALL to a utility or rewrite logic."
            ],
        )
