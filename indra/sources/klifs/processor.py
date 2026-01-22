"""Processor for KLIFS kinase-inhibitor data."""

from typing import List, Dict, Optional
import logging
from collections import defaultdict

from indra.statements import Inhibition, Agent, Evidence
from indra.databases import hgnc_client, chebi_client, uniprot_client

logger = logging.getLogger(__name__)

class KlifsProcessor:
    """Process KLIFS data into INDRA statements.
    
    Parameters
    ----------
    bioactivities : list
        List of bioactivity data from KLIFS
    ligands : list
        List of ligand information from KLIFS  
    kinases : list
        List of kinase information from KLIFS
    drugs : list
        List of approved drugs from KLIFS
    """
    
    def __init__(self, bioactivities=None, ligands=None, kinases=None, drugs=None):
        self.bioactivities = bioactivities or []
        self.ligands = ligands or []
        self.kinases = kinases or []
        self.drugs = drugs or []
        self.statements = []
        
        # Build lookup tables
        self._build_lookups()
        
    def _build_lookups(self):
        """Build lookup dictionaries for efficient processing."""
        # Ligand ID to ligand info
        self.ligand_lookup = {}
        for ligand in self.ligands:
            lig_id = ligand.get('ligand_id') or ligand.get('id')
            if lig_id:
                self.ligand_lookup[lig_id] = ligand
        
        # Kinase name to kinase info  
        self.kinase_lookup = {}
        for kinase in self.kinases:
            name = kinase.get('kinase_name') or kinase.get('name')
            if name:
                self.kinase_lookup[name] = kinase
        
        # Drug name to drug info
        self.drug_lookup = {}
        for drug in self.drugs:
            name = drug.get('drug_name') or drug.get('name')
            if name:
                self.drug_lookup[name.lower()] = drug
    
    def process_bioactivities(self):
        """Process bioactivity data into Inhibition statements.
        
        Returns
        -------
        list
            List of INDRA statements
        """
        logger.info(f'Processing {len(self.bioactivities)} bioactivities')
        
        for activity in self.bioactivities:
            stmt = self._process_single_activity(activity)
            if stmt:
                self.statements.append(stmt)
        
        logger.info(f'Generated {len(self.statements)} statements')
        return self.statements
    
    def _process_single_activity(self, activity: Dict) -> Optional[Inhibition]:
        """Process a single bioactivity entry into a statement.
        
        Parameters
        ----------
        activity : dict
            Bioactivity data from KLIFS
            
        Returns
        -------
        Inhibition or None
            INDRA statement if processing successful
        """
        # Get ligand/drug agent
        ligand_agent = self._make_ligand_agent(activity)
        if not ligand_agent:
            return None
            
        # Get kinase agent
        kinase_agent = self._make_kinase_agent(activity)
        if not kinase_agent:
            return None
        
        # Create evidence
        evidence = self._make_evidence(activity)
        
        # Create inhibition statement
        # (Most kinase-ligand interactions in KLIFS are inhibitory)
        stmt = Inhibition(ligand_agent, kinase_agent, evidence=[evidence])
        
        return stmt
    
    def _make_ligand_agent(self, activity: Dict) -> Optional[Agent]:
        """Create an Agent for the ligand/drug.
        
        Parameters
        ----------
        activity : dict
            Activity data containing ligand information
            
        Returns
        -------
        Agent or None
            Grounded ligand agent
        """
        # Get ligand ID and look up full info
        ligand_id = activity.get('ligand_id')
        ligand_info = self.ligand_lookup.get(ligand_id, {})
        
        # Try to get identifiers
        db_refs = {}
        name = None
        
        # Check for ChEMBL ID (preferred for compounds)
        chembl_id = (activity.get('chembl_id') or 
                    ligand_info.get('chembl_id') or
                    ligand_info.get('compound_chembl_id'))
        
        if chembl_id:
            # Clean ChEMBL ID format
            if not chembl_id.startswith('CHEMBL'):
                chembl_id = f'CHEMBL{chembl_id}'
            db_refs['CHEMBL'] = chembl_id
            
            # Try to get CHEBI from ChEMBL
            chebi_id = chebi_client.get_chebi_id_from_chembl(chembl_id)
            if chebi_id:
                db_refs['CHEBI'] = chebi_id
        
        # Check for PubChem
        pubchem_id = ligand_info.get('pubchem_id')
        if pubchem_id:
            db_refs['PUBCHEM'] = str(pubchem_id)
        
        # Add SMILES if available
        smiles = ligand_info.get('smiles')
        if smiles:
            db_refs['SMILES'] = smiles
        
        # InChI key
        inchi_key = ligand_info.get('inchi_key')
        if inchi_key:
            db_refs['INCHIKEY'] = inchi_key
        
        # Get name
        name = (activity.get('ligand_name') or 
                ligand_info.get('ligand_name') or
                ligand_info.get('name') or
                ligand_info.get('compound_name'))
        
        # Check if it's an approved drug
        if name:
            drug_info = self.drug_lookup.get(name.lower())
            if drug_info:
                # Add drug-specific identifiers
                if drug_info.get('drugbank_id'):
                    db_refs['DRUGBANK'] = drug_info['drugbank_id']
        
        # Store KLIFS ID
        if ligand_id:
            db_refs['KLIFS_LIGAND'] = str(ligand_id)
        
        # If still no name, use ChEMBL ID or generic name
        if not name:
            if chembl_id:
                name = chembl_id
            elif ligand_id:
                name = f'KLIFS_ligand_{ligand_id}'
            else:
                logger.warning(f'Could not determine name for ligand in activity: {activity}')
                return None
        
        return Agent(name, db_refs=db_refs)
    
    def _make_kinase_agent(self, activity: Dict) -> Optional[Agent]:
        """Create an Agent for the kinase.
        
        Parameters
        ----------
        activity : dict
            Activity data containing kinase information
            
        Returns
        -------
        Agent or None
            Grounded kinase agent
        """
        # Get kinase name
        kinase_name = activity.get('kinase_name') or activity.get('kinase')
        if not kinase_name:
            logger.warning(f'No kinase name in activity: {activity}')
            return None
        
        # Get full kinase info
        kinase_info = self.kinase_lookup.get(kinase_name, {})
        
        db_refs = {}
        
        # Try HGNC (preferred for human kinases)
        hgnc_symbol = (kinase_info.get('hgnc_symbol') or 
                      kinase_info.get('gene_name') or
                      kinase_name)
        
        if hgnc_symbol:
            hgnc_id = hgnc_client.get_current_hgnc_id(hgnc_symbol)
            if hgnc_id:
                db_refs['HGNC'] = hgnc_id
                
                # Get UniProt from HGNC
                up_id = hgnc_client.get_uniprot_id(hgnc_id)
                if up_id:
                    db_refs['UP'] = up_id
        
        # Try UniProt directly if no HGNC
        if not db_refs.get('HGNC'):
            uniprot_id = (kinase_info.get('uniprot_id') or
                         kinase_info.get('uniprot'))
            if uniprot_id:
                db_refs['UP'] = uniprot_id
                
                # Try to get gene name from UniProt
                gene_name = uniprot_client.get_gene_name(uniprot_id)
                if gene_name:
                    hgnc_id = hgnc_client.get_current_hgnc_id(gene_name)
                    if hgnc_id:
                        db_refs['HGNC'] = hgnc_id
        
        # Store KLIFS kinase ID
        klifs_kinase_id = kinase_info.get('kinase_id')
        if klifs_kinase_id:
            db_refs['KLIFS_KINASE'] = str(klifs_kinase_id)
        
        # Check if it's a family name
        if kinase_name in ['AKT', 'RAF', 'SRC', 'CDK', 'MAPK', 'PKC']:
            db_refs['FPLX'] = kinase_name
        
        return Agent(kinase_name, db_refs=db_refs)
    
    def _make_evidence(self, activity: Dict) -> Evidence:
        """Create Evidence object with activity details.
        
        Parameters
        ----------
        activity : dict
            Activity data from KLIFS
            
        Returns
        -------
        Evidence
            Evidence object with annotations
        """
        # Build annotations with all available data
        annotations = {}
        
        # Activity measurements
        if 'activity_type' in activity:
            annotations['activity_type'] = activity['activity_type']
        if 'activity_value' in activity:
            annotations['activity_value'] = activity['activity_value']
        if 'activity_unit' in activity:
            annotations['activity_unit'] = activity['activity_unit']
            
        # Often KLIFS has pIC50 or pKi
        if 'pic50' in activity:
            annotations['pIC50'] = activity['pic50']
        if 'pki' in activity:
            annotations['pKi'] = activity['pki']
        if 'pkd' in activity:
            annotations['pKd'] = activity['pkd']
            
        # Experimental details
        if 'assay_type' in activity:
            annotations['assay_type'] = activity['assay_type']
        if 'cell_line' in activity:
            annotations['cell_line'] = activity['cell_line']
            
        # Structure info if available
        if 'pdb_id' in activity:
            annotations['pdb_id'] = activity['pdb_id']
        if 'structure_id' in activity:
            annotations['structure_id'] = activity['structure_id']
            
        # Original IDs for back-reference
        if 'ligand_id' in activity:
            annotations['klifs_ligand_id'] = activity['ligand_id']
        if 'bioactivity_id' in activity:
            annotations['klifs_bioactivity_id'] = activity['bioactivity_id']
        
        # Clean up None values
        annotations = {k: v for k, v in annotations.items() if v is not None}
        
        # Create evidence
        evidence = Evidence(
            source_api='klifs',
            pmid=activity.get('pmid'),
            annotations=annotations
        )
        
        return evidence