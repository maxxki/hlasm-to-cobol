#!/usr/bin/env python3

"""
maxxki/core/parser.py
=====================
HLASM source → List[ParsedStatement]

Two-tier strategy
-----------------
Tier 1 (preferred)  : PLY-based lexer.  Accurate, handles edge cases.
Tier 2 (fallback)   : Pure-regex line scanner.  Zero dependencies, always
                      works, handles 95 % of real-world HLASM.

The public API is identical regardless of which tier is active, so callers
never need to know which path was taken.  ParsedStatement.parse_mode records it.

FIX 2025-04-26
--------------
Bug: PLY path did `line.split(op, 1)[-1]` which left leading whitespace.
     `_strip_inline_comment` then found double-space at position 0 and
     returned an empty operand string → every instruction fell through to
     UNHANDLED stub.
Fix: `.lstrip()` the split result before passing to `_split_operands`.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from .types import (
    ConversionContext,
    IParser,
    ParsedStatement,
    ParseMode,
    SourceLocation,
    StatementType,
)

_log = logging.getLogger(__name__)

# ── PLY availability ──────────────────────────────────────────────────────────
try:
    import ply.lex as lex   # type: ignore
    _PLY_AVAILABLE = True
except ImportError:
    _PLY_AVAILABLE = False
    _log.info("PLY not installed — parser will use regex fallback.")


# ============================================================================
# REGEX PATTERNS  (used by both tiers)
# ============================================================================

_PAT_COMMENT   = re.compile(r"^\*|^\s*\*>")
_PAT_JCL       = re.compile(r"^//")
_PAT_CICS      = re.compile(r"\bEXEC\s+CICS\b", re.I)
_PAT_SQL       = re.compile(r"\bEXEC\s+SQL\b",  re.I)
_PAT_IMS       = re.compile(r"\b(CBLTDLI|AIBTDLI)\b", re.I)
_PAT_MACRO_DEF = re.compile(r"^\s*MACRO\s*$",  re.I)
_PAT_MEND      = re.compile(r"^\s*MEND\s*$",   re.I)
_PAT_DS_DC     = re.compile(r"^\s*\S*\s+(DS|DC)\s", re.I)
_PAT_SYS_VAR   = re.compile(r"&SYS[A-Z0-9@#$]+", re.I)

# Comprehensive directive set — every standard HLASM assembler directive
_DIRECTIVES = {
    # Program structure
    "CSECT", "DSECT", "RSECT", "COM", "DXD",
    # Base/offset
    "USING", "DROP", "PUSH", "POP",
    # Data / storage control
    "ORG", "LTORG", "EQU", "DC", "DS",
    # Listing / title
    "TITLE", "EJECT", "SPACE", "PRINT",
    # Conditional assembly
    "AIF", "AGO", "ANOP", "ACTR",
    "AIF", "AREAD", "AINSERT",
    # SET symbols
    "SETA", "SETB", "SETC", "LCLA", "LCLB", "LCLC", "GBLA", "GBLB", "GBLC",
    # Macro
    "MACRO", "MEND", "MEXIT", "MNOTE",
    # Copy / include
    "COPY", "INCLUDE",
    # Linkage / entry
    "END", "ENTRY", "EXTRN", "WXTRN",
    # System / misc
    "ICTL", "ISEQ", "OPSYN", "REPRO",
    "SYSSTATE", "YREGS",
    # Common IBM macro-like directives sometimes seen inline
    "START",
}
_PAT_DIRECTIVE = re.compile(
    r"^\s*\S*\s+(" + "|".join(_DIRECTIVES) + r")\b"
    r"|"
    r"^\s*(" + "|".join(_DIRECTIVES) + r")\b",
    re.I,
)

_PAT_INLINE_COMMENT = re.compile(r"\s{2,}\*>.*$")

# Generic HLASM line: optional-label  opcode  operands  optional-comment
_PAT_LINE = re.compile(
    r"^\s*"                           # führende Whitespace
    r"(?:(?P<label>[A-Za-z@#$][A-Za-z0-9@#$]*)\s+)?"   # optional label
    r"(?P<op>[A-Za-z@#$][A-Za-z0-9@#$]*)"             # opcode
    r"(?:\s+(?P<operands>[^ \t*\n][^\n]*?))?"         # operands
    r"(?:\s{2,}.*)?$",                # inline comment
    re.VERBOSE
)


# ============================================================================
# HELPERS
# ============================================================================

def _strip_inline_comment(raw: str) -> str:
    """
    Remove HLASM inline comments from an operand string.
    HLASM convention: operands end at 2+ consecutive spaces or at *> marker.

    IMPORTANT: caller must .lstrip() the raw string before calling this,
    otherwise leading whitespace triggers the double-space check immediately
    and returns an empty string.
    """
    # Cut at two-or-more spaces (operands never contain bare double-space)
    m = re.search(r"  +", raw)
    if m:
        raw = raw[:m.start()]
    # Also cut at explicit *> comment marker
    m2 = re.search(r"\s*\*>", raw)
    if m2:
        raw = raw[:m2.start()]
    return raw.strip()


def _split_operands(raw: str) -> List[str]:
    """
    Split HLASM operand string on commas, but respect parentheses and strings.
    e.g. "D1(B1,X1),D2(B2)" → ["D1(B1,X1)", "D2(B2)"]
    Also handles literals like =F'456' and quoted strings like C'HI,THERE'.
    """
    raw = _strip_inline_comment(raw)

    result: List[str] = []
    depth = 0
    in_string = False
    buf: List[str] = []

    i = 0
    while i < len(raw):
        ch = raw[i]
        if in_string:
            buf.append(ch)
            # Escaped quote: '' inside a string
            if ch == "'" and i + 1 < len(raw) and raw[i + 1] == "'":
                buf.append("'")
                i += 2
                continue
            elif ch == "'":
                in_string = False
        elif ch == "'":
            in_string = True
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            result.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1

    if buf:
        result.append("".join(buf).strip())
    return [o for o in result if o]


def _classify(line: str) -> StatementType:
    """Determine StatementType from a raw line using regex heuristics."""
    stripped = line.strip()
    if not stripped:
        return StatementType.COMMENT
    if _PAT_COMMENT.match(stripped):
        return StatementType.COMMENT
    if _PAT_JCL.match(stripped):
        return StatementType.JCL_STATEMENT
    if _PAT_CICS.search(stripped):
        return StatementType.CICS_EXEC
    if _PAT_SQL.search(stripped):
        return StatementType.SQL_EXEC
    if _PAT_IMS.search(stripped):
        return StatementType.IMS_EXEC
    if _PAT_MACRO_DEF.match(stripped) or _PAT_MEND.match(stripped):
        return StatementType.MACRO_DEFINITION
    if _PAT_SYS_VAR.search(stripped):
        return StatementType.SYSTEM_VARIABLE
    if _PAT_DS_DC.match(stripped):
        return StatementType.DATA_DEFINITION
    if _PAT_DIRECTIVE.match(stripped):
        return StatementType.ASSEMBLER_DIRECTIVE
    return StatementType.ASSEMBLER_INSTRUCTION


# ============================================================================
# REGEX FALLBACK PARSER  (always available)
# ============================================================================

class RegexParser(IParser):
    """Pure-regex HLASM parser.  Fast, zero extra deps, good for 95 % of code."""

    def parse(self, source: str) -> List[ParsedStatement]:
        statements: List[ParsedStatement] = []
        for line_no, raw in enumerate(source.splitlines(), start=1):
            stmt = self.parse_line(raw, line_no)
            statements.append(stmt)
        return statements

    def parse_line(self, line: str, line_no: int = 0) -> ParsedStatement:
        stripped = line.rstrip()
        stmt_type = _classify(stripped)

        label:    Optional[str] = None
        op:       Optional[str] = None
        operands: List[str]     = []
        comments: List[str]     = []

        if stmt_type == StatementType.COMMENT:
            comments = [stripped.lstrip("* ").lstrip("*>").strip()]
        elif stmt_type == StatementType.JCL_STATEMENT:
            op = "JCL"
        else:
            m = _PAT_LINE.match(stripped)
            if m:
                label   = m.group("label")
                op      = m.group("op")
                raw_ops = (m.group("operands") or "").strip()
                operands = _split_operands(raw_ops)

        return ParsedStatement(
            raw_text       = stripped,
            statement_type = stmt_type,
            operation      = op,
            operands       = operands,
            labels         = [label] if label else [],
            comments       = comments,
            parse_mode     = ParseMode.REGEX_FALLBACK,
            location       = SourceLocation("", line_no),
        )


# ============================================================================
# PLY LEXER  (optional — only used when PLY is installed)
# ============================================================================

if _PLY_AVAILABLE:

    class _HLASMLexer:
        """Minimal PLY lexer that produces coarse tokens for the parser."""

        tokens = (
            "LABEL", "OPERATION", "STRING", "NUMBER", "REGISTER",
            "COMMA", "LPAREN", "RPAREN", "EQUALS",
            "COMMENT", "JCL_LINE", "NEWLINE",
        )

        t_COMMA  = r","
        t_LPAREN = r"\("
        t_RPAREN = r"\)"
        t_EQUALS = r"="
        t_ignore = " \t"

        KEYWORDS = _DIRECTIVES  # reuse the comprehensive set

        def t_JCL_LINE(self, t):
            r"^//[^\n]*"
            return t

        def t_COMMENT(self, t):
            r"\*[^\n]*"
            return t

        def t_STRING(self, t):
            r"'[^']*'"
            return t

        def t_REGISTER(self, t):
            r"R\d{1,2}\b"
            return t

        def t_NUMBER(self, t):
            r"\d+"
            t.value = int(t.value)
            return t

        def t_LABEL(self, t):
            r"[A-Za-z@#$][A-Za-z0-9@#$]*"
            t.type = "OPERATION" if t.value.upper() in self.KEYWORDS else "LABEL"
            return t

        def t_NEWLINE(self, t):
            r"\n+"
            t.lexer.lineno += len(t.value)
            return t

        def t_error(self, t):
            _log.debug("PLY lexer: skipping illegal char '%s'", t.value[0])
            t.lexer.skip(1)

        def build(self):
            self._lex = lex.lex(module=self, debug=False, errorlog=_log)
            return self._lex


# ============================================================================
# HYBRID PARSER  (public entry point)
# ============================================================================

class HLASMParser(IParser):
    """
    Public parser that uses PLY when available and falls back to regex.
    Implements IParser — callers only see parse() / parse_line().
    """

    def __init__(self) -> None:
        self._regex = RegexParser()
        self._ply_lexer = None
        if _PLY_AVAILABLE:
            try:
                self._ply_lexer = _HLASMLexer().build()
                _log.info("PLY lexer active.")
            except Exception as exc:
                _log.warning("PLY lexer failed to build (%s) — using regex.", exc)

    # ------------------------------------------------------------------

    def parse(self, source: str) -> List[ParsedStatement]:
        statements: List[ParsedStatement] = []
        for line_no, raw in enumerate(source.splitlines(), start=1):
            stmt = self.parse_line(raw, line_no)
            statements.append(stmt)
        _log.debug("Parsed %d statements.", len(statements))
        return statements

    def parse_line(self, line: str, line_no: int = 0) -> ParsedStatement:
        """
        Parse one line.  Uses PLY for tokenisation if available, then
        maps tokens to a ParsedStatement; falls back to regex otherwise.
        """
        if self._ply_lexer is not None:
            stmt = self._ply_parse_line(line, line_no)
            if stmt is not None:
                return stmt

        return self._regex.parse_line(line, line_no)

    # ------------------------------------------------------------------
    # PLY-assisted path
    # ------------------------------------------------------------------

    def _ply_parse_line(self, line: str, line_no: int) -> Optional[ParsedStatement]:
        try:
            self._ply_lexer.input(line)
            tokens = list(self._ply_lexer)
        except Exception as exc:
            _log.debug("PLY tokenise error on line %d: %s", line_no, exc)
            return None

        if not tokens:
            return ParsedStatement(
                raw_text=line, statement_type=StatementType.COMMENT,
                parse_mode=ParseMode.PLY_AST,
                location=SourceLocation("", line_no),
            )

        stmt_type = _classify(line)  # regex classify for accuracy

        label:    Optional[str] = None
        op:       Optional[str] = None
        operands: List[str]     = []
        comments: List[str]     = []

        if stmt_type == StatementType.COMMENT:
            comments = [line.lstrip("* ").lstrip("*>").strip()]
        elif stmt_type == StatementType.JCL_STATEMENT:
            op = "JCL"
        else:
            non_skip = [t for t in tokens if t.type not in ("NEWLINE",)]
            idx = 0
            if non_skip and non_skip[0].type == "LABEL":
                label = non_skip[0].value
                idx = 1
            if idx < len(non_skip) and non_skip[idx].type in ("OPERATION", "LABEL"):
                op = non_skip[idx].value
                idx += 1
            # FIX: .lstrip() the split result so leading whitespace does NOT
            # trigger the double-space check in _strip_inline_comment at pos 0,
            # which previously caused all operands to be silently discarded.
            if op:
                after_op = line.split(op, 1)[-1].lstrip()  # <-- THE FIX
                operands = _split_operands(after_op)
            else:
                operands = []

        return ParsedStatement(
            raw_text       = line.rstrip(),
            statement_type = stmt_type,
            operation      = op,
            operands       = operands,
            labels         = [label] if label else [],
            comments       = comments,
            parse_mode     = ParseMode.PLY_AST,
            location       = SourceLocation("", line_no),
        )
