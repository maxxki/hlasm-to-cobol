#!/usr/bin/env python3

"""
maxxki/plugins/instruction/load_store.py
=========================================
Handles all HLASM Load and Store instructions.

Opcodes covered
---------------
Load family:
  L    Load (fullword from memory)
  LR   Load Register
  LA   Load Address
  LH   Load Halfword
  LHI  Load Halfword Immediate
  LT   Load and Test           (z/Arch)
  LTR  Load and Test Register
  LC   Load Complement         (sets CC)
  LCR  Load Complement Register
  LN   Load Negative
  LNR  Load Negative Register
  LP   Load Positive
  LPR  Load Positive Register
  LM   Load Multiple registers

Store family:
  ST   Store (fullword)
  STH  Store Halfword
  STC  Store Character
  STCM Store Characters under Mask
  STM  Store Multiple registers

COBOL mapping strategy
-----------------------
  L  Rx,mem   →  MOVE mem TO Rx          (simplistic but readable)
  LA Rx,addr  →  MOVE addr TO Rx         (address load loses type info)
  ST Rx,mem   →  MOVE Rx TO mem
  LM R1,R2,D(B) → series of MOVE stubs  (complex — TODO stub)
  STM          → TODO stub

Indexed addressing (e.g., TABLE(R2)) is now handled.
"""
from __future__ import annotations

import re

from .base import IInstructionHandler
from core.types import (
    ConversionConfidence,
    ConversionContext,
    ConversionResult,
    ParsedStatement,
    RiskLevel,
)


class LoadStoreHandler(IInstructionHandler):

    HANDLER_NAME = "LoadStoreHandler"

    OPCODES = frozenset({
        # Load
        "L", "LR", "LA", "LH", "LHI",
        "LT", "LTR",
        "LC", "LCR",
        "LN", "LNR",
        "LP", "LPR",
        "LM",
        # Store
        "ST", "STH", "STC", "STCM", "STM",
    })

    @staticmethod
    def _clean_operand(operand: str) -> str:
        """Strips literal indicators like =F'' from numeric operands and handles common addressing modes."""
        if operand.startswith("=F'") and operand.endswith("'"):
            try:
                return str(int(operand[3:-1]))  # Extract integer from =F'nnn'
            except ValueError:
                pass
        # Handle indexed addressing: TABLE(R2) -> TABLE
        # We will process the index part separately in the _convert method.
        match = re.match(r"^(\w+)\(R?(\d+)\)$", operand)
        if match:
            return match.group(1) # Return the base name (e.g., TABLE)
        
        return operand

    def _convert(
        self,
        op:   str,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> ConversionResult:
        prefix = self._label_prefix(stmt)
        
        # Parse operands, potentially handling indexed addressing
        operand1 = self._op(stmt, 0)
        operand2 = self._op(stmt, 1)

        # Use _map_register for operands that are expected to be registers
        # Note: For indexed addressing, we need to parse the base and index separately.
        mapped_r1 = self._map_register(operand1, ctx) # For operations like L Rx, ...
        mapped_r2 = self._map_register(operand2, ctx) # For operations like L Rx, Ry, ... or L Rx, mem

        # Regex to parse common addressing modes:
        # 1. Base register (e.g., R2)
        # 2. Base address + displacement (e.g., TABLE+4)
        # 3. Base address + displacement + index register (e.g., TABLE(R2))
        # 4. Base address + index register (e.g., TABLE(R2))
        # We primarily care about extracting the base name and the index register if present.
        indexed_address_match = re.match(r"^(\w+)\(R?(\d+)\)$", operand2)
        base_name = None
        index_reg_operand = None
        effective_address_cobol = None

        if indexed_address_match:
            base_name = indexed_address_match.group(1)
            index_reg_operand = f"R{indexed_address_match.group(2)}" # Ensure format like R2
            mapped_index_reg = self._map_register(index_reg_operand, ctx)
            # COBOL representation: Base + Index Register Offset
            # This assumes the index register holds an offset. For simplicity, we add it.
            # A more robust solution would consider data types and array structures.
            cobol_index_offset_expr = f"{mapped_index_reg}"
            effective_address_cobol = f"{base_name} + {cobol_index_offset_expr}"
            _log.debug(f"Parsed indexed addressing: Base='{base_name}', IndexReg='{index_reg_operand}', MappedIndex='{mapped_index_reg}', EffectiveAddrExpr='{effective_address_cobol}'")

        # --- Multi-register ops → complex, emit TODO ---
        if op in ("LM", "STM"):
            return self._todo(stmt, f"{op} requires register-range analysis")

        # --- Store Character under Mask → complex ---
        if op == "STCM":
            return self._todo(stmt, "STCM mask semantics need manual review")

        # --- Load family ---
        if op in ("L", "LR", "LA", "LH", "LHI", "LT", "LTR"):
            target_cobol_var = mapped_r1
            source_cobol_expr = None

            if indexed_address_match:
                # Load from indexed address
                source_cobol_expr = effective_address_cobol
            else:
                # Normal load from memory/literal/register
                source_cobol_expr = self._clean_operand(mapped_r2)
            
            if not target_cobol_var or not source_cobol_expr:
                return self._todo(stmt, f"Could not determine source/target for {op} {stmt.raw_text}")

            cobol = f"{prefix}       MOVE {source_cobol_expr} TO {target_cobol_var}."
            
            # LT / LTR also set the condition code — warn
            if op in ("LT", "LTR"):
                return self._result(
                    stmt, cobol,
                    confidence = ConversionConfidence.MEDIUM,
                    risk       = RiskLevel.LOW,
                    warnings   = [f"{op} sets condition code — IF logic may be needed."],
                )
            return self._result(stmt, cobol)

        # --- Load Complement / Negative / Positive ---
        if op in ("LC", "LCR"):
            # These operations typically involve a single register operand for the result and another for the value.
            # E.g., LC R1, R2 (R1 = -R2)
            cobol = f"{prefix}       COMPUTE {mapped_r1} = -{mapped_r2}."
            return self._result(stmt, cobol, ConversionConfidence.MEDIUM, RiskLevel.LOW)

        if op in ("LN", "LNR"):
            # Load Negative: R1 = ABS(R2) if R2 > 0, else R1 = R2
            cobol = (
                f"{prefix}"
                f"       MOVE {mapped_r2} TO {mapped_r1}.
"
                f"       IF {mapped_r1} > 0 COMPUTE {mapped_r1} = -{mapped_r1} END-IF."
            )
            return self._result(stmt, cobol, ConversionConfidence.MEDIUM, RiskLevel.LOW)

        if op in ("LP", "LPR"):
            # Load Positive: R1 = ABS(R2) if R2 < 0, else R1 = R2
            cobol = (
                f"{prefix}"
                f"       MOVE {mapped_r2} TO {mapped_r1}.
"
                f"       IF {mapped_r1} < 0 COMPUTE {mapped_r1} = -{mapped_r1} END-IF."
            )
            return self._result(stmt, cobol, ConversionConfidence.MEDIUM, RiskLevel.LOW)

        # --- Store family ---
        if op in ("ST", "STH", "STC"):
            # Store Rx FROM Ry (or memory) means MOVE Rx TO Ry (or memory)
            # operand1 is Rx (source), operand2 is Ry/memory (target)
            cobol = f"{prefix}       MOVE {mapped_r1} TO {mapped_r2}."
            return self._result(stmt, cobol)

        return self._todo(stmt)
