"""KLIFS kinase-inhibitor database integration for INDRA.

KLIFS (Kinase-Ligand Interaction Fingerprints and Structures) is a database
that collects and disseminates structural kinase-inhibitor interaction data.
"""

from .api import KlifsClient
from .processor import KlifsProcessor
import logging

logger = logging.getLogger(__name__)

def process_from_web(kinase_names=None, include_drugs=True, min_activity=None):
    """Process KLIFS data from the web API into INDRA statements.
    
    Parameters
    ----------
    kinase_names : list or str, optional
        Specific kinase(s) to process. If None, processes all.
    include_drugs : bool
        Whether to include approved drug information
    min_activity : float, optional
        Minimum activity threshold (e.g., pIC50 > 6)
    
    Returns
    -------
    list
        List of INDRA statements
    """
    client = KlifsClient()
    
    # Convert single kinase to list
    if isinstance(kinase_names, str):
        kinase_names = [kinase_names]
    
    # Collect data
    all_bioactivities = []
    all_ligands = []
    all_kinases = []
    
    if kinase_names:
        # Process specific kinases
        for kinase_name in kinase_names:
            logger.info(f'Fetching data for {kinase_name}')
            
            # Get bioactivities for this kinase
            bioactivities = client.get_bioactivities(
                kinase_name=kinase_name,
                min_activity=min_activity
            )
            all_bioactivities.extend(bioactivities)
            
            # Get ligands for this kinase
            ligands = client.get_ligands_list(kinase_name=kinase_name)
            all_ligands.extend(ligands)
            
            # Get kinase info
            kinase_info = client.get_kinase_info(kinase_name=kinase_name)
            all_kinases.extend(kinase_info)
    else:
        # Get all data
        logger.info('Fetching all KLIFS data (this may take a while)')
        all_bioactivities = client.get_bioactivities(min_activity=min_activity)
        all_ligands = client.get_ligands_list()
        all_kinases = client.get_kinase_info()
    
    # Get drug info if requested
    drugs = []
    if include_drugs:
        drugs = client.get_drugs()
    
    # Remove duplicates from ligands and kinases
    seen_ligands = set()
    unique_ligands = []
    for ligand in all_ligands:
        lig_id = ligand.get('ligand_id') or ligand.get('id')
        if lig_id and lig_id not in seen_ligands:
            seen_ligands.add(lig_id)
            unique_ligands.append(ligand)
    
    seen_kinases = set()
    unique_kinases = []
    for kinase in all_kinases:
        kinase_name = kinase.get('kinase_name') or kinase.get('name')
        if kinase_name and kinase_name not in seen_kinases:
            seen_kinases.add(kinase_name)
            unique_kinases.append(kinase)
    
    logger.info(f'Retrieved {len(all_bioactivities)} bioactivities, '
                f'{len(unique_ligands)} ligands, {len(unique_kinases)} kinases')
    
    # Process into statements
    processor = KlifsProcessor(
        bioactivities=all_bioactivities,
        ligands=unique_ligands,
        kinases=unique_kinases,
        drugs=drugs
    )
    
    statements = processor.process_bioactivities()
    
    return statements


def process_from_dump(bioactivities_file=None, ligands_file=None, 
                     kinases_file=None, drugs_file=None):
    """Process KLIFS data from downloaded JSON files.
    
    Parameters
    ----------
    bioactivities_file : str
        Path to bioactivities JSON file
    ligands_file : str
        Path to ligands JSON file
    kinases_file : str
        Path to kinases JSON file  
    drugs_file : str, optional
        Path to drugs JSON file
        
    Returns
    -------
    list
        List of INDRA statements
    """
    import json
    
    bioactivities = []
    ligands = []
    kinases = []
    drugs = []
    
    if bioactivities_file:
        with open(bioactivities_file) as f:
            bioactivities = json.load(f)
    
    if ligands_file:
        with open(ligands_file) as f:
            ligands = json.load(f)
    
    if kinases_file:
        with open(kinases_file) as f:
            kinases = json.load(f)
    
    if drugs_file:
        with open(drugs_file) as f:
            drugs = json.load(f)
    
    processor = KlifsProcessor(
        bioactivities=bioactivities,
        ligands=ligands,
        kinases=kinases,
        drugs=drugs
    )
    
    statements = processor.process_bioactivities()
    
    return statements