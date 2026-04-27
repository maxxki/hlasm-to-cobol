#!/usr/bin/env python3

"""
maxxki/plugins/instruction/compare.py
=======================================
Handles HLASM compare and test instructions.

Opcodes covered
---------------
Register compares:  CR, CLR, CGR, CLGR
Memory compares:    C, CL, CH, CLC, CLI, CLCL
Test under mask:    TM, TMH, TML

COBOL mapping strategy
-----------------------
HLASM comparisons set the condition code (CC) which is then tested by a
subsequent branch instruction (BC/BCR/BE/BNE/...).

We cannot know the branch context here, so we emit a comment-style
placeholder that preserves the operands and warns the reviewer that
an IF statement is needed.

Pattern emitted:
  *> COMPARE {r1} WITH {r2} [CC set — add IF/GO TO]

For TM (Test under Mask) we emit a BIT-test comment because there is
no direct COBOL equivalent.
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


class CompareHandler(IInstructionHandler):

    HANDLER_NAME = "CompareHandler"

    OPCODES = frozenset({
        # Register
        "CR", "CLR", "CGR", "CLGR",
        # Memory
        "C", "CL", "CH", "CLC", "CLI", "CLCL",
        # Test under mask
        "TM", "TMH", "TML",
    })

    _TEST_OPS    = frozenset({"TM", "TMH", "TML"})
    _CHAR_OPS    = frozenset({"CLC", "CLI", "CLCL"})

    def _convert(
        self,
        op:   str,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> ConversionResult:
        prefix = self._label_prefix(stmt)
        r1 = self._map_register(self._op(stmt, 0), ctx)  # Map register
        r2 = self._map_register(self._op(stmt, 1), ctx)  # Map register

        if op in self._TEST_OPS:
            cobol = (
                f"{prefix}"
                f"      *> TEST MASK {r2} AGAINST {r1} — "
                f"add IF (bit test) logic here."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.LOW,
                risk       = RiskLevel.HIGH,
                warnings   = [f"{op}: bit-mask test — no direct COBOL equivalent."],
            )

        if op in self._CHAR_OPS:
            cobol = (
                f"{prefix}"
                f"      *> COMPARE CHARACTERS {r1} WITH {r2} — "
                f"add IF statement here."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.MEDIUM,
                warnings   = [f"{op}: character compare — add IF/EVALUATE logic."],
            )

        # Numeric register/memory compare
        if not r1 or not r2:
            return self._todo(stmt, "Compare missing operands")

        ctx.last_compare_result = f"{r1} {r2}"  # Store operands for branch handler
        cobol = (
            f"{prefix}"
            f"      *> COMPARE {r1} WITH {r2} — condition code set."
        )
        return self._result(
            stmt, cobol,
            confidence = ConversionConfidence.MEDIUM,
            risk       = RiskLevel.MEDIUM,
            warnings   = [f"{op}: sets condition code — subsequent IF/GO TO will use this."],
        )
