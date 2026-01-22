# indra/sources/klifs/api.py

import requests
from typing import List, Dict, Optional, Union
import logging

logger = logging.getLogger(__name__)

class KlifsClient:
    """Client for KLIFS API based on official Swagger documentation."""
    
    # The documented base URL from Swagger
    BASE_URL = 'https://klifs.net/api'
    
    def __init__(self):
        self.session = requests.Session()
        self._kinase_cache = {}
        
    # ========== Information Endpoints ==========
    
    def get_kinase_groups(self) -> List[str]:
        """Get list of kinase groups."""
        res = self.session.get(f'{self.BASE_URL}/kinase_groups')
        res.raise_for_status()
        return res.json()
    
    def get_kinase_families(self, kinase_group: Optional[str] = None) -> List[str]:
        """Get list of kinase families, optionally filtered by group."""
        params = {}
        if kinase_group:
            params['kinase_group'] = kinase_group
        res = self.session.get(f'{self.BASE_URL}/kinase_families', params=params)
        res.raise_for_status()
        return res.json()
    
    def get_kinase_names(self, 
                        kinase_group: Optional[str] = None,
                        kinase_family: Optional[str] = None,
                        species: Optional[str] = None) -> List[Dict]:
        """Get list of kinases with IDs and names.
        
        Returns list of dicts with: kinase_ID, name, full_name, species
        """
        params = {}
        if kinase_group:
            params['kinase_group'] = kinase_group
        if kinase_family:
            params['kinase_family'] = kinase_family
        if species:
            params['species'] = species.upper()  # HUMAN, MOUSE
            
        res = self.session.get(f'{self.BASE_URL}/kinase_names', params=params)
        res.raise_for_status()
        return res.json()
    
    def get_kinase_information(self, 
                              kinase_ids: Optional[List[int]] = None,
                              species: Optional[str] = None) -> List[Dict]:
        """Get detailed kinase information.
        
        Returns KinaseInformation objects with HGNC, UniProt, pocket sequence, etc.
        """
        params = {}
        if kinase_ids:
            # API expects comma-separated IDs
            params['kinase_ID'] = ','.join(map(str, kinase_ids))
        if species:
            params['species'] = species.upper()
            
        res = self.session.get(f'{self.BASE_URL}/kinase_information', params=params)
        res.raise_for_status()
        return res.json()
    
    def get_kinase_id(self, kinase_name: str, species: Optional[str] = None) -> List[Dict]:
        """Get kinase ID(s) for a given kinase name.
        
        Parameters
        ----------
        kinase_name : str
            Kinase name (e.g., 'EGFR', 'ABL1') or UniProt ID
        species : str, optional
            Species filter (HUMAN, MOUSE)
            
        Returns
        -------
        list
            List of matching kinases with their IDs
        """
        params = {'kinase_name': kinase_name}
        if species:
            params['species'] = species.upper()
            
        res = self.session.get(f'{self.BASE_URL}/kinase_ID', params=params)
        res.raise_for_status()
        return res.json()
    
    # ========== Ligands Endpoints ==========
    
    def get_ligands_list(self, kinase_ids: Optional[List[int]] = None) -> List[Dict]:
        """Get all co-crystallized ligands, optionally filtered by kinase IDs.
        
        Returns ligandDetails objects with: ligand_ID, PDB-code, Name, SMILES, InChIKey
        """
        params = {}
        if kinase_ids:
            params['kinase_ID'] = ','.join(map(str, kinase_ids))
            
        res = self.session.get(f'{self.BASE_URL}/ligands_list', params=params)
        res.raise_for_status()
        return res.json()
    
    def get_bioactivity_by_ligand_id(self, ligand_id: int) -> List[Dict]:
        """Get all ChEMBL bioactivities for a specific ligand.
        
        Returns BioactivityDetails with: pref_name, accession, standard_type,
        standard_value, standard_units, pchembl_value, etc.
        """
        params = {'ligand_ID': ligand_id}
        res = self.session.get(f'{self.BASE_URL}/bioactivity_list_id', params=params)
        res.raise_for_status()
        return res.json()
    
    def get_bioactivity_by_pdb(self, ligand_pdb: str) -> List[Dict]:
        """Get all ChEMBL bioactivities for a ligand by PDB code."""
        params = {'ligand_PDB': ligand_pdb}
        res = self.session.get(f'{self.BASE_URL}/bioactivity_list_pdb', params=params)
        res.raise_for_status()
        return res.json()
    
    # ========== Structures Endpoints ==========
    
    def get_structures_by_kinase(self, kinase_ids: List[int]) -> List[Dict]:
        """Get all structures for given kinase ID(s).
        
        Returns structureDetails objects.
        """
        params = {'kinase_ID': ','.join(map(str, kinase_ids))}
        res = self.session.get(f'{self.BASE_URL}/structures_list', params=params)
        res.raise_for_status()
        return res.json()
    
    # ========== Helper Methods ==========
    
    def get_kinase_bioactivities(self, kinase_name: str, species: str = 'HUMAN') -> List[Dict]:
        """Helper to get all bioactivities for a specific kinase.
        
        This combines multiple API calls:
        1. Get kinase ID from name
        2. Get ligands for that kinase
        3. Get bioactivities for each ligand
        
        Parameters
        ----------
        kinase_name : str
            Kinase name (e.g., 'EGFR')
        species : str
            Species (default: 'HUMAN')
            
        Returns
        -------
        list
            All bioactivity data for the kinase with ligand info included
        """
        # Step 1: Get kinase ID
        kinase_info = self.get_kinase_id(kinase_name, species=species)
        if not kinase_info:
            logger.warning(f"Kinase '{kinase_name}' not found")
            return []
        
        kinase_id = kinase_info[0]['kinase_ID']
        logger.info(f"Found {kinase_name}: ID {kinase_id}")
        
        # Step 2: Get ligands for this kinase
        ligands = self.get_ligands_list(kinase_ids=[kinase_id])
        logger.info(f"Found {len(ligands)} ligands for {kinase_name}")
        
        # Step 3: Get bioactivities for each ligand
        all_bioactivities = []
        for ligand in ligands:
            ligand_id = ligand.get('ligand_ID')
            if not ligand_id:
                continue
                
            try:
                bioactivities = self.get_bioactivity_by_ligand_id(ligand_id)
                
                # Add ligand and kinase info to each bioactivity
                for bio in bioactivities:
                    # Add ligand info
                    bio['ligand_ID'] = ligand_id
                    bio['ligand_name'] = ligand.get('Name')
                    bio['ligand_SMILES'] = ligand.get('SMILES')
                    bio['ligand_InChIKey'] = ligand.get('InChIKey')
                    bio['ligand_PDB'] = ligand.get('PDB-code')
                    
                    # Add kinase info
                    bio['kinase_ID'] = kinase_id
                    bio['kinase_name'] = kinase_name
                    
                all_bioactivities.extend(bioactivities)
                
            except Exception as e:
                logger.debug(f"No bioactivity for ligand {ligand_id}: {e}")
                continue
        
        logger.info(f"Found {len(all_bioactivities)} total bioactivities for {kinase_name}")
        return all_bioactivities