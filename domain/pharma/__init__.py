"""
Pharma domain pack for Market-Zero.

This is the first domain pack — it extracts all pharma-specific configuration
from the pipeline codebase into a single declarative module.

Usage:
    from domain.pharma import get_pharma_pack
    from domain.registry import DomainRegistry

    DomainRegistry.register(get_pharma_pack())
"""

from domain.pharma.pack import get_pharma_pack

__all__ = ["get_pharma_pack"]
