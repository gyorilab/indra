# indra/sources/klifs/api.py

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Union

from .client import KlifsClient
from .processor import KlifsProcessor

__all__ = [
    "get_kinase_groups",
    "get_kinase_families",
    "get_kinase_names",
    "get_kinase_information",
    "get_kinase_id",
    "get_ligands_list",
    "get_bioactivities_for_ligand",
    "process_bioactivities_for_ligand",
]

_default_client = KlifsClient()


# -----------------
# Kinase Information
# -----------------
def get_kinase_groups(client: KlifsClient = _default_client) -> List[str]:
    """Get the list of kinase groups from KLIFS.

    Swagger mapping: GET /kinase_groups
    """
    return client.kinase_groups()


def get_kinase_families(
    kinase_group: Optional[Union[str, Iterable[str]]] = None,
    client: KlifsClient = _default_client,
) -> List[str]:
    """Get the list of kinase families from KLIFS.

    Swagger mapping: GET /kinase_families
    """
    return client.kinase_families(kinase_group=kinase_group)


def get_kinase_names(
    kinase_group: Optional[Union[str, Iterable[str]]] = None,
    kinase_family: Optional[Union[str, Iterable[str]]] = None,
    species: Optional[str] = None,
    client: KlifsClient = _default_client,
) -> List[Dict[str, Any]]:
    """Get kinase names (HGNC gene symbols) and associated IDs from KLIFS.

    Swagger mapping: GET /kinase_names
    """
    return client.kinase_names(
        kinase_group=kinase_group,
        kinase_family=kinase_family,
        species=species,
    )


def get_kinase_information(
    kinase_ids: Optional[Union[int, Iterable[int]]] = None,
    species: Optional[str] = None,
    client: KlifsClient = _default_client,
) -> List[Dict[str, Any]]:
    """Get kinase information records from KLIFS.

    Swagger mapping: GET /kinase_information
    """
    return client.kinase_information(kinase_id=kinase_ids, species=species)


def get_kinase_id(
    kinase_name: Union[str, Iterable[str]],
    species: Optional[str] = None,
    client: KlifsClient = _default_client,
) -> List[int]:
    """Resolve one or more kinase names to KLIFS kinase_ID integers.

    Swagger mapping: GET /kinase_ID

    Notes
    -----
    The Swagger endpoint returns KinaseInformation-like records; this helper
    extracts and returns only the `kinase_ID` integer(s).
    """
    rows = client.kinase_id(kinase_name=kinase_name, species=species)
    out: List[int] = []
    for row in rows or []:
        kid = row.get("kinase_ID")
        if kid is not None:
            out.append(int(kid))
    return out


# -----------------
# Ligand Information
# -----------------
def get_ligands_list(
    kinase_id: Optional[Union[int, Iterable[int]]] = None,
    client: KlifsClient = _default_client,
) -> List[Dict[str, Any]]:
    """Get ligandDetails records from KLIFS.

    Swagger mapping: GET /ligands_list
    """
    return client.ligands_list(kinase_id=kinase_id)


# -----------------
# Bioactivities (IC50, Kd, Ki, etc.)
# -----------------
def get_bioactivities_for_ligand(
    ligand_id: Optional[int] = None,
    ligand_pdb: Optional[str] = None,
    client: KlifsClient = _default_client,
) -> List[Dict[str, Any]]:
    """Get bioactivity records for a ligand from KLIFS.

    KLIFS exposes two separate Swagger endpoints that return the same *kind* of
    record (BioactivityDetails) for a ligand, differing only by identifier:

    - GET /bioactivity_list_id   (use when `ligand_id` is provided)
    - GET /bioactivity_list_pdb  (use when `ligand_pdb` is provided)

    This convenience function dispatches to the correct endpoint.

    Raises
    ------
    ValueError
        If neither `ligand_id` nor `ligand_pdb` is provided.
    """
    if ligand_id is not None:
        return client.bioactivity_list_id(ligand_id)
    if ligand_pdb is not None:
        return client.bioactivity_list_pdb(ligand_pdb)
    raise ValueError("Provide ligand_id or ligand_pdb.")


def process_bioactivities_for_ligand(
    ligand_id: Optional[int] = None,
    ligand_pdb: Optional[str] = None,
    ligand_details: Optional[Dict[str, Any]] = None,
    client: KlifsClient = _default_client,
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
    bio = get_bioactivities_for_ligand(
        ligand_id=ligand_id,
        ligand_pdb=ligand_pdb,
        client=client,
    )
    kp = KlifsProcessor(
        bioactivities=bio,
        ligand_id=ligand_id,
        ligand_pdb=ligand_pdb,
        ligand_details=ligand_details,
    )
    kp.extract_statements()
    return kp