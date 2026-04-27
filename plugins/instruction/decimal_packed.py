#!/usr/bin/env python3

"""
maxxki/plugins/instruction/decimal_packed.py
=====================================================

Handles Assembler instructions related to Packed Decimal (COMP-3) and binary conversions.
"""
from __future__ import annotations

from core.conversion_context import ConversionContext
from core.types import Instruction, COBOLStatement, ConversionResult, ParsedStatement, RiskLevel, ConversionConfidence
from plugins.instruction.base import IInstructionHandler


class DecimalPackedPlugin(IInstructionHandler):
    """
    Handles Assembler instructions for packed decimal (COMP-3) and binary conversions.
    """

    HANDLER_NAME = "DecimalPackedHandler"
    OPCODES = frozenset({"PACK", "UNPK", "CVB", "CVD"})

    def __init__(self, context: ConversionContext):
        super().__init__(context)

    def _convert(self, op: str, stmt: ParsedStatement, ctx: ConversionContext) -> Optional[ConversionResult]:
        """Converts PACK, UNPK, CVB, CVD instructions to COBOL."""
        cobol_code = ""
        risk = RiskLevel.NONE
        confidence = ConversionConfidence.HIGH
        warnings = []

        prefix = self._label_prefix(stmt)

        if op == "PACK":
            target_operand = self._op(stmt, 0)
            source_operand = self._op(stmt, 1)

            # In COBOL, PACK is often a MOVE if data types align.
            # Need to ensure that target_operand and source_operand are correctly defined
            # with packed/zoned formats respectively. This plugin doesn't do that level of type checking.
            cobol_code = f"{prefix}            MOVE {source_operand} TO {target_operand}."

        elif op == "UNPK":
            target_operand = self._op(stmt, 0)
            source_operand = self._op(stmt, 1)

            # Similar to PACK, UNPK is often a MOVE in COBOL.
            cobol_code = f"{prefix}            MOVE {source_operand} TO {target_operand}."

        elif op == "CVB": # Convert to Binary
            reg_operand = self._op(stmt, 0)
            decimal_area_operand = self._op(stmt, 1)

            cobol_reg_var = ctx.get_cobol_var_for_register(reg_operand)
            if not cobol_reg_var:
                return self._todo(stmt, f"CVB: Register {reg_operand} not mapped.")

            # COBOL doesn't have a direct 'convert packed to binary register' op.
            # This is usually a MOVE to a binary field, then potentially used.
            cobol_code = f"{prefix}            * NOTE: CVB conversion from packed decimal {decimal_area_operand} to binary {cobol_reg_var}.
"
            cobol_code += f"            MOVE {decimal_area_operand} TO {cobol_reg_var}.
"
            cobol_code += f"            * Add logic here if direct binary conversion is needed and not handled by MOVE."
            risk = RiskLevel.MEDIUM
            warnings.append(f"CVB: Manual review of packed to binary conversion needed for {decimal_area_operand} to {cobol_reg_var}.")

        elif op == "CVD": # Convert to Decimal
            reg_operand = self._op(stmt, 0)
            decimal_area_operand = self._op(stmt, 1)

            cobol_reg_var = ctx.get_cobol_var_for_register(reg_operand)
            if not cobol_reg_var:
                return self._todo(stmt, f"CVD: Register {reg_operand} not mapped.")

            # Similar to CVB, this is usually a MOVE operation in COBOL.
            cobol_code = f"{prefix}            * NOTE: CVD conversion from binary {cobol_reg_var} to packed decimal {decimal_area_operand}.
"
            cobol_code += f"            MOVE {cobol_reg_var} TO {decimal_area_operand}.
"
            cobol_code += f"            * Add logic here if direct packed decimal conversion is needed."
            risk = RiskLevel.MEDIUM
            warnings.append(f"CVD: Manual review of binary to packed decimal conversion needed for {cobol_reg_var} to {decimal_area_operand}.")

        if cobol_code:
            return self._result(stmt, cobol_code, confidence=confidence, risk=risk, warnings=warnings)

        return None # Should not happen if op is in OPCODES

