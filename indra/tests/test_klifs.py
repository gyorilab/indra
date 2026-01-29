import pytest

from indra.sources import klifs
from indra.sources.klifs.processor import KlifsProcessor
from indra.statements import Complex, Inhibition


def make_processor(rec, ligand_id=1, ligand_details=None):
    kp = KlifsProcessor(
        ligand_id=ligand_id,
        ligand_details=ligand_details or {"Name": "TEST_LIG"},
        ligand_pdb=None
    )
    kp.bioactivities = rec
    kp.extract_statements()
    return kp


def test_ic50_produces_inhibition_statement():
    rec = {
        "standard_type": "IC50",
        "standard_value": 12.3,
        "standard_units": "nM",
        "accession": "P00519",
        "pref_name": "ABL1",
    }
    kp = make_processor(rec)

    assert len(kp.statements) == 1
    stmt = kp.statements[0]

    assert isinstance(stmt, Inhibition)
    assert stmt.subj.name == "TEST_LIG"
    assert stmt.obj.db_refs["UP"] == "P00519"

    ev = stmt.evidence[0]
    assert ev.source_api == "klifs"
    assert ev.annotations["standard_type"] == "IC50"
    assert ev.annotations["standard_units"] == "nM"


@pytest.mark.parametrize("standard_type", ["Kd", "KD", "Ki", "KI"])
def test_kd_ki_produce_complex_statement(standard_type):
    rec = {
        "standard_type": standard_type,
        "standard_value": 50.0,
        "standard_units": "nM",
        "accession": "P00519",
        "pref_name": "ABL1",
    }
    kp = make_processor(rec)

    assert len(kp.statements) == 1
    stmt = kp.statements[0]
    assert isinstance(stmt, Complex)


def test_unknown_activity_type_defaults_to_complex():
    rec = {
        "standard_type": "FOO",
        "standard_value": 1.0,
        "standard_units": "nM",
        "accession": "P00519",
        "pref_name": "ABL1",
    }
    kp = make_processor(rec)

    assert len(kp.statements) == 1
    stmt = kp.statements[0]
    assert isinstance(stmt, Complex)

    ev = stmt.evidence[0]
    assert ev.annotations["klifs_interpretation"] == "default_complex_unknown_type"


def test_kinase_agent_grounding_uses_uniprot():
    rec = {
        "standard_type": "IC50",
        "standard_value": 1.0,
        "standard_units": "nM",
        "accession": "P00519",
        "pref_name": "ABL1",
    }
    kp = make_processor(rec)

    assert len(kp.statements) == 1
    stmt = kp.statements[0]
    kinase = stmt.obj
    assert kinase.db_refs["UP"] == "P00519"


def test_ligand_agent_has_expected_db_refs():
    rec = {
        "standard_type": "Kd",
        "standard_value": 10.0,
        "standard_units": "nM",
        "accession": "P00519",
        "pref_name": "ABL1",
    }
    ligand_details = {
        "Name": "LIGX",
        "PDB-code": "STU",
        "InChIKey": "ABCDEFGHIJKLMN",
        "SMILES": "CCO",
    }

    kp = make_processor(rec, ligand_id=123, ligand_details=ligand_details)

    assert len(kp.statements) == 1
    stmt = kp.statements[0]
    assert isinstance(stmt, Complex)

    # Don't rely on ordering in Complex.members
    ligands = [a for a in stmt.members if a.db_refs.get("KLIFS_LIGAND") == "123"]
    assert len(ligands) == 1
    ligand = ligands[0]

    assert ligand.db_refs["KLIFS_LIGAND"] == "123"
    assert ligand.db_refs["PDB"] == "STU"
    assert ligand.db_refs["INCHIKEY"] == "ABCDEFGHIJKLMN"
    assert ligand.db_refs["SMILES"] == "CCO"


def test_process_ligand():
    klifs.process_ligand(ligand_id='k-252a')