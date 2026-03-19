"""
Domain pack system for Market-Zero pipeline engine.

A DomainPack declares all domain-specific configuration in one place:
entity schemas, link rules, field mappings, resolution config, and
validation rules. The pipeline engine reads from the active domain pack
instead of hardcoded values.

This makes the pipeline reusable across domains:
  - domain.pharma  → pharma intelligence (Market-Zero)
  - domain.genomics → omics data curation (future)
  - domain.labdata  → ELN/instrument data (future)
"""

from domain.schema import (
    DomainPack,
    EntitySchema,
    FieldMapping,
    LinkRule,
    OntologyConfig,
    SourceConfig,
)
from domain.registry import DomainRegistry

__all__ = [
    "DomainPack",
    "DomainRegistry",
    "EntitySchema",
    "FieldMapping",
    "LinkRule",
    "OntologyConfig",
    "SourceConfig",
]
