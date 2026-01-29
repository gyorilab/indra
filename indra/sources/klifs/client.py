# indra/sources/klifs/client.py

from __future__ import annotations

import logging
from dataclasses import dataclass
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


@dataclass
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

    base_url: str = "https://klifs.net/api"
    timeout: int = 30
    session: Optional[requests.Session] = None

    def _session(self) -> requests.Session:
        """Get a cached requests.Session for connection reuse."""
        if self.session is None:
            self.session = requests.Session()
        return self.session

    def _get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        sess = self._session()
        url = self.base_url + path
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        logger.debug("KLIFS GET %s params=%s", url, clean_params)
        res = sess.get(url, params=clean_params, timeout=self.timeout)
        res.raise_for_status()
        return res

    def _get_json(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        res = self._get(path, params=params)
        return res.json()

    def _get_bytes(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        res = self._get(path, params=params)
        return res.content

    # -----------------
    # Information (Swagger paths)
    # -----------------
    def kinase_groups(self) -> List[str]:
        """GET /kinase_groups"""
        return self._get_json("/kinase_groups")

    def kinase_families(
        self,
        kinase_group: Optional[Union[str, Iterable[str]]] = None,
    ) -> List[str]:
        """GET /kinase_families"""
        return self._get_json(
            "/kinase_families",
            {"kinase_group": _comma_list(kinase_group)},
        )

    def kinase_names(
        self,
        kinase_group: Optional[Union[str, Iterable[str]]] = None,
        kinase_family: Optional[Union[str, Iterable[str]]] = None,
        species: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """GET /kinase_names"""
        return self._get_json(
            "/kinase_names",
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
        return self._get_json(
            "/kinase_information",
            {"kinase_ID": _comma_list(kinase_id), "species": species},
        )

    def kinase_id(
        self,
        kinase_name: Union[str, Iterable[str]],
        species: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """GET /kinase_ID"""
        return self._get_json(
            "/kinase_ID",
            {"kinase_name": _comma_list(kinase_name), "species": species},
        )

    # -----------------
    # Ligands (Swagger paths)
    # -----------------
    def ligands_list(
        self,
        kinase_id: Optional[Union[int, Iterable[int]]] = None,
    ) -> List[Dict[str, Any]]:
        """GET /ligands_list"""
        return self._get_json(
            "/ligands_list",
            {"kinase_ID": _comma_list(kinase_id)},
        )

    def bioactivity_list_id(self, ligand_id: int) -> List[Dict[str, Any]]:
        """GET /bioactivity_list_id"""
        return self._get_json("/bioactivity_list_id", {"ligand_ID": ligand_id})

    def bioactivity_list_pdb(self, ligand_pdb: str) -> List[Dict[str, Any]]:
        """GET /bioactivity_list_pdb"""
        return self._get_json(
            "/bioactivity_list_pdb",
            {"ligand_PDB": ligand_pdb},
        )

    # -----------------
    # File-return endpoints (Swagger paths; bytes)
    # -----------------
    def structure_get_pdb_complex(self, structure_id: int) -> bytes:
        """GET /structure_get_pdb_complex (chemical/x-pdb)"""
        return self._get_bytes(
            "/structure_get_pdb_complex",
            {"structure_ID": structure_id},
        )

    def structure_get_complex_mol2(self, structure_id: int) -> bytes:
        """GET /structure_get_complex (chemical/x-mol2)"""
        return self._get_bytes(
            "/structure_get_complex",
            {"structure_ID": structure_id},
        )

    def structure_get_protein_mol2(self, structure_id: int) -> bytes:
        """GET /structure_get_protein (chemical/x-mol2)"""
        return self._get_bytes(
            "/structure_get_protein",
            {"structure_ID": structure_id},
        )

    def structure_get_pocket_mol2(self, structure_id: int) -> bytes:
        """GET /structure_get_pocket (chemical/x-mol2)"""
        return self._get_bytes(
            "/structure_get_pocket",
            {"structure_ID": structure_id},
        )

    def structure_get_ligand_mol2(self, structure_id: int) -> bytes:
        """GET /structure_get_ligand (chemical/x-mol2)"""
        return self._get_bytes(
            "/structure_get_ligand",
            {"structure_ID": structure_id},
        )
