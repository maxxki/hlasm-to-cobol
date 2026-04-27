#!/usr/bin/env python3

"""
maxxki/plugins/data_division_plugin.py
=======================================
Converts HLASM DS (Define Storage) and DC (Define Constant) statements
to COBOL DATA DIVISION entries.

Priority: 900  — runs before arithmetic / branch plugins but after any
                 higher-priority structural plugins.

FIX 2025-04-26
--------------
Bug: Plugin was writing the COBOL line to BOTH:
       (a) context.cobol_divisions["DATA"]   → emitted in _assemble_cobol step 1
       (b) ConversionResult.converted_statement → emitted again in step 2
     This caused every DS/DC entry to appear twice in the output.

Fix: Set converted_statement = "" in the returned ConversionResult.
     The real output lives in cobol_divisions["DATA"].
     The orchestrator's _DIVISION_MANAGED_TYPES guard remains as a
     second line of defence, but the empty string check in step 2
     now also catches it cleanly.

Supported patterns
------------------
DS  0H / 0F / 0D         → alignment comment
DS  CL<n>                → PIC X(<n>)
DS  PL<n>                → PIC S9(<n*2-1>) COMP-3  (packed decimal)
DS  ZL<n>                → PIC S9(<n>) (zoned decimal, display)
DS  F / FL4              → PIC S9(9) COMP  (fullword)
DS  H / HL2              → PIC S9(4) COMP  (halfword)
DS  D / DL8              → COMP-2           (double float)
DS  E / EL4              → COMP-1           (single float)
DS  <n>CL<l>             → array: OCCURS <n> TIMES PIC X(<l>)

DC  C'<text>'            → PIC X(<n>) VALUE '<text>'
DC  X'<hex>'             → PIC X(<n>) VALUE X'<hex>'
DC  F'<val>'             → PIC S9(9) COMP VALUE <val>
DC  H'<val>'             → PIC S9(4) COMP VALUE <val>
DC  P'<val>'             → PIC S9(15) COMP-3 VALUE <val>
DC  Y'<val>'             → PIC S9(4) COMP VALUE <val>  (address constant)
"""
from __future__ import annotations

import re
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


# ============================================================================
# PATTERN TABLE
# ============================================================================

_DC_CHAR_PAT  = re.compile(r"^C'([^']*)'$",          re.I)
_DC_HEX_PAT   = re.compile(r"^X'([0-9A-Fa-f]*)'$",   re.I)
_DC_NUM_PAT   = re.compile(r"^[FHYy]'([^']*)'$",      re.I)
_DC_PACK_PAT  = re.compile(r"^P'([^']*)'$",           re.I)


# ============================================================================
# PLUGIN
# ============================================================================

