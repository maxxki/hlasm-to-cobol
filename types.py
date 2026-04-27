#!/usr/bin/env python3

"""
maxxki/core/types.py
====================
Single Source of Truth for all shared types, enums, dataclasses and
abstract interfaces. No business logic lives here — only contracts.

Architecture principle:
  Every other module imports FROM here. Nothing in this file imports
  from any other maxxki module.  This eliminates circular imports.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


# ============================================================================
# ENUMS
# ============================================================================

class StatementType(Enum):
    """Canonical statement-type taxonomy for HLASM source."""
    # Assembler primitives
    DATA_DEFINITION        = "DATA_DEFINITION"        # DS / DC
    ASSEMBLER_INSTRUCTION  = "ASSEMBLER_INSTRUCTION"  # L, ST, AR, …
    ASSEMBLER_DIRECTIVE    = "ASSEMBLER_DIRECTIVE"     # USING, ORG, EQU, …
    # Structured control
    MACRO_DEFINITION       = "MACRO_DEFINITION"        # MACRO … MEND
    MACRO_CALL             = "MACRO_CALL"              # any user-defined macro
    CONDITIONAL            = "CONDITIONAL"             # AIF / AGO / ANOP
    # Subsystem interfaces
    CICS_EXEC              = "CICS_EXEC"
    SQL_EXEC               = "SQL_EXEC"
    IMS_EXEC               = "IMS_EXEC"
    JCL_STATEMENT          = "JCL_STATEMENT"
    # Meta
    COMMENT                = "COMMENT"
    SYSTEM_VARIABLE        = "SYSTEM_VARIABLE"         # &SYSDATE etc.
    UNKNOWN                = "UNKNOWN"


class ConversionConfidence(Enum):
    """How certain the converter is about the produced COBOL."""
    HIGH    = "HIGH"     # Rule-based, deterministic
    MEDIUM  = "MEDIUM"   # Heuristic or partial match
    LOW     = "LOW"      # ML-generated, needs review
    UNKNOWN = "UNKNOWN"  # Fallback / not converted


class RiskLevel(Enum):
    """
    Risk assigned to a conversion result.
    CRITICAL means the symbolic execution detected a logic mismatch.
    """
    NONE     = "NONE"
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class ParseMode(Enum):
    """Which parsing strategy produced this statement."""
    PLY_AST        = "PLY_AST"
    REGEX_FALLBACK = "REGEX_FALLBACK"
    HYBRID         = "HYBRID"


# ============================================================================
# VALUE OBJECTS  (immutable after construction)
# ============================================================================

@dataclass(frozen=True)
class SourceLocation:
    """Pinpoints where in the original source a statement lives."""
    file_path:     str
    line_number:   int
    column_number: Optional[int] = None


@dataclass(frozen=True)
class PluginMetadata:
    """Declarative description of a converter plugin."""
    name:            str
    version:         str
    description:     str
    priority:        int                    # Higher → tried first
    supported_types: tuple[StatementType, ...] = ()


@dataclass
class StatementAudit:
    """Per-statement audit entry kept inside ConversionReport."""
    line_number:  int
    raw_text:     str
    stmt_type:    StatementType
    plugin_used:  Optional[str]
    confidence:   ConversionConfidence
    risk_level:   RiskLevel
    duration_ms:  float
    warnings:     List[str]  = field(default_factory=list)
    errors:       List[str]  = field(default_factory=list)


@dataclass
class ConversionReport:
    source_path:   Optional[str]
    total_lines:   int
    duration_ms:   float

    results:       List[ConversionResult]   = field(default_factory=list)
    audit_trail:   List[StatementAudit]     = field(default_factory=list)
    cobol_lines:   List[str]                = field(default_factory=list)
    statistics:    Dict[str, Any]           = field(default_factory=dict)

    @property
    def cobol_text(self) -> str:
        return "\n".join(self.cobol_lines)

    @property
    def has_critical_risk(self) -> bool:
        return any(a.risk_level == RiskLevel.CRITICAL for a in self.audit_trail)

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        ok = sum(1 for r in self.results if r.is_successful)
        return ok / len(self.results)


@dataclass
class ParsedStatement:
    """
    Structured representation of a single HLASM statement,
    as produced by the parser layer.
    """
    raw_text:       str
    statement_type: StatementType
    operation:      Optional[str]       = None
    operands:       List[str]           = field(default_factory=list)
    labels:         List[str]           = field(default_factory=list)
    comments:       List[str]           = field(default_factory=list)
    parameters:     Dict[str, str]      = field(default_factory=dict)
    parse_mode:     ParseMode           = ParseMode.REGEX_FALLBACK
    location:       Optional[SourceLocation] = None

    # ── Convenience ──────────────────────────────────────────────────────────
    @property
    def first_label(self) -> Optional[str]:
        return self.labels[0] if self.labels else None

    @property
    def first_operand(self) -> Optional[str]:
        return self.operands[0] if self.operands else None


@dataclass
class ConversionResult:
    """
    The output of converting one ParsedStatement to COBOL.
    Carries full provenance: who converted it, how confident, at what risk.
    """
    original_statement:  str
    converted_statement: str
    statement_type:      StatementType
    confidence:          ConversionConfidence
    plugin_name:         Optional[str]  = None
    risk_level:          RiskLevel      = RiskLevel.NONE
    processing_time_ms:  float          = 0.0
    warnings:            List[str]      = field(default_factory=list)
    errors:              List[str]      = field(default_factory=list)
    comments:            List[str]      = field(default_factory=list)
    source:              Optional[ParsedStatement] = None

    # ── Derived ──────────────────────────────────────────────────────────────
    @property
    def is_successful(self) -> bool:
        return (
            bool(self.converted_statement)
            and self.confidence != ConversionConfidence.UNKNOWN
            and not self.errors
        )

    @property
    def needs_review(self) -> bool:
        return self.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)


@dataclass
class ConversionContext:
    """
    Mutable bag of state that flows through the conversion pipeline.
    Plugins read from and write to this object.
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
    register_map: Dict[str, str] = field(default_factory=lambda: {
        "0": "WS-R0", "1": "WS-R1", "2": "WS-R2", "3": "WS-R3",
        "4": "WS-R4", "5": "WS-R5", "6": "WS-R6", "7": "WS-R7",
        "8": "WS-R8", "9": "WS-R9", "10": "WS-R10", "11": "WS-R11",
        "12": "WS-R12", "13": "WS-R13", "14": "WS-R14", "15": "WS-R15",
    })

    cobol_divisions: Dict[str, List[str]] = field(default_factory=lambda: {
        "IDENTIFICATION": [],
        "ENVIRONMENT":    [],
        "DATA":           [],
        "PROCEDURE":      [],
    })

    # Current source location (updated by the orchestrator per statement)
    location: Optional[SourceLocation] = None

    # Last compare result (used by conditional branches)
    last_compare_result: Optional[str] = None

    # ── Helpers ──────────────────────────────────────────────────────────────
    def update_register(self, reg: str, value: Any) -> None:
        self.registers[reg.upper()] = value

    def get_register(self, reg: str) -> Any:
        return self.registers.get(reg.upper())

    def record_xref(self, label: str, mode: str, by: str) -> None:
        """mode ∈ {'reads', 'writes'}"""
        entry = self.xref.setdefault(label, {"reads": [], "writes": []})
        entry[mode].append(by)

    def with_location(self, loc: SourceLocation) -> "ConversionContext":
        self.location = loc
        return self


