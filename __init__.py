#!/usr/bin/env python3

"""
maxxki/plugins/instruction/__init__.py
========================================
InstructionPlugin — the Revolver Router.

This plugin is nothing more than a priority-ordered chain of
IInstructionHandler instances.  When convert() is called, it spins
the cylinder until one handler fires and returns a result.

Handler priority (first match wins)
------------------------------------
1. LoadStoreHandler   — L, LR, LA, ST, STH, …
2. ArithmeticHandler  — A, AR, S, SR, M, MR, D, DR, …
3. MoveHandler        — MVC, MVI, MVCL, …
4. CompareHandler     — CR, C, CLC, TM, …
5. BranchHandler      — B, BC, BE, BNE, BAL, BCT, …
6. ShiftHandler       — SLL, SRL, SLA, SRA, …
7. BooleanHandler     — N, NR, O, OR, X, XR, …
8. DecimalHandler     — AP, SP, MP, ZAP, CVB, CVD, PACK, …
9. FallbackHandler    — catches everything else (always fires)

Adding a new group
------------------
1. Create plugins/instruction/mygroup.py with a class that extends
   IInstructionHandler and declares OPCODES + _convert().
2. Import it below and add an instance to _HANDLERS.
3. Done — no other file needs to change.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from core.types import (
    ConversionContext,
    ConversionResult,
    IPlugin,
    ParsedStatement,
    PluginMetadata,
    StatementType,
)
from .base        import IInstructionHandler
from .load_store  import LoadStoreHandler
from .arithmetic  import ArithmeticHandler
from .move        import MoveHandler
from .compare     import CompareHandler
from .branch      import BranchHandler
from .shift       import ShiftHandler
from .boolean     import BooleanHandler
from .decimal     import DecimalHandler
from .fallback    import FallbackHandler

_log = logging.getLogger(__name__)


class InstructionPlugin(IPlugin):
    """
    Routes ASSEMBLER_INSTRUCTION statements through the handler chain.
    Acts purely as a dispatcher — zero conversion logic lives here.
    """

    _META = PluginMetadata(
        name            = "InstructionPlugin",
        version         = "2.0.0",
        description     = (
            "Revolver-style dispatcher: routes HLASM instructions to "
            "specialised sub-handlers (Load/Store, Arithmetic, Move, "
            "Compare, Branch, Shift, Boolean, Decimal, Fallback)."
        ),
        priority        = 500,
        supported_types = (StatementType.ASSEMBLER_INSTRUCTION,),
    )

    # The cylinder — ordered by expected frequency / specificity.
    _HANDLERS: List[IInstructionHandler] = [
        LoadStoreHandler(),
        ArithmeticHandler(),
        MoveHandler(),
        CompareHandler(),
        BranchHandler(),
        ShiftHandler(),
        BooleanHandler(),
        DecimalHandler(),
        FallbackHandler(),   # must always be last
    ]

    # ------------------------------------------------------------------

    @property
    def metadata(self) -> PluginMetadata:
        return self._META

    def can_handle(
        self,
        statement: ParsedStatement,
        context:   ConversionContext,
    ) -> bool:
        return statement.statement_type == StatementType.ASSEMBLER_INSTRUCTION

    def convert(
        self,
        statement: ParsedStatement,
        context:   ConversionContext,
    ) -> Optional[ConversionResult]:
        op = (statement.operation or "").upper()

        for handler in self._HANDLERS:
            try:
                result = handler.handle(statement, context)
            except Exception as exc:
                _log.error(
                    "Handler '%s' raised on opcode '%s': %s",
                    handler.HANDLER_NAME, op, exc,
                )
                result = None

            if result is not None:
                result.plugin_name = f"{self._META.name}/{handler.HANDLER_NAME}"
                _log.debug(
                    "Opcode '%s' handled by %s (confidence=%s)",
                    op, handler.HANDLER_NAME, result.confidence,
                )
                return result

        # Should never reach here because FallbackHandler always fires.
        _log.error("All handlers missed opcode '%s' — this is a bug!", op)
        return None
