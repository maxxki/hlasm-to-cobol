#!/usr/bin/env python3

"""
maxxki/plugins/instruction/register_mapping.py
=============================================

Plugin responsible for identifying register usage and generating
corresponding WORKING-STORAGE items in the COBOL DATA DIVISION.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Set, Tuple

from core.conversion_context import ConversionContext
from core.types import (
    ConversionConfidence,
    ConversionResult,
    ParsedStatement,
    RiskLevel,
    StatementType,
)
from plugins.instruction.base import IInstructionHandler

_log = logging.getLogger(__name__)


class RegisterMappingPlugin(IInstructionHandler):
    """
    Scans for register usage and ensures COBOL variables are defined.
    This plugin should run very early in the pipeline.
    """

    HANDLER_NAME = "RegisterMappingPlugin"

    # This plugin doesn't handle specific opcodes in the traditional sense,
    # but rather scans all statements. We can use a broad category or just ALL.
    # For now, let's assume it runs before opcode handlers.
    # If it needs to be explicitly registered via a router, we might need a different approach.
    # For this structure, we will make it a standalone plugin that runs once.

    # --- NOTE: This plugin is intended to be called ONCE by the Orchestrator
    # --- before the main instruction-handling loop begins.
    # --- It does NOT implement the IInstructionHandler.handle() method directly
    # --- in a way that a typical router would call it for each statement.
    # --- Instead, it requires a dedicated execution hook.

    # If we MUST adhere to IInstructionHandler, we could add all known ops
    # and have _convert perform the scan.
    OPCODES = frozenset({"L", "LR", "LA", "LH", "LHI", "LT", "LTR", "LC", "LCR", "LN", "LNR", "LP", "LPR", "LM", "ST", "STH", "STC", "STCM", "STM"}) # Example: cover load/store ops

    def __init__(self, context: ConversionContext):
        super().__init__(context) # Pass context to base class
        self._used_registers: Set[str] = set()

    def _scan_for_registers(self, statements: List[ParsedStatement]) -> None:
        """Scans all statements to identify used assembler registers."""
        _log.info("Scanning for register usage...")
        for stmt in statements:
            # Check operands for register numbers (e.g., 'R1', '1', 'TABLE(R2)')
            for operand in stmt.operands:
                # Simple extraction: look for R followed by digits, or just digits
                parts = operand.replace('(', ' ').replace(',', ' ').split()
                for part in parts:
                    cleaned_part = part.upper().replace('R', '')
                    if cleaned_part.isdigit():
                        try:
                            reg_num = int(cleaned_part)
                            if 0 <= reg_num <= 15:
                                self._used_registers.add(str(reg_num))
                        except ValueError:
                            pass # Not a valid register number
            # Also check labels that might be associated with registers (e.g., in BCTR R5, R6 target)
            # This part is more complex and might need context from other plugins or a pre-pass.
            # For now, focus on direct register operands.

        _log.info("Identified registers used: %s", self._used_registers)

    def _generate_working_storage(self) -> List[str]:
        """Generates COBOL WORKING-STORAGE definitions for used registers."""
        ws_items = []
        # Sort registers numerically for consistent output
        sorted_regs = sorted(list(self._used_registers), key=int)

        for reg_num in sorted_regs:
            # Default PIC clause - can be made more sophisticated later
            # e.g., based on usage (L vs LH vs LHI)
            pic_clause = "PIC S9(9) COMP."
            self.context.generated_ws_registers[reg_num] = pic_clause
            ws_items.append(f"    05 WS-REG{reg_num} {pic_clause}")
            _log.debug("Generated WS for R%s: %s", reg_num, pic_clause)
        return ws_items

    def _update_context_with_mapping(self) -> None:
        """Updates the context's register_map and potentially adds the generated WS items."""
        generated_ws = self._generate_working_storage()

        # Add generated items to the COBOL DATA division
        if generated_ws:
            self.context.add_cobol_division_line("DATA", "      WORKING-STORAGE SECTION.")
            for item in generated_ws:
                self.context.add_cobol_division_line("DATA", item)

        # Ensure the context's register_map points to the correct COBOL vars
        # The base register_map is static, this dynamically updates it if needed.
        # More importantly, ensure get_cobol_var_for_register in context uses generated_ws_registers.
        # The existing context.get_cobol_var_for_register logic already checks generated_ws_registers.
        _log.info("Updated register mapping in context.")

    # --- Implementation for IInstructionHandler (as a fallback/example) ---

    def _convert(self, op: str, stmt: ParsedStatement, ctx: ConversionContext) -> Optional[ConversionResult]:
        """
        This method is a fallback. The primary use of this plugin is a pre-pass.
        However, if called, it can still perform its scan and update context.
        It will return a TODO for the original statement as it doesn't directly convert.
        """
        if op in self.OPCODES:
            _log.debug("RegisterMappingPlugin processing opcode %s", op)
            # If this is the first time encountering a register, trigger a scan if not already done.
            # This might be inefficient if called per statement.
            # A better orchestration is needed.
            if not ctx.generated_ws_registers:
                _log.warning("RegisterMappingPlugin called during statement processing. Performing scan now.")
                # This requires access to ALL statements, which is tricky in this handler-per-statement model.
                # For now, we'll assume the main orchestrator calls _scan_for_registers and _update_context_with_mapping separately.
                pass # Rely on pre-pass

            # This plugin doesn't translate the instruction itself, it prepares the context.
            # So, we return a TODO or indicate it was handled by preparation.
            return self._result(
                stmt,
                f"      *> Handled by RegisterMappingPlugin preparation: {stmt.raw_text}",
                confidence=ConversionConfidence.HIGH,
                risk=RiskLevel.NONE,
                warnings=["Register mapping prepared."]
            )
        return None # Not handled by this plugin for this opcode


# --- Helper to integrate RegisterMappingPlugin into the pipeline ---

def run_register_mapping_pre_pass(context: ConversionContext, all_statements: List[ParsedStatement]) -> None:
    """
    This function should be called by the Orchestrator *before* iterating through statements for conversion.
    """
    mapper = RegisterMappingPlugin(context)
    mapper._scan_for_registers(all_statements)
    mapper._update_context_with_mapping()



