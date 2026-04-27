#!/usr/bin/env python3

from __future__ import annotations
import logging
from typing import Optional

from .types import (
    ConversionConfidence,
    ConversionContext,
    ConversionResult,
    IPlugin,
    ParsedStatement,
    PluginMetadata,
    RiskLevel,
    StatementType,
)

_log = logging.getLogger(__name__)

class DirectivePlugin(IPlugin):
    """
    Handles HLASM directives like CSECT, DSECT, USING, and END.
    Maps them to COBOL structural divisions.
    """

    _META = PluginMetadata(
        name            = "DirectivePlugin",
        version         = "1.0.0",
        description     = "Handles HLASM structural directives (CSECT, END, etc.)",
        priority        = 1000, # High priority to catch structure early
        supported_types = (StatementType.ASSEMBLER_DIRECTIVE,),
    )

    @property
    def metadata(self) -> PluginMetadata:
        return self._META

    def can_handle(self, statement: ParsedStatement, context: ConversionContext) -> bool:
        return statement.statement_type == StatementType.ASSEMBLER_DIRECTIVE or \
               (statement.operation and statement.operation.upper() in ("CSECT", "END", "TITLE"))

    def convert(self, statement: ParsedStatement, context: ConversionContext) -> Optional[ConversionResult]:
        op = (statement.operation or "").upper()
        label = statement.first_label or ""

        cobol = ""
        conf = ConversionConfidence.HIGH
        risk = RiskLevel.NONE

        if op == "CSECT":
            prog_name = label if label else "MAINPROG"
            context.cobol_divisions["IDENTIFICATION"].append(f"PROGRAM-ID. {prog_name}.")
            cobol = f"*> CSECT {prog_name} -> PROGRAM-ID"

        elif op == "END":
            cobol = "       END PROGRAM."

        elif op == "USING":
            # USING is an Assembler base-register directive with no direct COBOL equivalent.
            cobol = f"*> IGNORED DIRECTIVE: {statement.raw_text} (USING is an Assembler linkage directive)"
            conf = ConversionConfidence.MEDIUM

        elif op == "TITLE":
            cobol = f"*> TITLE: {statement.first_operand}"

        else:
            # Fallback for any other directive (LTORG, ORG, EQU, COPY, etc.)
            cobol = f"*> IGNORED DIRECTIVE: {statement.raw_text}"
            conf = ConversionConfidence.MEDIUM

        return ConversionResult(
            original_statement  = statement.raw_text,
            converted_statement = cobol,
            statement_type      = statement.statement_type,
            confidence          = conf,
            plugin_name         = self._META.name,
            risk_level          = risk,
            source              = statement,
        )
