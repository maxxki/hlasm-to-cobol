#!/usr/bin/env python3

"""
maxxki/core/registry.py
=======================
Thread-safe Inversion-of-Control container.

Design decisions
----------------
* Singleton per service name (one live instance per key).
* Factory support: register a callable that is invoked lazily on first get().
* Graceful shutdown: every registered service that exposes .shutdown() is
  called in reverse-registration order when shutdown_all() is invoked.
* No external dependencies — only stdlib.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

_log = logging.getLogger(__name__)


class ServiceRegistry:
    """
    Central IoC registry.

    Usage
    -----
    # Register an already-constructed instance:
    ServiceRegistry.register("parser", MyParser())

    # Register a factory (lazy construction):
    ServiceRegistry.register("config", ConfigManager, factory=True)

    # Retrieve (constructs lazily if factory was registered):
    parser = ServiceRegistry.get("parser")

    # Teardown:
    ServiceRegistry.shutdown_all()
    """

    _lock:     threading.RLock              = threading.RLock()
    _services: Dict[str, Any]              = {}
    _factories: Dict[str, Callable]        = {}
    _order:    List[str]                   = []   # registration order
    _metadata: Dict[str, Dict[str, Any]]   = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def register(
        cls,
        name:     str,
        service:  Any,
        *,
        factory:  bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register *service* under *name*.

        Parameters
        ----------
        name    : Unique service identifier.
        service : Either a live instance (factory=False) or a callable
                  that returns the instance (factory=True).
        factory : If True, *service* is treated as a zero-argument factory
                  and the instance is constructed on first get().
        metadata: Optional dict stored alongside the service for introspection.
        """
        with cls._lock:
            if factory:
                if not callable(service):
                    raise TypeError(f"Factory for '{name}' must be callable.")
                cls._factories[name] = service
            else:
                cls._services[name] = service

            if name not in cls._order:
                cls._order.append(name)

            cls._metadata[name] = {
                "registered_at": datetime.now().isoformat(),
                "factory":       factory,
                "type":          service.__name__ if factory else type(service).__name__,
                **(metadata or {}),
            }
            _log.debug("Registered service '%s' (factory=%s).", name, factory)

    @classmethod
    def get(cls, name: str) -> Any:
        """
        Retrieve the service registered under *name*.
        Raises KeyError if no service (or factory) is registered.
        """
        with cls._lock:
            # Already instantiated?
            if name in cls._services:
                return cls._services[name]

            # Lazy factory?
            if name in cls._factories:
                _log.debug("Constructing service '%s' from factory.", name)
                instance = cls._factories.pop(name)()
                cls._services[name] = instance
                cls._metadata[name]["constructed_at"] = datetime.now().isoformat()
                return instance

            raise KeyError(
                f"Service '{name}' is not registered. "
                f"Available: {list(cls._services) + list(cls._factories)}"
            )

    @classmethod
    def has(cls, name: str) -> bool:
        """Return True iff *name* is registered (instantiated or as factory)."""
        with cls._lock:
            return name in cls._services or name in cls._factories

    @classmethod
    def get_or_none(cls, name: str) -> Optional[Any]:
        """Like get(), but returns None instead of raising."""
        try:
            return cls.get(name)
        except KeyError:
            return None

    @classmethod
    def info(cls) -> Dict[str, Dict[str, Any]]:
        """Return a copy of the metadata dict for introspection / health checks."""
        with cls._lock:
            return {k: dict(v) for k, v in cls._metadata.items()}

    @classmethod
    def shutdown_all(cls) -> None:
        """
        Call .shutdown() on every registered service that exposes it,
        in reverse-registration order. Then clear all internal state.
        """
        with cls._lock:
            for name in reversed(cls._order):
                service = cls._services.get(name)
                if service is not None and hasattr(service, "shutdown"):
                    try:
                        _log.info("Shutting down service '%s'…", name)
                        service.shutdown()
                    except Exception as exc:
                        _log.error(
                            "Error shutting down service '%s': %s", name, exc
                        )
            cls._services.clear()
            cls._factories.clear()
            cls._order.clear()
            cls._metadata.clear()
            _log.info("ServiceRegistry cleared.")
