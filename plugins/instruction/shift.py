#!/usr/bin/env python3

"""
maxxki/plugins/instruction/shift.py
=====================================
Handles HLASM shift instructions.

Opcodes covered
---------------
  SLL   Shift Left  Logical   (single register)
  SRL   Shift Right Logical
  SLA   Shift Left  Arithmetic
  SRA   Shift Right Arithmetic
  SLDL  Shift Left  Double Logical   (register pair)
  SRDL  Shift Right Double Logical
  SLDA  Shift Left  Double Arithmetic
  SRDA  Shift Right Double Arithmetic

COBOL mapping
-------------
Logical   left  shift by n  ≈  COMPUTE r = r * 2^n   (loses sign semantics)
Logical   right shift by n  ≈  COMPUTE r = r / 2^n   (unsigned — loses bits)
Arithmetic shifts preserve sign — same COMPUTE but with caveat.
Double-register pair shifts have no COMPUTE equivalent → TODO stub.

All shift results are MEDIUM confidence, LOW-MEDIUM risk.
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

_DOUBLE_OPS = frozenset({"SLDL", "SRDL", "SLDA", "SRDA"})
_LEFT_OPS   = frozenset({"SLL", "SLA", "SLDL", "SLDA"})


class ShiftHandler(IInstructionHandler):

    HANDLER_NAME = "ShiftHandler"

    OPCODES = frozenset({
        "SLL", "SRL", "SLA", "SRA",
        "SLDL", "SRDL", "SLDA", "SRDA",
    })

    def _convert(
        self,
        op:   str,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> ConversionResult:
        prefix = self._label_prefix(stmt)
        reg    = self._map_register(self._op(stmt, 0), ctx)  # Map register
        amount = self._op(stmt, 1) or "?"   # shift amount (immediate or base-disp)

        if op in _DOUBLE_OPS:
            cobol = (
                f"{prefix}"
                f"      *> {op} {reg},{amount} — double-register pair shift.\n"
                f"      *> TODO: Implement manual 64-bit shift routine (e.g., using a "
                f"group variable that REDEFINES two 32-bit registers)."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.LOW,
                risk       = RiskLevel.HIGH,
                warnings   = [f"{op}: double-register pair shift — manual conversion required."],
            )

        direction = "left" if op in _LEFT_OPS else "right"
        operator  = "*" if direction == "left" else "/"

        # Try to use a literal power-of-two if amount is a plain integer
        try:
            n = int(amount.split("(")[0])   # e.g. "3(0)" → 3
            factor = 2 ** n
            compute = f"COMPUTE {reg} = {reg} {operator} {factor}."
        except (ValueError, TypeError):
            compute = f"*> COMPUTE {reg} = {reg} {operator} 2**{amount}  *> shift {direction}"

        cobol = f"{prefix}       {compute}"
        return self._result(
            stmt, cobol,
            confidence = ConversionConfidence.MEDIUM,
            risk       = RiskLevel.LOW,
            warnings   = [
                f"{op}: shift {direction} by {amount} — "
                "COMPUTE approximation loses bit-precision; verify overflow behaviour."
            ],
        )
