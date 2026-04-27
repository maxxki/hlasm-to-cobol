#!/usr/bin/env python3

"""
maxxki/plugins/instruction/branch.py
======================================
Handles HLASM branch instructions.

Opcodes covered
---------------
Unconditional:  B, BR, BAL, BALR, BAS, BASR
Conditional:    BC, BCR
Mnemonics:      BE, BNE, BH, BL, BNH, BNL, BZ, BNZ, BO, BNO, BM, BNM, BP, BNP
Loop:           BCT, BCTR, BXH, BXLE
No-op:          NOP, NOPR

Condition code mask → COBOL IF operator mapping
-------------------------------------------------
HLASM BC  mask,target uses a 4-bit mask:
  8 = CC=0 (equal / zero)
  4 = CC=1 (low / minus)
  2 = CC=2 (high / plus)
  1 = CC=3 (overflow)

Common mnemonics and their masks:
  BE  / BZ   = 8   (equal / zero)
  BL  / BM   = 4   (low / minus)
  BH  / BP   = 2   (high / plus)
  BO         = 1   (overflow)
  BNE / BNZ  = 7   (not equal / not zero)
  BNL / BNM  = 11  (not low)
  BNH / BNP  = 13  (not high)
  BNO        = 14  (not overflow)
  B          = 15  (unconditional)
"""
from __future__ import annotations

from .base import IInstructionHandler
from core.types import (
    ConversionConfidence,
    ConversionContext,
    ConversionResult,
    ParsedStatement,
    RiskLevel,
)

# Mnemonic → (COBOL condition comment, risk)
_MNEMONIC_MAP: dict[str, tuple[str, RiskLevel]] = {
    "BE":  ("IF equal (CC=0)",          RiskLevel.MEDIUM),
    "BZ":  ("IF zero  (CC=0)",          RiskLevel.MEDIUM),
    "BL":  ("IF low / minus (CC=1)",    RiskLevel.MEDIUM),
    "BM":  ("IF minus (CC=1)",          RiskLevel.MEDIUM),
    "BH":  ("IF high / plus (CC=2)",    RiskLevel.MEDIUM),
    "BP":  ("IF plus  (CC=2)",          RiskLevel.MEDIUM),
    "BO":  ("IF overflow (CC=3)",       RiskLevel.HIGH),
    "BNE": ("IF NOT equal (CC≠0)",      RiskLevel.MEDIUM),
    "BNZ": ("IF NOT zero  (CC≠0)",      RiskLevel.MEDIUM),
    "BNL": ("IF NOT low   (CC≠1)",      RiskLevel.MEDIUM),
    "BNM": ("IF NOT minus (CC≠1)",      RiskLevel.MEDIUM),
    "BNH": ("IF NOT high  (CC≠2)",      RiskLevel.MEDIUM),
    "BNP": ("IF NOT plus  (CC≠2)",      RiskLevel.MEDIUM),
    "BNO": ("IF NOT overflow (CC≠3)",   RiskLevel.HIGH),
}


