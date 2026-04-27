#!/usr/bin/env python3

"""
maxxki/plugins/instruction/move.py
====================================
Handles HLASM memory-to-memory move instructions.

Opcodes covered
---------------
  MVC   Move Characters
  MVCL  Move Characters Long
  MVI   Move Immediate (one byte)
  MVN   Move Numerics
  MVZ   Move Zones
  MVCIN Move Characters Inverse

COBOL mapping
-------------
  MVC  dest,src  →  MOVE src TO dest
  MVI  addr,byte →  MOVE byte TO addr   (immediate byte value)
  MVCL           →  MOVE with length — stub with warning
  MVN / MVZ      →  no direct equivalent — TODO stub
  MVCIN          →  MOVE with REVERSE — TODO stub
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


class MoveHandler(IInstructionHandler):

    HANDLER_NAME = "MoveHandler"

    OPCODES = frozenset({
        "MVC", "MVCL", "MVI", "MVN", "MVZ", "MVCIN",
    })

    def _convert(
        self,
        op:   str,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> ConversionResult:
        prefix = self._label_prefix(stmt)
        dest = self._map_register(self._op(stmt, 0), ctx)  # Map register
        src  = self._map_register(self._op(stmt, 1), ctx)  # Map register

        if op == "MVC":
            # dest operand often has length: FIELD(10)
            # strip length spec for readability — reviewer must verify
            dest_clean = dest.split("(")[0] if "(" in dest else dest
            src_clean  = src.split("(")[0]  if "(" in src  else src
            cobol = f"{prefix}       MOVE {src_clean} TO {dest_clean}."
            warnings = []
            if "(" in dest or "(" in src:
                warnings.append(
                    "MVC: length specifier detected — verify field lengths match."
                )
            return self._result(stmt, cobol, warnings=warnings)

        if op == "MVI":
            # MVI addr,X'41'  or  MVI addr,C' '
            cobol = f"{prefix}       MOVE {src} TO {dest}."
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.LOW,
                warnings   = ["MVI: immediate byte — verify COBOL field type (PIC X)."],
            )

        if op == "MVCL":
            cobol = (
                f"{prefix}"
                f"      *> MVCL {dest},{src} — long move, add MOVE with length check."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.LOW,
                risk       = RiskLevel.HIGH,
                warnings   = ["MVCL: variable-length move — requires manual conversion."],
            )

        if op in ("MVN", "MVZ"):
            cobol = (
                f"{prefix}"
                f"      *> {op} {dest},{src} — zone/numeric overlay.\n"
                f"      *> TODO: Implement manual byte-level manipulation using "
                f"REDEFINES or bitwise/arithmetic logic to overlay numeric/zone bits."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.LOW,
                risk       = RiskLevel.HIGH,
                warnings   = [f"{op}: zone/numeric overlay — no direct COBOL equivalent."],
            )

        if op == "MVCIN":
            cobol = (
                f"{prefix}"
                f"      *> MVCIN {dest},{src} — reverse copy, consider FUNCTION REVERSE."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.LOW,
                risk       = RiskLevel.MEDIUM,
                warnings   = ["MVCIN: consider MOVE FUNCTION REVERSE(src) TO dest."],
            )

        return self._todo(stmt)
