import logging
from typing import Any, Dict, Iterable, List, Optional, Union

import requests

logger = logging.getLogger(__name__)


def _comma_list(x: Any) -> Optional[str]:
    """Convert iterables to comma-separated strings for query parameters."""
    if x is None:
        return None
    if isinstance(x, (list, tuple, set)):
        return ",".join(str(i) for i in x)
    return str(x)


class KlifsClient:
    """Thin KLIFS REST client reflecting the Swagger endpoints.

    Parameters
    ----------
    base_url :
        Base URL for KLIFS API (Swagger: schemes + host + basePath).
    timeout :
        Request timeout in seconds.
    session :
        Optional requests session to reuse HTTP connections.
    """

    base_url: str = "https://klifs.net/api/"
    timeout: int = 30

    def send_request(self, endpoint, param=None):
        res = requests.get(
            self.base_url + endpoint,
            params=param,
            timeout=self.timeout,
        )
        return res

    def get_json(self, endpoint, param=None):
        res = self.send_request(endpoint, param)
        res.raise_for_status()
        return res.json()

    def get_content(self, endpoint, param=None):
        res = self.send_request(endpoint, param)
        res.raise_for_status()
        return res.content

    def kinase_groups(self) -> List[str]:
        """GET /kinase_groups"""
        return self.get_json('kinase_groups')

    def kinase_families(
        self,
        kinase_group: Optional[Union[str, Iterable[str]]] = None,
    ) -> List[str]:
        """GET /kinase_families"""
        return self.get_json(
            "kinase_families",
            {"kinase_group": _comma_list(kinase_group)},
        )

    def kinase_names(
        self,
        kinase_group: Optional[Union[str, Iterable[str]]] = None,
        kinase_family: Optional[Union[str, Iterable[str]]] = None,
        species: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """GET /kinase_names"""
        return self.get_json(
            "kinase_names",
            {
                "kinase_group": _comma_list(kinase_group),
                "kinase_family": _comma_list(kinase_family),
                "species": species,
            },
        )

    def kinase_information(
        self,
        kinase_id: Optional[Union[int, Iterable[int]]] = None,
        species: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """GET /kinase_information"""
        return self.get_json(
            "kinase_information",
            {"kinase_ID": _comma_list(kinase_id), "species": species},
        )

    def kinase_id(
        self,
        kinase_name: Union[str, Iterable[str]],
        species: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """GET /kinase_ID"""
        return self.get_json(
            "kinase_ID",
            {"kinase_name": _comma_list(kinase_name), "species": species},
        )

    def ligands_list(
        self,
        kinase_id: Optional[Union[int, Iterable[int]]] = None,
    ) -> List[Dict[str, Any]]:
        """GET /ligands_list"""
        return self.get_json(
            "ligands_list",
            {"kinase_ID": _comma_list(kinase_id)},
        )

    def bioactivity_list_id(self, ligand_id: int) -> List[Dict[str, Any]]:
        """GET /bioactivity_list_id"""
        return self.get_json("bioactivity_list_id", {"ligand_ID": ligand_id})

    def bioactivity_list_pdb(self, ligand_pdb: str) -> List[Dict[str, Any]]:
        """GET /bioactivity_list_pdb"""
        return self.get_json(
            "bioactivity_list_pdb",
            {"ligand_PDB": ligand_pdb},
        )

    def structure_get_pdb_complex(self, structure_id: int) -> bytes:
        """GET /structure_get_pdb_complex (chemical/x-pdb)"""
        return self.get_content(
            "structure_get_pdb_complex",
            {"structure_ID": structure_id},
        )

    def structure_get_complex_mol2(self, structure_id: int) -> bytes:
        """GET /structure_get_complex (chemical/x-mol2)"""
        return self.get_content(
            "structure_get_complex",
            {"structure_ID": structure_id},
        )

    def structure_get_protein_mol2(self, structure_id: int) -> bytes:
        """GET /structure_get_protein (chemical/x-mol2)"""
        return self.get_content(
            "structure_get_protein",
            {"structure_ID": structure_id},
        )

    def structure_get_pocket_mol2(self, structure_id: int) -> bytes:
        """GET /structure_get_pocket (chemical/x-mol2)"""
        return self.get_content(
            "structure_get_pocket",
            {"structure_ID": structure_id},
        )

    def structure_get_ligand_mol2(self, structure_id: int) -> bytes:
        """GET /structure_get_ligand (chemical/x-mol2)"""
        return self.get_content(
            "structure_get_ligand",
            {"structure_ID": structure_id},
        )