class BranchHandler(IInstructionHandler):

    HANDLER_NAME = "BranchHandler"

    OPCODES = frozenset({
        # Unconditional
        "B", "BR",
        # Subroutine linkage
        "BAL", "BALR", "BAS", "BASR",
        # Generic conditional
        "BC", "BCR",
        # Mnemonics
        "BE", "BNE", "BH", "BL", "BNH", "BNL",
        "BZ", "BNZ", "BO", "BNO", "BM", "BNM", "BP", "BNP",
        # Loop
        "BCT", "BCTR", "BXH", "BXLE",
        # No-op
        "NOP", "NOPR",
    })

    def _convert(
        self,
        op:   str,
        stmt: ParsedStatement,
        ctx:  ConversionContext,
    ) -> ConversionResult:
        prefix = self._label_prefix(stmt)
        target = self._map_register(self._op(stmt, 0), ctx)   # Map register or label

        # ── No-op ─────────────────────────────────────────────────────────────
        if op in ("NOP", "NOPR"):
            cobol = f"{prefix}      *> NOP — no operation"
            return self._result(stmt, cobol)

        # ── Unconditional branch ───────────────────────────────────────────────
        if op == "B":
            cobol = f"{prefix}       GO TO {target}."
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.HIGH,
                risk       = RiskLevel.LOW,
                warnings   = ["Verify GO TO target is a valid COBOL paragraph name."],
            )
        if op == "BR":
            raw_target = self._op(stmt, 0)
            # BR 14 = return to caller
            if raw_target == "14" or raw_target == "R14":
                cobol = f"{prefix}       GOBACK."
                return self._result(
                    stmt, cobol,
                    confidence = ConversionConfidence.HIGH,
                    risk       = RiskLevel.NONE,
                )
            else:
                cobol = f"{prefix}       *> BR to register {target} — manual conversion needed"
                return self._result(
                    stmt, cobol,
                    confidence = ConversionConfidence.LOW,
                    risk       = RiskLevel.HIGH,
                    warnings   = [f"BR to register {target}: manual conversion required."],
                )

        # ── Subroutine linkage (BAL / BALR / BAS / BASR) ──────────────────────
        if op in ("BAL", "BALR", "BAS", "BASR"):
            link_reg = self._op(stmt, 0)
            tgt      = self._op(stmt, 1)
            cobol = (
                f"{prefix}"
                f"      *> CALL/LINK: {op} R{link_reg} → {tgt}\n"
                f"       PERFORM {tgt}."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.MEDIUM,
                warnings   = [
                    f"{op}: saves return address in register — "
                    "map to PERFORM or CALL depending on target scope."
                ],
            )

        # ── Generic BC/BCR with numeric mask ──────────────────────────────────
        if op in ("BC", "BCR"):
            mask = self._op(stmt, 0)
            tgt  = self._op(stmt, 1)
            cobol = (
                f"{prefix}"
                f"      *> BC mask={mask} → {tgt} — "
                f"add IF (condition) GO TO {tgt} END-IF here."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.LOW,
                risk       = RiskLevel.HIGH,
                warnings   = [f"BC mask {mask}: translate condition code to IF statement."],
            )

        # ── Loop instructions ──────────────────────────────────────────────────
        if op == "BCT":
            ctr = self._op(stmt, 0)
            tgt = self._op(stmt, 1)
            cobol = (
                f"{prefix}"
                f"       SUBTRACT 1 FROM {ctr}.\n"
                f"       IF {ctr} NOT = 0 GO TO {tgt} END-IF."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.MEDIUM,
            )

        if op == "BCTR":
            ctr = self._op(stmt, 0)
            cobol = (
                f"{prefix}"
                f"       SUBTRACT 1 FROM {ctr}."
                f"      *> BCTR: branch if {ctr} ≠ 0 — add GO TO if needed."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = RiskLevel.MEDIUM,
            )

        if op in ("BXH", "BXLE"):
            r1 = self._map_register(self._op(stmt, 0), ctx)
            r2 = self._map_register(self._op(stmt, 1), ctx)
            tgt = self._op(stmt, 2)
            cobol = (
                f"{prefix}"
                f"      *> {op} {r1},{r2},{tgt} — index register loop.\n"
                f"      *> TODO: Implement loop logic: increment/compare index register {r1} "
                f"against limit {r2}, branch to {tgt} if condition met."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.LOW,
                risk       = RiskLevel.HIGH,
                warnings   = [f"{op}: manual conversion required for complex index-register loop."],
            )

        # ── Named condition-code mnemonics ────────────────────────────────────
        if op in _MNEMONIC_MAP:
            condition_text, risk = _MNEMONIC_MAP[op]
            if ctx.last_compare_result:
                r1, r2 = ctx.last_compare_result.split(" ", 1) # r1 is operand 0, r2 is operand 1
                cobol_condition = ""
                if op in ("BE", "BZ"):  # Equal / Zero
                    cobol_condition = f"IF {r1} = {r2}"
                elif op in ("BNE", "BNZ"):  # Not Equal / Not Zero
                    cobol_condition = f"IF {r1} NOT = {r2}"
                elif op in ("BL", "BM"):  # Low / Minus
                    cobol_condition = f"IF {r1} < {r2}"
                elif op in ("BH", "BP"):  # High / Plus
                    cobol_condition = f"IF {r1} > {r2}"
                elif op in ("BNL", "BNM"):  # Not Low / Not Minus
                    cobol_condition = f"IF {r1} NOT < {r2}"
                elif op in ("BNH", "BNP"):  # Not High / Not Plus
                    cobol_condition = f"IF {r1} NOT > {r2}"
                
                if cobol_condition:
                    cobol = (
                        f"{prefix}"
                        f"       {cobol_condition}\n"
                        f"           GO TO {target}\n"
                        f"       END-IF."
                    )
                    # Clear the last_compare_result after use
                    ctx.last_compare_result = None
                    return self._result(stmt, cobol, confidence=ConversionConfidence.HIGH, risk=risk)
            
            # Fallback to TODO if no last_compare_result or unhandled condition
            cobol = (
                f"{prefix}"
                f"      *> {condition_text} GO TO {target}.\n"
                f"      *> TODO: replace with: IF <prev-compare-result> GO TO {target} END-IF."
            )
            return self._result(
                stmt, cobol,
                confidence = ConversionConfidence.MEDIUM,
                risk       = risk,
                warnings   = [
                    f"{op}: conditional branch — link to preceding compare instruction "
                    "and add IF statement."
                ],
            )

        return self._todo(stmt)
