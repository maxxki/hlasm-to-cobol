#!/usr/bin/env python3

"""
maxxki/plugins/instruction/arithmetic.py
=========================================
Handles HLASM integer arithmetic instructions.

Opcodes covered
---------------
Add:       A, AR, AH, AHI, AL, ALR, ALFI
Subtract:  S, SR, SH, SHI, SL, SLR, SLFI
Multiply:  M, MR, MH, MHI, MS, MSR
Divide:    D, DR

COBOL mapping
-------------
  ADD src TO tgt           for A/AR/AH/AHI variants
  SUBTRACT src FROM tgt    for S/SR/SH variants
  MULTIPLY — COMPUTE tgt = tgt * src
  DIVIDE   — COMPUTE tgt = tgt / src  (integer divide loses remainder)

Notes on M/MR and D/DR
-----------------------
In HLASM, M Rx,mem multiplies the even-odd register pair (Rx, Rx+1).
This cannot be faithfully expressed as a single COMPUTE statement.
We emit a COMPUTE with a warning + HIGH risk so the reviewer knows
to check register pairing.
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


class ArithmeticHandler(IInstructionHandler):

    HANDLER_NAME = "ArithmeticHandler"

    OPCODES = frozenset({
        # Add
        "A", "AR", "AH", "AHI", "AL", "ALR", "ALFI",
        # Subtract
        "S", "SR", "SH", "SHI", "SL", "SLR", "SLFI",
        # Multiply
        "M", "MR", "MH", "MHI", "MS", "MSR",
        # Divide
        "D", "DR",
    })

    # Map opcode → (verb, is_complex)
    _ADD_OPS = frozenset({"A", "AR", "AH", "AHI", "AL", "ALR", "ALFI"})
    _SUB_OPS = frozenset({"S", "SR", "SH", "SHI", "SL", "SLR", "SLFI"})
    _MUL_OPS = frozenset({"M", "MR", "MH", "MHI", "MS", "MSR"})
    _DIV_OPS = frozenset({"D", "DR"})

    def _convert(
        self,
        op:   str,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> ConversionResult:
        prefix = self._label_prefix(stmt)
        r1 = self._map_register(self._op(stmt, 0), ctx)  # Map register
        r2 = self._map_register(self._op(stmt, 1), ctx)  # Map register

        if op in self._ADD_OPS:
            cobol = f"{prefix}       ADD {r2} TO {r1}."
            return self._result(stmt, cobol)

        if op in self._SUB_OPS:
            cobol = f"{prefix}       SUBTRACT {r2} FROM {r1}."
            return self._result(stmt, cobol)

        if op in self._MUL_OPS:
            # Register-pair semantics: warn but produce usable stub
            cobol = f"{prefix}       COMPUTE {r1} = {r1} * {r2}."
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.MEDIUM,
                warnings   = [
                    f"{op}: HLASM uses even/odd register pair — "
                    "verify register pairing before using this output."
                ],
            )

        if op in self._DIV_OPS:
            cobol = f"{prefix}       COMPUTE {r1} = {r1} / {r2}."
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.MEDIUM,
                warnings   = [
                    f"{op}: HLASM stores quotient/remainder in register pair — "
                    "remainder is lost in this COBOL mapping."
                ],
            )

        return self._todo(stmt)
