#!/usr/bin/env python3

"""
maxxki/plugins/instruction/loop_control.py
==================================================

Handles Assembler loop control instructions.
"""
from __future__ import annotations

import logging # Added for _log
from typing import Optional # Added Optional import

from core.conversion_context import ConversionContext
from core.types import ConversionResult, ParsedStatement, RiskLevel, ConversionConfidence
from plugins.instruction.base import IInstructionHandler

_log = logging.getLogger(__name__) # Initialize logger


class LoopControlPlugin(IInstructionHandler):
    """
    Handles Assembler loop control instructions like BCT, BCTR, BXH, BXLE.
    """

    HANDLER_NAME = "LoopControlHandler"
    OPCODES = frozenset({"BCT", "BCTR", "BXH", "BXLE"})

    def __init__(self, context: ConversionContext):
        super().__init__(context)

    def _convert(self, op: str, stmt: ParsedStatement, ctx: ConversionContext) -> Optional[ConversionResult]:
        """Converts loop control instructions to COBOL."""
        cobol_code = ""
        risk = RiskLevel.NONE
        confidence = ConversionConfidence.HIGH
        warnings = []

        prefix = self._label_prefix(stmt)

        if op == "BCT":
            reg_operand = self._op(stmt, 0)
            target_operand = self._op(stmt, 1)

            cobol_reg_var = ctx.get_cobol_var_for_register(reg_operand)
            # Assuming get_cobol_label_for_operand exists or we directly use target_operand as a label.
            # For now, let's assume target_operand IS the label for BCT.
            target_label = target_operand # Direct use as label

            if not cobol_reg_var:
                return self._todo(stmt, f"BCT: Register {reg_operand} not mapped.")
            # No need to check for target_label if it's directly from operand

            cobol_code = f"{prefix}            SUBTRACT 1 FROM {cobol_reg_var}.
"
            cobol_code += f"            IF {cobol_reg_var} NOT = ZERO
"
            cobol_code += f"                GO TO {target_label}."

        elif op == "BCTR":
            reg_for_count = self._op(stmt, 0)
            reg_for_target = self._op(stmt, 1)

            cobol_count_var = ctx.get_cobol_var_for_register(reg_for_count)
            cobol_target_label = ctx.get_cobol_label_from_register(reg_for_target)

            if not cobol_count_var:
                return self._todo(stmt, f"BCTR: Count register {reg_for_count} not mapped.")

            if not cobol_target_label:
                # If the target register doesn't directly map to a known label, generate one
                # This is a simplification; proper handling might require more context.
                cobol_target_label = ctx.generate_cobol_label(f"BCTR_TARGET_{reg_for_count}")
                ctx.add_register_label_mapping(reg_for_target, cobol_target_label) # Record this mapping
                _log.warning("BCTR target register '%s' for instruction '%s' not directly mapped to a label. Generated placeholder: %s.", reg_for_target, stmt.raw_text, cobol_target_label)
                warnings.append(f"BCTR target register '{reg_for_target}' not directly mapped to a label.")
                risk = RiskLevel.MEDIUM

            cobol_code = f"{prefix}            SUBTRACT 1 FROM {cobol_count_var}.
"
            cobol_code += f"            IF {cobol_count_var} NOT = ZERO
"
            cobol_code += f"                GO TO {cobol_target_label}."

        elif op in ("BXH", "BXLE"):
            # These are more complex as they involve index registers and base addresses.
            # They will require a more sophisticated analysis of addressability and iteration.
            return self._todo(stmt, f"{op} requires complex index/addressing analysis")

        if cobol_code:
            return self._result(stmt, cobol_code, confidence=confidence, risk=risk, warnings=warnings)

        return None # Should not happen if op is in OPCODES, but safety first
