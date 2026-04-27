#!/usr/bin/env python3

"""
maxxki/core/orchestrator.py
============================
Central conversion pipeline controller.

FIX 2025-04-26
--------------
Bug: DATA DIVISION entries were written twice — once from cobol_divisions
     (step 1 of _assemble_cobol) and again from ConversionResult.converted_statement
     (step 2), because DataDivisionPlugin stores the COBOL line in BOTH places.

Fix: DataDivisionPlugin now sets converted_statement = "" so step 2 has
     nothing to emit. The _DIVISION_MANAGED_TYPES guard remains as a
     second line of defence.
     Additionally, _assemble_cobol now explicitly skips empty
     converted_statement strings (already done) AND skips any result
     whose statement_type is in _DIVISION_MANAGED_TYPES (also already done).
     The real fix is in DataDivisionPlugin — see that file.

     Here in the orchestrator we add a belt-and-suspenders check:
     skip results where converted_statement is empty OR whitespace-only.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import ConfigurationManager
from .registry import ServiceRegistry
from .types import (
    ConversionConfidence,
    ConversionContext,
    ConversionResult,
    ConversionReport, # Added
    IMLConverter,
    IParser,
    IPlugin,
    ParsedStatement,
    RiskLevel,
    SourceLocation,
    StatementType,
)

_log = logging.getLogger(__name__)


# ============================================================================
# REPORT OBJECTS
# ============================================================================

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


# (Removed from orchestrator.py)


# ============================================================================
# SYMBOLIC STATE UPDATER
# ============================================================================

_CC_SETTERS = frozenset({
    "LR", "L", "AR", "SR", "MR", "DR", "CR", "CLR",
    "A", "S", "M", "D", "C", "CL", "LA",
    "TM", "NI", "OI", "XI", "NC", "OC", "XC",
    "BXH", "BXLE",
})
_LOAD_OPS  = frozenset({"L", "LR", "LA", "LH", "LHI", "LGR", "LG"})
_STORE_OPS = frozenset({"ST", "STH", "STC", "STG"})


def _update_symbolic_state(stmt: ParsedStatement, ctx: ConversionContext) -> None:
    op = (stmt.operation or "").upper()

    if op in _CC_SETTERS:
        ctx.condition_code = None

    if op in _LOAD_OPS and stmt.operands:
        target_reg = stmt.operands[0].strip().upper()
        if len(stmt.operands) > 1:
            ctx.update_register(target_reg, f"<{op}:{stmt.operands[1]}>")
        else:
            ctx.update_register(target_reg, f"<{op}>")

    for label in stmt.labels:
        ctx.record_xref(label, "writes", op or "UNKNOWN")

    _LABEL_RE_MATCH = __import__("re").compile(r"^[A-Za-z@#$][A-Za-z0-9@#$]*$")
    for operand in stmt.operands:
        if _LABEL_RE_MATCH.match(operand):
            ctx.record_xref(operand, "reads", op or "UNKNOWN")


# ============================================================================
# ORCHESTRATOR
# ============================================================================

# Statement types whose COBOL output is managed entirely via cobol_divisions.
# Results with these types must NOT be emitted again in the flat results pass.
_DIVISION_MANAGED_TYPES: Set[StatementType] = {
    StatementType.DATA_DEFINITION,
}


class Orchestrator:

    _ML_FALLBACK_PRIORITY = -1

    def __init__(self) -> None:
        self._cfg_mgr    = ConfigurationManager()
        self._registry   = ServiceRegistry
        self._sorted_plugins: Optional[List[IPlugin]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert_file(self, path: str | Path) -> ConversionReport:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Source file not found: {p}")
        _log.info("convert_file: reading '%s'", p)
        source = p.read_text(encoding="utf-8", errors="replace")
        return self.convert_source(source, source_path=str(p))

    def convert_source(
        self,
        source: str,
        *,
        source_path: Optional[str] = None,
    ) -> ConversionReport:
        t0 = time.perf_counter()

        parser  = self._get_parser()
        stmts   = parser.parse(source)
        _log.debug("Parsed %d statements from '%s'.", len(stmts), source_path or "<string>")

        ctx     = self._build_context(source_path)
        plugins = self._get_sorted_plugins()
        ml_conv = self._get_ml_converter()

        results:     List[ConversionResult] = []
        audit_trail: List[StatementAudit]   = []

        for stmt in stmts:
            if stmt.location:
                ctx.with_location(stmt.location)

            result, plugin_name = self._convert_statement(stmt, ctx, plugins, ml_conv)
            results.append(result)

            _update_symbolic_state(stmt, ctx)

            audit_trail.append(StatementAudit(
                line_number = stmt.location.line_number if stmt.location else 0,
                raw_text    = stmt.raw_text,
                stmt_type   = stmt.statement_type,
                plugin_used = plugin_name,
                confidence  = result.confidence,
                risk_level  = result.risk_level,
                duration_ms = result.processing_time_ms,
                warnings    = list(result.warnings),
                errors      = list(result.errors),
            ))

        cobol_lines = self._assemble_cobol(ctx, results)

        duration_ms = (time.perf_counter() - t0) * 1_000
        report = ConversionReport(
            source_path = source_path,
            total_lines = len(stmts),
            duration_ms = duration_ms,
            results     = results,
            audit_trail = audit_trail,
            cobol_lines = cobol_lines,
        )
        report.statistics = self._compute_statistics(report)

        _log.info(
            "Conversion complete: %d statements, %.1f ms, success_rate=%.1f%%",
            report.total_lines, report.duration_ms, report.success_rate * 100,
        )
        return report

    # ------------------------------------------------------------------
    # Service resolution
    # ------------------------------------------------------------------

    def _get_parser(self) -> IParser:
        parser = self._registry.get_or_none("parser")
        if parser is None:
            raise RuntimeError(
                "No 'parser' service registered. "
                "Call ServiceRegistry.register('parser', HLASMParser()) first."
            )
        return parser  # type: ignore[return-value]

    def _get_sorted_plugins(self) -> List[IPlugin]:
        if self._sorted_plugins is not None:
            return self._sorted_plugins
        raw = self._registry.get_or_none("plugins") or []
        if not raw:
            _log.warning("No plugins registered — all statements will fall through to ML or unconverted.")
        self._sorted_plugins = sorted(raw, key=lambda p: p.metadata.priority, reverse=True)
        names = [p.metadata.name for p in self._sorted_plugins]
        _log.info("Plugin chain (priority order): %s", names)
        return self._sorted_plugins

    def _get_ml_converter(self) -> Optional[IMLConverter]:
        conv = self._registry.get_or_none("ml_converter")
        if conv is None:
            _log.debug("No 'ml_converter' registered — ML fallback disabled.")
        elif not conv.is_available():
            _log.warning("ML converter registered but reports not available.")
            return None
        return conv  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Context construction
    # ------------------------------------------------------------------

    def _build_context(self, source_path: Optional[str]) -> ConversionContext:
        cfg = self._cfg_mgr.config
        ctx = ConversionContext(
            options={
                "cobol_target":       cfg.cobol_target,
                "generate_copybooks": cfg.generate_copybooks,
                "preserve_comments":  cfg.preserve_comments,
                "min_ml_confidence":  cfg.min_ml_confidence,
            },
            feature_flags=[],
        )
        for i in range(16):
            ctx.registers[f"R{i}"] = None
        ctx.condition_code = None
        if source_path:
            ctx.location = SourceLocation(source_path, 0)
        return ctx

    # ------------------------------------------------------------------
    # Core statement conversion
    # ------------------------------------------------------------------

    def _convert_statement(
        self,
        stmt:    ParsedStatement,
        ctx:     ConversionContext,
        plugins: List[IPlugin],
        ml_conv: Optional[IMLConverter],
    ) -> Tuple[ConversionResult, Optional[str]]:
        t0 = time.perf_counter()

        for plugin in plugins:
            if not plugin.can_handle(stmt, ctx):
                continue
            try:
                result = plugin.convert(stmt, ctx)
            except Exception as exc:
                _log.error(
                    "Plugin '%s' raised on line %s: %s",
                    plugin.metadata.name,
                    stmt.location.line_number if stmt.location else "?",
                    exc,
                )
                result = None

            if result is not None:
                result.processing_time_ms = (time.perf_counter() - t0) * 1_000
                return result, plugin.metadata.name

        if ml_conv is not None:
            try:
                ml_result = ml_conv.convert(stmt, ctx)
            except Exception as exc:
                _log.error("ML converter raised: %s", exc)
                ml_result = None

            if ml_result is not None:
                if ml_result.confidence == ConversionConfidence.UNKNOWN:
                    ml_result = self._make_fallback_stub(stmt, t0, note="ML confidence unknown")
                ml_result.processing_time_ms = (time.perf_counter() - t0) * 1_000
                return ml_result, None

        stub = self._make_fallback_stub(stmt, t0)
        return stub, None

    @staticmethod
    def _make_fallback_stub(
        stmt: ParsedStatement,
        t0:   float,
        note: str = "No plugin or ML converter handled this statement",
    ) -> ConversionResult:
        return ConversionResult(
            original_statement  = stmt.raw_text,
            converted_statement = f"*> TODO: {stmt.raw_text}",
            statement_type      = stmt.statement_type,
            confidence          = ConversionConfidence.UNKNOWN,
            risk_level          = RiskLevel.HIGH,
            processing_time_ms  = (time.perf_counter() - t0) * 1_000,
            warnings            = [note],
            source              = stmt,
        )

    # ------------------------------------------------------------------
    # COBOL assembly
    # ------------------------------------------------------------------

    def _assemble_cobol(
        self,
        ctx:     ConversionContext,
        results: List[ConversionResult],
    ) -> List[str]:
        for reg, cobol_name in ctx.register_map.items():
            if ctx.registers.get(reg) is not None:  # Register wurde benutzt
                ctx.cobol_divisions["DATA"].insert(0, f"       05  {cobol_name:<30} PIC S9(9) COMP.")

        lines: List[str] = []

        # ── 1. Structured divisions (IDENTIFICATION, DATA, …) ─────────────────
        # Written in a fixed, meaningful order rather than dict-insertion order.
        division_order = ["IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE"]
        for div_name in division_order:
            div_lines = ctx.cobol_divisions.get(div_name, [])
            if div_lines:
                lines.append(f"       {div_name} DIVISION.")
                for dl in div_lines:
                    lines.append(dl if dl.startswith("       ") else f"       {dl}")
                lines.append("")

        # ── 2. Per-statement results — skip division-managed types ────────────
        procedure_started = False
        for result in results:
            # Skip blank converted statements
            if not result.converted_statement or not result.converted_statement.strip():
                continue
            # DATA DIVISION entries were already written above
            if result.statement_type in _DIVISION_MANAGED_TYPES:
                continue
            # Emit PROCEDURE DIVISION header before first procedural line
            if (
                not procedure_started
                and result.statement_type == StatementType.ASSEMBLER_INSTRUCTION
            ):
                lines.append("       PROCEDURE DIVISION.")
                procedure_started = True

            lines.append(result.converted_statement)

        return lines

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_statistics(report: ConversionReport) -> Dict[str, Any]:
        total = len(report.results)
        if total == 0:
            return {"total": 0}

        conf_counts: Dict[str, int] = {}
        for r in report.results:
            key = r.confidence.value
            conf_counts[key] = conf_counts.get(key, 0) + 1

        risk_counts: Dict[str, int] = {}
        for r in report.results:
            key = r.risk_level.value
            risk_counts[key] = risk_counts.get(key, 0) + 1

        type_counts: Dict[str, int] = {}
        for a in report.audit_trail:
            key = a.stmt_type.value
            type_counts[key] = type_counts.get(key, 0) + 1

        plugin_usage: Dict[str, int] = {}
        ml_count   = 0
        stub_count = 0
        for a in report.audit_trail:
            if a.plugin_used:
                plugin_usage[a.plugin_used] = plugin_usage.get(a.plugin_used, 0) + 1
            elif a.confidence == ConversionConfidence.UNKNOWN:
                stub_count += 1
            else:
                ml_count += 1

        successful   = sum(1 for r in report.results if r.is_successful)
        needs_review = sum(1 for r in report.results if r.needs_review)

        return {
            "total":             total,
            "successful":        successful,
            "success_rate_pct":  round(successful / total * 100, 1),
            "needs_review":      needs_review,
            "unconverted_stubs": stub_count,
            "ml_converted":      ml_count,
            "total_duration_ms": round(report.duration_ms, 2),
            "avg_stmt_ms":       round(report.duration_ms / total, 3),
            "confidence":        conf_counts,
            "risk":              risk_counts,
            "statement_types":   type_counts,
            "plugin_usage":      plugin_usage,
        }
