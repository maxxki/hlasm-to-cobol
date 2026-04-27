#!/usr/bin/env python3

"""
maxxki/plugins/instruction/base.py
===================================
Abstract base class for all instruction sub-handlers.

Every handler covers one logical group of HLASM opcodes.
The InstructionPlugin (router) iterates handlers in priority order
and calls handle() on each until one returns a result.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import FrozenSet, Optional

from core.types import (
    ConversionConfidence,
    ConversionContext,
    ConversionResult,
    ParsedStatement,
    RiskLevel,
    StatementType,
)


class IInstructionHandler(ABC):
    """
    Contract for a single opcode-group handler.

    Subclasses declare their opcode set in OPCODES and implement _convert().
    handle() is final — it owns the can-handle check and result construction.
    """

    # Subclasses override these two class-level attributes
    OPCODES:      FrozenSet[str] = frozenset()
    HANDLER_NAME: str            = "BaseHandler"

    # ------------------------------------------------------------------
    # Final public entry point — do not override
    # ------------------------------------------------------------------

    def handle(
        self,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> Optional[ConversionResult]:
        """
        Return a ConversionResult if this handler owns the opcode,
        None otherwise (lets the router fall through to the next handler).
        """
        op = (stmt.operation or "").upper()
        if op not in self.OPCODES:
            return None
        return self._convert(op, stmt, ctx)

    # ------------------------------------------------------------------
    # Subclasses implement this
    # ------------------------------------------------------------------

    @abstractmethod
    def _convert(
        self,
        op:   str,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> Optional[ConversionResult]:
        """Produce a ConversionResult for *op*.  May return None to skip."""

    # ------------------------------------------------------------------
    # Shared helpers available to all handlers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_register(reg_operand: str, ctx: ConversionContext) -> str:
        """
        Map Assembler register operand (e.g., '1', 'R1', 'TABLE(R2)')
        to its corresponding COBOL variable name (e.g., 'WS-R1').
        
        This method now relies on the ConversionContext to provide the mapping,
        which is dynamically populated by the RegisterMappingPlugin.
        """
        if not reg_operand:
            return reg_operand

        # Try to get the COBOL variable name from the context.
        # The context's get_cobol_var_for_register() method handles:
        # 1. Checking generated WS variables (e.g., WS-REG0).
        # 2. Falling back to static mappings if available.
        # 3. Returning None if the operand is not a recognized register.
        cobol_var = ctx.get_cobol_var_for_register(reg_operand)
        
        if cobol_var:
            return cobol_var
        else:
            # If it's not a register we can map, return the operand as is.
            # This might be a memory address, literal, etc.
            return reg_operand

    @staticmethod
    def _result(
        stmt:       ParsedStatement,
        cobol:      str,
        confidence: ConversionConfidence = ConversionConfidence.HIGH,
        risk:       RiskLevel            = RiskLevel.NONE,
        warnings:   list[str]            | None = None,
    ) -> ConversionResult:
        """Convenience factory for ConversionResult."""
        return ConversionResult(
            original_statement  = stmt.raw_text,
            converted_statement = cobol,
            statement_type      = stmt.statement_type,
            confidence          = confidence,
            risk_level          = risk,
            warnings            = warnings or [],
            source              = stmt,
            plugin_name         = getattr(stmt, 'handler_name', None), # Attempt to get handler name if available
        )

    @staticmethod
    def _todo(stmt: ParsedStatement, reason: str = "") -> ConversionResult:
        """Emit a TODO stub with HIGH risk."""
        note = f" ({reason})" if reason else ""
        return ConversionResult(
            original_statement  = stmt.raw_text,
            converted_statement = f"      *> TODO{note}: {stmt.raw_text}",
            statement_type      = stmt.statement_type,
            confidence          = ConversionConfidence.LOW,
            risk_level          = RiskLevel.HIGH,
            warnings            = [f"Manual review required{note}."],
            source              = stmt,
            plugin_name         = getattr(stmt, 'handler_name', None), 
        )

    @staticmethod
    def _label_prefix(stmt: ParsedStatement) -> str:
        """Return '       LABEL.
' if the statement carries a label, else ''."""
        lbl = stmt.first_label
        # Corrected f-string for multiline output using triple quotes
        return f"""       {lbl}.
""" if lbl else ""

    @staticmethod
    def _op(stmt: ParsedStatement, n: int) -> str:
        """Return operand n (0-based) or '' if not present."""
        try:
            return stmt.operands[n]
        except IndexError:
            return ""
