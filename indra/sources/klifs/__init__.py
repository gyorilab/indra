"""INDRA source integration for KLIFS (Kinase–Ligand Interaction Fingerprints
and Structures).

Public API is primarily a thin, Swagger-mirroring layer defined in .api.
"""

from .api import process_ligand

__all__ = ["process_ligand"]
