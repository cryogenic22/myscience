"""
Domain pack registry — loads and provides access to domain packs.

Usage:
    from domain.registry import DomainRegistry

    # Register a domain pack
    DomainRegistry.register(pharma_pack)

    # Get the active domain pack
    pack = DomainRegistry.get("pharma")

    # Or get the default (first registered)
    pack = DomainRegistry.active()
"""

from __future__ import annotations

import logging
from typing import Optional

from domain.schema import DomainPack

logger = logging.getLogger(__name__)


class DomainRegistry:
    """
    Singleton registry for domain packs.

    The pipeline reads from DomainRegistry.active() to get all
    domain-specific configuration.
    """

    _packs: dict[str, DomainPack] = {}
    _active: Optional[str] = None

    @classmethod
    def register(cls, pack: DomainPack, set_active: bool = True) -> None:
        """Register a domain pack. Optionally set it as the active pack."""
        cls._packs[pack.name] = pack
        logger.info("Registered domain pack: %s v%s", pack.name, pack.version)
        if set_active or cls._active is None:
            cls._active = pack.name
            logger.info("Active domain pack: %s", pack.name)

    @classmethod
    def get(cls, name: str) -> Optional[DomainPack]:
        """Get a domain pack by name."""
        return cls._packs.get(name)

    @classmethod
    def active(cls) -> Optional[DomainPack]:
        """Get the currently active domain pack."""
        if cls._active:
            return cls._packs.get(cls._active)
        return None

    @classmethod
    def set_active(cls, name: str) -> None:
        """Set the active domain pack by name."""
        if name not in cls._packs:
            raise ValueError(f"Domain pack '{name}' not registered")
        cls._active = name

    @classmethod
    def list_packs(cls) -> list[str]:
        """List registered domain pack names."""
        return list(cls._packs.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registered packs. Primarily for testing."""
        cls._packs.clear()
        cls._active = None
