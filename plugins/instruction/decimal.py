#!/usr/bin/env python3

"""
maxxki/plugins/instruction/decimal.py
=======================================
Handles HLASM packed-decimal and conversion instructions.

Opcodes covered
---------------
Packed decimal arithmetic:
  AP   Add Packed
  SP   Subtract Packed
  MP   Multiply Packed
  DP   Divide Packed
  ZAP  Zero and Add Packed
  CP   Compare Packed

Conversion:
  CVB  Convert to Binary (packed decimal → integer register)
  CVD  Convert to Decimal (integer register → packed decimal)
  PACK Pack (zoned → packed)
  UNPK Unpack (packed → zoned)

COBOL mapping
-------------
Packed decimal ops map naturally to COBOL COMP-3 arithmetic.
CVB/CVD map to MOVE between COMP-3 and COMP fields.
PACK/UNPK have no single-statement equivalent — MOVE between
PIC S9 and PIC S9 COMP-3 fields effectively re-packs the value.
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


class DecimalHandler(IInstructionHandler):

    HANDLER_NAME = "DecimalHandler"

    OPCODES = frozenset({
        "AP", "SP", "MP", "DP", "ZAP", "CP",
        "CVB", "CVD",
        "PACK", "UNPK",
    })

    def _convert(
        self,
        op:   str,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> ConversionResult:
        prefix = self._label_prefix(stmt)
        r1 = self._map_register(self._op(stmt, 0), ctx)  # Map register
        r2 = self._map_register(self._op(stmt, 1), ctx)  # Map register

        # ── Packed decimal arithmetic ─────────────────────────────────────────
        if op == "AP":
            cobol = f"{prefix}       ADD {r2} TO {r1}."
            return self._result(
                stmt, cobol,
                warnings=["AP: ensure both fields are PIC S9(...) COMP-3."],
            )

        if op == "SP":
            cobol = f"{prefix}       SUBTRACT {r2} FROM {r1}."
            return self._result(
                stmt, cobol,
                warnings=["SP: ensure both fields are PIC S9(...) COMP-3."],
            )

        if op == "MP":
            cobol = f"{prefix}       MULTIPLY {r2} BY {r1}."
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.LOW,
                warnings   = ["MP: verify result field is large enough for product."],
            )

        if op == "DP":
            cobol = f"{prefix}       DIVIDE {r2} INTO {r1}."
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.MEDIUM,
                warnings   = [
                    "DP: HLASM DP stores quotient+remainder in one field — "
                    "COBOL DIVIDE GIVING REMAINDER syntax may be needed."
                ],
            )

        if op == "ZAP":
            # Zero and Add: dest = 0 + src  (effectively MOVE with sign)
            cobol = f"{prefix}       MOVE {r2} TO {r1}."
            return self._result(
                stmt, cobol,
                warnings=["ZAP: treated as MOVE — verify sign handling."],
            )

        if op == "CP":
            cobol = (
                f"{prefix}"
                f"      *> COMPARE PACKED {r1} WITH {r2} — add IF statement here."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.MEDIUM,
                warnings   = ["CP: sets condition code — add IF/EVALUATE logic."],
            )

        # ── Conversion ────────────────────────────────────────────────────────
        if op == "CVB":
            # packed decimal → binary integer
            cobol = f"{prefix}       MOVE {r2} TO {r1}."
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.LOW,
                warnings   = [
                    "CVB: source must be PIC S9(...) COMP-3, "
                    "target PIC S9(...) COMP."
                ],
            )

        if op == "CVD":
            # binary integer → packed decimal
            cobol = f"{prefix}       MOVE {r1} TO {r2}."
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.LOW,
                warnings   = [
                    "CVD: source PIC S9(...) COMP, "
                    "target must be PIC S9(...) COMP-3."
                ],
            )

        if op == "PACK":
            cobol = f"{prefix}       MOVE {r2} TO {r1}."
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.LOW,
                warnings   = [
                    "PACK: target should be PIC S9(...) COMP-3, "
                    "source PIC S9(...)."
                ],
            )

        if op == "UNPK":
            cobol = f"{prefix}       MOVE {r1} TO {r2}."
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.LOW,
                warnings   = [
                    "UNPK: source PIC S9(...) COMP-3, "
                    "target PIC S9(...) DISPLAY."
                ],
            )

        return self._todo(stmt)
