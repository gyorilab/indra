import pytest
from indra.sources.klifs.api import KlifsClient
from indra.sources.klifs.processor import KlifsProcessor
from indra.statements import Inhibition


# ========== Processor Tests (no network) ==========

def test_processor_init():
    """Test processor initializes correctly."""
    processor = KlifsProcessor()
    assert processor.statements == []
    assert processor.bioactivities == []


def test_process_bioactivity():
    """Test processing a bioactivity into a statement."""
    bioactivity = {
        'ligand_id': 123,
        'ligand_name': 'gefitinib',
        'kinase_name': 'EGFR',
    }
    processor = KlifsProcessor(bioactivities=[bioactivity])
    stmts = processor.process_bioactivities()
    
    assert len(stmts) == 1
    assert isinstance(stmts[0], Inhibition)
    assert stmts[0].subj.name == 'gefitinib'
    assert stmts[0].obj.name == 'EGFR'


def test_process_empty():
    """Test processor handles empty input."""
    processor = KlifsProcessor(bioactivities=[])
    stmts = processor.process_bioactivities()
    assert stmts == []


def test_evidence_creation():
    """Test evidence is created with correct source."""
    bioactivity = {
        'ligand_name': 'imatinib',
        'kinase_name': 'ABL1',
    }
    processor = KlifsProcessor(bioactivities=[bioactivity])
    stmts = processor.process_bioactivities()
    
    assert len(stmts) == 1
    assert stmts[0].evidence[0].source_api == 'klifs'


# ========== API Tests (network) ==========

@pytest.mark.webservice
def test_get_kinase_names():
    """Test that kinase names can be retrieved."""
    client = KlifsClient()
    kinase_names = client.get_kinase_names()
    assert isinstance(kinase_names, list)
    assert len(kinase_names) > 0
    assert 'kinase_ID' in kinase_names[0]


@pytest.mark.webservice
def test_get_ligands_list():
    """Test that ligands list can be retrieved."""
    client = KlifsClient()
    ligands = client.get_ligands_list()
    assert isinstance(ligands, list)
    assert len(ligands) > 0


@pytest.mark.webservice
def test_get_kinase_id():
    """Test that kinase ID can be retrieved for EGFR."""
    client = KlifsClient()
    result = client.get_kinase_id('EGFR')
    assert isinstance(result, list)
    assert len(result) > 0


@pytest.mark.webservice
def test_get_egfr_ligands():
    """Test retrieving ligands for a specific kinase."""
    client = KlifsClient()
    egfr_info = client.get_kinase_id('EGFR')
    egfr_id = egfr_info[0]['kinase_ID']
    ligands = client.get_ligands_list(kinase_ids=[egfr_id])
    assert isinstance(ligands, list)
    assert len(ligands) > 0