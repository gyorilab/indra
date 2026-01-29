# indra/sources/klifs/processor.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from indra.statements import Agent, Complex, Evidence, Inhibition, Statement

import html


def _safe_str(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = html.unescape(str(x).strip())
    return s or None


def _norm_measurement_type(x: Any) -> Optional[str]:
    """Normalize measurement type strings (e.g., 'IC50', 'Kd', 'Ki')."""
    s = _safe_str(x)
    if s is None:
        return None
    return s.upper().replace(" ", "")


@dataclass
class KlifsProcessor:
    """Processor for turning KLIFS BioactivityDetails into INDRA Statements.

    Current focus
    -------------
    Convert KLIFS BioactivityDetails records (from /bioactivity_list_id or
    /bioactivity_list_pdb) into INDRA Statements.

    Interpretation
    --------------
    KLIFS provides assay measurements (IC50/Ki/Kd/etc.), not explicit claims.
    This processor interprets:
    - IC50 measurements as evidence for Inhibition(chemical, kinase)
    - Ki/Kd measurements as evidence for Complex(chemical, kinase)

    Any other/unknown measurement types default to Complex with an explicit
    annotation describing the fallback behavior.

    All quantitative fields are preserved in Evidence annotations.
    """

    bioactivities: List[Dict[str, Any]]
    ligand_id: Optional[int] = None
    ligand_pdb: Optional[str] = None
    ligand_details: Optional[Dict[str, Any]] = None

    statements: List[Statement] = field(default_factory=list)

    def extract_statements(self) -> None:
        """Extract INDRA Statements into `self.statements`."""
        self.statements = []
        ligand = self._make_ligand_agent()
        if ligand is None:
            return

        for rec in self.bioactivities or []:
            kinase = self._make_kinase_agent(rec)
            if kinase is None:
                continue

            ev = Evidence(
                source_api="klifs",
                annotations=self._make_annotations(rec),
            )

            stmt = self._make_statement(ligand, kinase, rec, ev)
            if stmt is not None:
                self.statements.append(stmt)

    def _make_statement(
        self,
        ligand: Agent,
        kinase: Agent,
        rec: Dict[str, Any],
        ev: Evidence,
    ) -> Optional[Statement]:
        stype = _norm_measurement_type(rec.get("standard_type"))

        if stype == "IC50":
            return Inhibition(ligand, kinase, evidence=[ev])

        if stype in {"KD", "KI"}:
            return Complex([ligand, kinase], evidence=[ev])

        # Default: treat as binding/association, but keep type annotated
        ev.annotations["klifs_interpretation"] = "default_complex_unknown_type"
        return Complex([ligand, kinase], evidence=[ev])

    def _make_ligand_agent(self) -> Optional[Agent]:
        ld = self.ligand_details or {}

        name = (
            _safe_str(ld.get("Name"))
            or _safe_str(ld.get("PDB-code"))
            or (f"KLIFS_LIGAND_{self.ligand_id}" if self.ligand_id is not None else None)
            or (_safe_str(self.ligand_pdb) if self.ligand_pdb else None)
        )
        if name is None:
            return None

        db_refs: Dict[str, Any] = {}
        inchikey = _safe_str(ld.get("InChIKey"))
        smiles = _safe_str(ld.get("SMILES"))
        pdb_code = _safe_str(ld.get("PDB-code"))

        if self.ligand_id is not None:
            db_refs["KLIFS_LIGAND"] = str(self.ligand_id)
        if pdb_code is not None:
            db_refs["PDB"] = pdb_code
        if inchikey is not None:
            db_refs["INCHIKEY"] = inchikey
        if smiles is not None:
            db_refs["SMILES"] = smiles

        return Agent(name, db_refs=db_refs)

    def _make_kinase_agent(self, rec: Dict[str, Any]) -> Optional[Agent]:
        accession = _safe_str(rec.get("accession"))
        name = _safe_str(rec.get("pref_name")) or accession
        if name is None:
            return None

        db_refs: Dict[str, Any] = {}
        if accession is not None:
            db_refs["UP"] = accession
        return Agent(name, db_refs=db_refs)

    def _make_annotations(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        ann: Dict[str, Any] = {
            "klifs_ligand_id": self.ligand_id,
            "klifs_ligand_pdb": self.ligand_pdb,
        }

        for k in [
            "standard_type",
            "standard_relation",
            "standard_value",
            "standard_units",
            "pchembl_value",
            "organism",
            "pref_name",
            "accession",
        ]:
            v = rec.get(k)
            if v is not None and v != "":
                ann[k] = v

        return ann
