from typing import Any, Dict, Optional

from .processor import KlifsProcessor

__all__ = ["process_ligand"]



def process_ligand(
    ligand_id: Optional[int] = None,
    ligand_pdb: Optional[str] = None,
    ligand_details: Optional[Dict[str, Any]] = None,
) -> KlifsProcessor:
    """Fetch ligand bioactivities and convert them into INDRA Statements.

    NOTE: This is meant to be analogous to process_from_web style functions in other INDRA sources

    This is a standard INDRA convenience pipeline that combines:
    1) A Swagger fetch via one of:
       - GET /bioactivity_list_id
       - GET /bioactivity_list_pdb
    2) INDRA-side transformation via KlifsProcessor

    Returns
    -------
    :
        A KlifsProcessor instance with extracted INDRA Statements available
        in its `statements` attribute.
    """
    kp = KlifsProcessor(
        ligand_id=ligand_id,
        ligand_pdb=ligand_pdb,
        ligand_details=ligand_details,
    )
    kp.extract_statements()
    return kp