# ============================================================================
# ABSTRACT INTERFACES
# ============================================================================

class IPlugin(ABC):
    """
    Every converter plugin implements this interface.
    The orchestrator only talks to plugins through this contract.
    """

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Declarative description — must be a class-level constant."""

    @abstractmethod
    def can_handle(
        self,
        statement: ParsedStatement,
        context:   ConversionContext,
    ) -> bool:
        """
        Return True iff this plugin is able to convert *statement*.
        Must be fast (no I/O, no heavy computation).
        """

    @abstractmethod
    def convert(
        self,
        statement: ParsedStatement,
        context:   ConversionContext,
    ) -> Optional[ConversionResult]:
        """
        Convert *statement* to COBOL.
        Return None to signal "I cannot handle this after all" (graceful
        skip — the orchestrator will fall through to the next plugin).
        """


class IParser(ABC):
    """Contract for the HLASM parser layer."""

    @abstractmethod
    def parse(self, source: str) -> List[ParsedStatement]:
        """Parse full source text into a flat list of statements."""

    @abstractmethod
    def parse_line(self, line: str, line_no: int = 0) -> ParsedStatement:
        """Parse a single raw line."""


class IMLConverter(ABC):
    """Contract for ML-based conversion back-end."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True iff the model is loaded and ready."""

    @abstractmethod
    def convert(self, statement: ParsedStatement, context: ConversionContext) -> Optional[ConversionResult]:
        """Attempt ML-based conversion; return None on failure."""
