#!/usr/bin/env python3

"""
maxxki/plugins/instruction/fallback.py
========================================
Catch-all handler — always last in the handler chain.

Any opcode that no other handler claimed lands here.
We emit a structured TODO comment so the output is still valid COBOL
(comment lines) and reviewers know exactly which original instruction
needs manual attention.

This handler's OPCODES is intentionally empty — it overrides handle()
to always fire regardless of opcode.
"""
from __future__ import annotations

from typing import Optional

from .base import IInstructionHandler
from core.types import (
    ConversionConfidence,
    ConversionContext,
    ConversionResult,
    ParsedStatement,
    RiskLevel,
)


class FallbackHandler(IInstructionHandler):

    HANDLER_NAME = "FallbackHandler"
    OPCODES      = frozenset()   # not used — we override handle()

    def handle(
        self,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> Optional[ConversionResult]:
        """Always fires — no opcode check."""
        return self._convert((stmt.operation or "UNKNOWN").upper(), stmt, ctx)

    def _convert(
        self,
        op:   str,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> ConversionResult:
        prefix = self._label_prefix(stmt)
        cobol  = f"{prefix}      *> TODO [UNHANDLED {op}]: {stmt.raw_text}"
        return ConversionResult(
            original_statement  = stmt.raw_text,
            converted_statement = cobol,
            statement_type      = stmt.statement_type,
            confidence          = ConversionConfidence.UNKNOWN,
            risk_level          = RiskLevel.HIGH,
            warnings            = [
                f"Opcode '{op}' has no handler — manual conversion required."
            ],
            source              = stmt,
        )
