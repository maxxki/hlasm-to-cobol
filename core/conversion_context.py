#!/usr/bin/env python3

"""
maxxki/core/conversion_context.py
===============================

Manages the mutable state passed through the conversion pipeline.
This includes register states, variables, labels, and accumulated COBOL divisions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional

from core.types import (
    ConversionContext as ConversionContextBase,
    ParsedStatement,
    SourceLocation,
    StatementType,
)

_log = logging.getLogger(__name__)


@dataclass
class ConversionContext(ConversionContextBase):
    """
    Mutable bag of state that flows through the conversion pipeline.
    Plugins read from and write to this object.

    Extended with specific logic for register mapping and code generation.
    """
    # User / run-time settings
    options:       Dict[str, Any]       = field(default_factory=dict)
    feature_flags: List[str]            = field(default_factory=list)

    # Macro table: name → definition dict
    macros:        Dict[str, Any]       = field(default_factory=dict)

    # Symbolic execution state (register file + condition codes)
    registers:     Dict[str, Any]       = field(default_factory=dict)   # R0–R15
    condition_code: Optional[int]       = None                          # 0-3

    # Variable table (assembler SET symbols etc.)
    variables:     Dict[str, str]       = field(default_factory=dict)

    # XREF: label → {"reads": [...], "writes": [...]}
    xref:          Dict[str, Dict[str, List[str]]] = field(default_factory=dict)

    # Accumulated COBOL divisions
    # This will be populated by plugins, especially the new RegisterMappingPlugin
    cobol_divisions: Dict[str, List[str]] = field(default_factory=lambda: {
        "IDENTIFICATION": [],
        "ENVIRONMENT":    [],
        "DATA":           [],
        "PROCEDURE":      [],
    })

    # Mapping of Assembler registers to COBOL variable names.
    # This will be dynamically populated by RegisterMappingPlugin.
    # Initially, it can have a basic mapping for convenience.
    register_map: Dict[str, str] = field(default_factory=lambda: {
        "0": "WS-R0", "1": "WS-R1", "2": "WS-R2", "3": "WS-R3",
        "4": "WS-R4", "5": "WS-R5", "6": "WS-R6", "7": "WS-R7",
        "8": "WS-R8", "9": "WS-R9", "10": "WS-R10", "11": "WS-R11",
        "12": "WS-R12", "13": "WS-R13", "14": "WS-R14", "15": "WS-R15",
    })

    # To store generated WORKING-STORAGE items for registers
    # Key: Assembler Register Number (e.g., "0", "15")
    # Value: COBOL PIC clause (e.g., "PIC S9(9) COMP.")
    generated_ws_registers: Dict[str, str] = field(default_factory=dict)

    # Current source location (updated by the orchestrator per statement)
    location: Optional[SourceLocation] = None

    # Last compare result (used by conditional branches)
    last_compare_result: Optional[str] = None

    # Counter for generating unique labels (e.g., for BCTR targets)
    label_counter: int = 0

    # Mapping for labels associated with registers, for more complex branching
    # Example: { "REG_LABEL_FOR_R5": "TARGET_LABEL_FROM_R5" }
    register_label_map: Dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_register_value(self, reg: str, value: Any) -> None:
        """Updates the symbolic value of an assembler register."""
        self.registers[reg.upper()] = value

    def get_register_value(self, reg: str) -> Any:
        """Retrieves the symbolic value of an assembler register."""
        return self.registers.get(reg.upper())

    def record_xref(self, label: str, mode: str, by: str) -> None:
        """Records cross-references for labels (mode ∈ {'reads', 'writes'})."""
        entry = self.xref.setdefault(label, {"reads": [], "writes": []})
        entry[mode].append(by)

    def with_location(self, loc: SourceLocation) -> "ConversionContext":
        """Returns a new context with updated source location (for immutability if needed)."""
        # Note: This implementation is mutable. A truly immutable version would deepcopy.
        # For now, we assume mutability is intended for pipeline state.
        self.location = loc
        return self

    def generate_cobol_label(self, prefix: str = "LABEL") -> str:
        """Generates a unique COBOL label name."""
        self.label_counter += 1
        return f"{prefix.upper()}_{self.label_counter:04d}"

    def get_cobol_var_for_register(self, reg_operand: str) -> Optional[str]:
        """
        Returns the COBOL variable name for a given assembler register operand.
        This method will be enhanced by RegisterMappingPlugin.
        """
        clean_reg = reg_operand.upper().replace('R', '')
        if clean_reg.isdigit() and 0 <= int(clean_reg) <= 15:
            reg_num = clean_reg
            # 1. Check if it's a dynamically generated WS var
            if reg_num in self.generated_ws_registers:
                return f"WS-REG{reg_num}" # Assuming generated WS vars are named WS-REG0, WS-REG1 etc.
            # 2. Check the static map (if no dynamic var is defined)
            return self.register_map.get(reg_num)
        return None

    def ensure_register_is_mapped(self, reg_operand: str) -> Optional[str]:
        """
        Ensures a register has a corresponding COBOL variable mapped.
        If not already mapped, it attempts to define one.
        Returns the COBOL variable name or None if mapping fails.
        """
        cobol_var = self.get_cobol_var_for_register(reg_operand)
        if cobol_var:
            return cobol_var

        clean_reg = reg_operand.upper().replace('R', '')
        if clean_reg.isdigit() and 0 <= int(clean_reg) <= 15:
            reg_num = clean_reg
            # If no mapped var exists, and it's a valid register, create a placeholder
            # The RegisterMappingPlugin will finalize these.
            # For now, we assume a default PIC S9(9) COMP.
            if reg_num not in self.generated_ws_registers:
                _log.debug("Temporarily mapping register %s to WS-REG%s", reg_operand, reg_num)
                # This is a placeholder; RegisterMappingPlugin will make it permanent
                self.generated_ws_registers[reg_num] = "PIC S9(9) COMP."
                return f"WS-REG{reg_num}"
        return None

    def add_cobol_division_line(self, division_name: str, line: str) -> None:
        """Adds a line to the specified COBOL division."""
        division_name = division_name.upper()
        if division_name in self.cobol_divisions:
            self.cobol_divisions[division_name].append(line)
        else:
            _log.warning("Attempted to add line to unknown COBOL division: %s", division_name)

    def get_cobol_division_content(self, division_name: str) -> List[str]:
        """Retrieves the content of a COBOL division."""
        return self.cobol_divisions.get(division_name.upper(), [])

    def get_all_generated_ws_items(self) -> List[str]:
        """Returns a list of all generated WORKING-STORAGE items.
        Format: "05 WS-REGX PIC S9(9) COMP." (example)
        """
        ws_items = []
        # Ensure we iterate over sorted register numbers for consistent output
        sorted_regs = sorted(self.generated_ws_registers.keys(), key=lambda x: int(x))
        for reg_num in sorted_regs:
            pic_clause = self.generated_ws_registers[reg_num]
            ws_items.append(f"    05 WS-REG{reg_num} {pic_clause}")
        return ws_items

    def set_last_compare_result(self, result: Optional[str]) -> None:
        """Sets the result of the last comparison operation (e.g., EQ, NE, GT)."""
        self.last_compare_result = result

    def get_last_compare_result(self) -> Optional[str]:
        """Gets the result of the last comparison operation."""
        return self.last_compare_result

    def add_register_label_mapping(self, reg_operand: str, target_label: str) -> None:
        """Maps an assembler register to a COBOL label for branching targets."""
        self.register_label_map[reg_operand.upper()] = target_label

    def get_cobol_label_from_register(self, reg_operand: str) -> Optional[str]:
        """Retrieves the COBOL label associated with an assembler register."""
        return self.register_label_map.get(reg_operand.upper())
