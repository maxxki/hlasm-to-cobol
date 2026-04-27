#!/usr/bin/env python3

"""
maxxki/core/ml_bridge.py
========================
IMLConverter implementation.

Two modes
---------
DummyMLConverter   — always reports is_available()=False.
                     Safe placeholder; lets the stack run end-to-end
                     without any ML dependency.

HuggingFaceMLConverter — real CodeT5+ back-end (lazy-loaded).
                         Only activates when transformers + torch are
                         installed AND Config.enable_ml is True.

The Orchestrator only ever calls IMLConverter — it never imports
either class directly.  Bootstrap decides which one to register.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .types import (
    ConversionConfidence,
    ConversionContext,
    ConversionResult,
    IMLConverter,
    ParsedStatement,
    RiskLevel,
    StatementType,
)

_log = logging.getLogger(__name__)


# ============================================================================
# DUMMY  (always safe, zero deps)
# ============================================================================

class DummyMLConverter(IMLConverter):
    """
    Stand-in converter that does nothing.
    Registered when ML is disabled or transformers are not installed.
    Keeps the Orchestrator's ML-fallback branch reachable but inert.
    """

    def is_available(self) -> bool:
        return False

    def convert(
        self,
        statement: ParsedStatement,
        context:   ConversionContext,
    ) -> Optional[ConversionResult]:
        # Never called because is_available() → False, but
        # implement cleanly for completeness.
        return None


# ============================================================================
# HUGGINGFACE BACK-END  (real ML, optional dep)
# ============================================================================

class HuggingFaceMLConverter(IMLConverter):
    """
    CodeT5+ powered HLASM → COBOL converter.

    Lazy model loading: the first convert() call triggers the download /
    cache load.  Subsequent calls reuse the in-memory model.

    Config keys consumed (via ConversionContext.options or direct cfg):
        ml_model_name     : HuggingFace model id
        ml_quantization   : 4 | 8 | 16
        ml_max_memory_gb  : float
        ml_cache_dir      : local cache path
        ml_device         : "auto" | "cuda" | "cpu"
        min_ml_confidence : float  (0.0–1.0)
    """

    def __init__(self, cfg_options: dict) -> None:
        self._opts     = cfg_options
        self._model    = None
        self._tokenizer = None
        self._ready    = False
        self._load_attempted = False

    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        if self._ready:
            return True
        if self._load_attempted:
            return False
        return self._try_load()

    def convert(
        self,
        statement: ParsedStatement,
        context:   ConversionContext,
    ) -> Optional[ConversionResult]:
        if not self.is_available():
            return None

        t0 = time.perf_counter()
        try:
            cobol = self._infer(statement.raw_text)
        except Exception as exc:
            _log.error("ML inference failed: %s", exc)
            return None

        duration_ms = (time.perf_counter() - t0) * 1_000
        confidence  = self._estimate_confidence(cobol, statement)

        return ConversionResult(
            original_statement  = statement.raw_text,
            converted_statement = cobol,
            statement_type      = statement.statement_type,
            confidence          = confidence,
            plugin_name         = "HuggingFaceMLConverter",
            risk_level          = (
                RiskLevel.MEDIUM
                if confidence == ConversionConfidence.MEDIUM
                else RiskLevel.HIGH
            ),
            processing_time_ms  = duration_ms,
            warnings            = ["ML-generated — manual review recommended."],
            source              = statement,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _try_load(self) -> bool:
        self._load_attempted = True
        try:
            from transformers import AutoTokenizer, AutoModelForSeq2SeqLM  # type: ignore
            import torch  # type: ignore
        except ImportError:
            _log.info("transformers / torch not installed — ML bridge inactive.")
            return False

        model_name  = self._opts.get("ml_model_name",    "Salesforce/codet5p-770m")
        cache_dir   = self._opts.get("ml_cache_dir",     "./models")
        device_pref = self._opts.get("ml_device",        "auto")
        quant_bits  = int(self._opts.get("ml_quantization", 8))

        _log.info("Loading ML model '%s' (q%d)…", model_name, quant_bits)
        try:
            load_kwargs: dict = {"cache_dir": cache_dir}

            if quant_bits == 8:
                load_kwargs["load_in_8bit"] = True
            elif quant_bits == 4:
                load_kwargs["load_in_4bit"] = True

            if device_pref == "auto":
                load_kwargs["device_map"] = "auto"
            elif device_pref != "cpu":
                load_kwargs["device_map"] = device_pref

            self._tokenizer = AutoTokenizer.from_pretrained(model_name, **{"cache_dir": cache_dir})
            self._model     = AutoModelForSeq2SeqLM.from_pretrained(model_name, **load_kwargs)
            self._ready     = True
            _log.info("ML model loaded successfully.")
            return True

        except Exception as exc:
            _log.error("Failed to load ML model: %s", exc)
            return False

    def _infer(self, raw_text: str) -> str:
        prompt = (
            f"Convert the following IBM HLASM assembly statement to COBOL-85.\n"
            f"HLASM: {raw_text}\nCOBOL:"
        )
        inputs  = self._tokenizer(prompt, return_tensors="pt", truncation=True, max_length=256)
        outputs = self._model.generate(**inputs, max_new_tokens=128, num_beams=4)
        return self._tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

    @staticmethod
    def _estimate_confidence(
        cobol: str,
        stmt:  ParsedStatement,
    ) -> ConversionConfidence:
        """Heuristic: longer, structured output → higher confidence."""
        if not cobol or cobol.startswith("*>"):
            return ConversionConfidence.UNKNOWN
        words = cobol.split()
        if len(words) >= 4:
            return ConversionConfidence.MEDIUM
        return ConversionConfidence.LOW