class DataDivisionPlugin(IPlugin):

    _META = PluginMetadata(
        name            = "DataDivisionPlugin",
        version         = "1.1.0",
        description     = "Converts HLASM DS/DC statements to COBOL DATA DIVISION entries.",
        priority        = 900,
        supported_types = (StatementType.DATA_DEFINITION,),
    )

    @property
    def metadata(self) -> PluginMetadata:
        return self._META

    # ------------------------------------------------------------------

    def can_handle(
        self,
        statement: ParsedStatement,
        context:   ConversionContext,
    ) -> bool:
        return statement.statement_type == StatementType.DATA_DEFINITION

    def convert(
        self,
        statement: ParsedStatement,
        context:   ConversionContext,
    ) -> Optional[ConversionResult]:
        op = (statement.operation or "").upper()
        if op not in ("DS", "DC"):
            return None

        label    = statement.first_label or "_UNNAMED"
        operand  = statement.first_operand or ""
        warnings: list[str] = []

        if op == "DS":
            cobol, conf, risk = self._convert_ds(label, operand, context, warnings)
        else:
            cobol, conf, risk = self._convert_dc(label, operand, context, warnings)

        if cobol is None:
            warnings.append(f"DataDivisionPlugin: unrecognised operand '{operand}' — stub emitted.")
            cobol = f"       05  {label:<30} PIC X.  *> TODO: DS {operand}"
            conf  = ConversionConfidence.UNKNOWN
            risk  = RiskLevel.HIGH

        # Write the COBOL into the DATA DIVISION accumulator.
        context.cobol_divisions["DATA"].append(cobol)

        # FIX: Do NOT put the cobol line in converted_statement as well —
        # that caused it to be emitted a second time in _assemble_cobol step 2.
        # We return an empty converted_statement; the real output is in
        # cobol_divisions["DATA"] and will be assembled in step 1.
        return ConversionResult(
            original_statement  = statement.raw_text,
            converted_statement = "",          # intentionally empty — see FIX above
            statement_type      = StatementType.DATA_DEFINITION,
            confidence          = conf,
            plugin_name         = self._META.name,
            risk_level          = risk,
            warnings            = warnings,
            source              = statement,
        )

    # ------------------------------------------------------------------
    # DS conversion
    # ------------------------------------------------------------------

    def _convert_ds(
        self,
        label:    str,
        operand:  str,
        context:  ConversionContext,
        warnings: list,
    ) -> tuple[Optional[str], ConversionConfidence, RiskLevel]:

        op = operand.strip()

        # Alignment-only (DS 0H etc.) → comment line
        if re.match(r"^0[HhFfDd]$", op):
            return (
                f"      *> ALIGN: {label} DS {op}",
                ConversionConfidence.HIGH,
                RiskLevel.NONE,
            )

        # Character: [n]CL<len>
        m = re.match(r"^(\d*)CL(\d+)$", op, re.I)
        if m:
            occurs = int(m.group(1)) if m.group(1) else 1
            length = int(m.group(2))
            if occurs > 1:
                cobol = (
                    f"       05  {label:<30} PIC X({length})\n"
                    f"                                        OCCURS {occurs} TIMES."
                )
            else:
                cobol = f"       05  {label:<30} PIC X({length})."
            return cobol, ConversionConfidence.HIGH, RiskLevel.NONE

        # Packed decimal: [n]PL<len>
        m = re.match(r"^(\d*)PL(\d+)$", op, re.I)
        if m:
            occurs = int(m.group(1)) if m.group(1) else 1
            length = int(m.group(2))
            digits = length * 2 - 1
            cobol  = f"       05  {label:<30} PIC S9({digits}) COMP-3."
            if occurs > 1:
                cobol += f"\n                                        OCCURS {occurs} TIMES."
            return cobol, ConversionConfidence.HIGH, RiskLevel.NONE

        # Zoned decimal: [n]ZL<len>
        m = re.match(r"^(\d*)ZL(\d+)$", op, re.I)
        if m:
            length = int(m.group(2))
            cobol  = f"       05  {label:<30} PIC S9({length})."
            return cobol, ConversionConfidence.HIGH, RiskLevel.NONE

        # Fullword F / FL4
        if re.match(r"^(\d*)[Ff](L4)?$", op):
            cobol = f"       05  {label:<30} PIC S9(9) COMP."
            return cobol, ConversionConfidence.HIGH, RiskLevel.NONE

        # Halfword H / HL2
        if re.match(r"^(\d*)[Hh](L2)?$", op):
            cobol = f"       05  {label:<30} PIC S9(4) COMP."
            return cobol, ConversionConfidence.HIGH, RiskLevel.NONE

        # Double D / DL8
        if re.match(r"^(\d*)[Dd](L8)?$", op):
            cobol = f"       05  {label:<30} COMP-2."
            return cobol, ConversionConfidence.MEDIUM, RiskLevel.LOW

        # Single float E / EL4
        if re.match(r"^(\d*)[Ee](L4)?$", op):
            cobol = f"       05  {label:<30} COMP-1."
            return cobol, ConversionConfidence.MEDIUM, RiskLevel.LOW

        return None, ConversionConfidence.UNKNOWN, RiskLevel.HIGH

    # ------------------------------------------------------------------
    # DC conversion
    # ------------------------------------------------------------------

    def _convert_dc(
        self,
        label:    str,
        operand:  str,
        context:  ConversionContext,
        warnings: list,
    ) -> tuple[Optional[str], ConversionConfidence, RiskLevel]:

        op = operand.strip()

        # C'text'
        m = _DC_CHAR_PAT.match(op)
        if m:
            text   = m.group(1)
            length = len(text)
            cobol  = f"       05  {label:<30} PIC X({length}) VALUE '{text}'."
            return cobol, ConversionConfidence.HIGH, RiskLevel.NONE

        # X'hex'
        m = _DC_HEX_PAT.match(op)
        if m:
            hexval = m.group(1)
            length = max(1, len(hexval) // 2)
            cobol  = f"       05  {label:<30} PIC X({length}) VALUE X'{hexval}'."
            return cobol, ConversionConfidence.HIGH, RiskLevel.NONE

        # F/H/Y numeric
        m = _DC_NUM_PAT.match(op)
        if m:
            val    = m.group(1)
            prefix = op[0].upper()
            if prefix in ("F", "Y"):
                cobol = f"       05  {label:<30} PIC S9(9) COMP VALUE {val}."
            else:  # H
                cobol = f"       05  {label:<30} PIC S9(4) COMP VALUE {val}."
            return cobol, ConversionConfidence.HIGH, RiskLevel.NONE

        # P'packed'
        m = _DC_PACK_PAT.match(op)
        if m:
            val   = m.group(1).replace(",", "")
            cobol = f"       05  {label:<30} PIC S9(15) COMP-3 VALUE {val}."
            return cobol, ConversionConfidence.HIGH, RiskLevel.NONE

        return None, ConversionConfidence.UNKNOWN, RiskLevel.HIGH

