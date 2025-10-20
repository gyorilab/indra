"""Module containing the implementation of an IndraOntology for the
 general biology use case."""
__all__ = ['bio_ontology', 'BioOntology']

from indra.config import get_config
from .ontology import BioOntology
from .sqlite_ontology import SqliteOntology, DEFAULT_SQLITE_ONTOLOGY
from ..virtual import VirtualOntology

indra_ontology_url = get_config('INDRA_ONTOLOGY_URL')
if indra_ontology_url is None:
    bio_ontology = BioOntology()
elif indra_ontology_url == "sqlite":
    sqlite_ontology_path = get_config("SQLITE_ONTOLOGY_PATH") or DEFAULT_SQLITE_ONTOLOGY
    bio_ontology = SqliteOntology(db_path=sqlite_ontology_path)
else:
    bio_ontology = VirtualOntology(url=indra_ontology_url)
