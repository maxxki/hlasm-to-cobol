#!/usr/bin/env python3

"""
maxxki/core/config.py
=====================
Unified configuration management.

Load order (later sources override earlier ones):
  1. Hard-coded defaults  (Config dataclass)
  2. JSON / YAML file     (optional, path via constructor)
  3. Environment vars     MAXXKI_<KEY_UPPER> = value

Thread-safe singleton via double-checked locking.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

_log = logging.getLogger(__name__)


# ============================================================================
# SETTINGS SCHEMA
# ============================================================================

@dataclass
class Config:
    """All configurable knobs in one place.  Sensible defaults throughout."""

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level:         str  = "INFO"
    log_max_bytes:     int  = 50 * 1024 * 1024   # 50 MB
    log_backup_count:  int  = 5

    # ── Parsing ──────────────────────────────────────────────────────────────
    parse_mode:        str  = "HYBRID"   # PLY_AST | REGEX_FALLBACK | HYBRID

    # ── ML back-end ──────────────────────────────────────────────────────────
    enable_ml:         bool = True
    ml_model_name:     str  = "Salesforce/codet5p-770m"
    ml_quantization:   int  = 8          # 4 | 8 | 16 (bits)
    ml_max_memory_gb:  float = 16.0
    ml_cache_dir:      str  = "./models"
    ml_device:         str  = "auto"     # auto | cuda | cpu

    # ── Conversion behaviour ─────────────────────────────────────────────────
    cobol_target:      str  = "COBOL-85"
    generate_copybooks: bool = True
    preserve_comments:  bool = True
    min_ml_confidence:  float = 0.30     # below this → fallback comment

    # ── Performance ──────────────────────────────────────────────────────────
    cache_enabled:     bool = True
    cache_size:        int  = 1_000
    worker_threads:    int  = 4

    # ── Plugin paths (additional directories scanned for plugins) ────────────
    plugin_paths:      List[str] = field(default_factory=list)

    # ── Telemetry (opt-in only) ───────────────────────────────────────────────
    telemetry_enabled: bool = False


# ============================================================================
# MANAGER
# ============================================================================

class ConfigurationManager:
    """
    Thread-safe singleton that owns the single Config instance.

    Quick start
    -----------
    mgr = ConfigurationManager()
    mgr.load("config.json")          # optional
    cfg = mgr.config                 # access settings
    """

    _instance: Optional["ConfigurationManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ConfigurationManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._config: Optional[Config] = None
                    obj._loaded = False
                    cls._instance = obj
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(
        self,
        config_file: Optional[Union[str, Path]] = None,
        *,
        force: bool = False,
    ) -> "ConfigurationManager":
        """
        Load configuration.  Safe to call multiple times; subsequent calls
        are no-ops unless *force=True*.

        Parameters
        ----------
        config_file : Path to a JSON (or YAML) settings file.  Optional.
        force       : Re-load even if already loaded.
        """
        with self._lock:
            if self._loaded and not force:
                return self

            cfg = Config()

            # ── 1. File ───────────────────────────────────────────────────
            if config_file:
                cfg = self._apply_file(cfg, Path(config_file))

            # ── 2. Environment variables ──────────────────────────────────
            cfg = self._apply_env(cfg)

            self._config = cfg
            self._loaded = True
            _log.info("Configuration loaded (file=%s).", config_file)

        return self

    @property
    def config(self) -> Config:
        """Return the active Config.  Calls load() with defaults if needed."""
        if not self._loaded:
            self.load()          # graceful auto-init with pure defaults
        return self._config      # type: ignore[return-value]

    def get(self, key: str, default: Any = None) -> Any:
        """Convenience accessor: ``mgr.get("log_level", "INFO")``."""
        return getattr(self.config, key, default)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_file(cfg: Config, path: Path) -> Config:
        """Overlay settings from a JSON (or minimal YAML) file."""
        if not path.exists():
            _log.warning("Config file '%s' not found — skipping.", path)
            return cfg

        try:
            raw: Dict[str, Any]
            if path.suffix in (".yml", ".yaml"):
                import yaml  # optional dep
                with path.open("r", encoding="utf-8") as fh:
                    raw = yaml.safe_load(fh) or {}
            else:
                with path.open("r", encoding="utf-8") as fh:
                    raw = json.load(fh)

            known = {f.name for f in fields(cfg)}
            for key, value in raw.items():
                if key in known:
                    setattr(cfg, key, value)
                else:
                    _log.warning("Unknown config key '%s' in %s — ignored.", key, path)

            _log.debug("Applied %d settings from '%s'.", len(raw), path)

        except Exception as exc:
            _log.error("Failed to read config file '%s': %s", path, exc)

        return cfg

    @staticmethod
    def _apply_env(cfg: Config) -> Config:
        """Override settings from MAXXKI_<KEY> environment variables."""
        for f in fields(cfg):
            env_name = f"MAXXKI_{f.name.upper()}"
            raw = os.environ.get(env_name)
            if raw is None:
                continue
            try:
                current = getattr(cfg, f.name)
                if isinstance(current, bool):
                    value: Any = raw.lower() in ("1", "true", "yes", "y", "t")
                elif isinstance(current, int):
                    value = int(raw)
                elif isinstance(current, float):
                    value = float(raw)
                elif isinstance(current, list):
                    value = [item.strip() for item in raw.split(",") if item.strip()]
                else:
                    value = raw
                setattr(cfg, f.name, value)
                _log.debug("Env override: %s = %r", f.name, value)
            except (ValueError, TypeError) as exc:
                _log.error(
                    "Invalid env var %s=%r (%s) — keeping default.", env_name, raw, exc
                )
        return cfg
