from typing import Any, Dict, Optional

from .processor import KlifsProcessor

__all__ = ["process_kinase"]



def process_kinase(
    kinase_gene_name: Optional[int] = None,
    kinase_uniprot: Optional[str] = None,
) -> KlifsProcessor:
    """

    Returns
    -------
    :
        A KlifsProcessor instance with extracted INDRA Statements available
        in its `statements` attribute.
    """
    kp = KlifsProcessor(
        kinase_gene_name=kinase_gene_name,
        kinase_uniprot=kinase_uniprot,
    )
    kp.extract_statements()
    return kp