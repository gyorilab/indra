from indra.statements import *
from indra.statements.io import stmt_from_json
from indra.ontology.standardize import standardize_agent_name

import re
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

class IndraBertProcessor:
    def __init__(self, data, grounder=None):
        self.data = data
        self.statements = []
        self.source_api = 'indra_bert'
        self.grounder = grounder if grounder else default_grounder_wrapper
        self.extract_statements()


    def extract_statement(self, entry):
        """Extract a statement from JSON using INDRA's built-in functionality."""
        try:
            # Use INDRA's built-in statement_from_json functionality
            stmt = stmt_from_json(entry)
            
            # Apply grounding to agents if grounder is available
            if self.grounder:
                text = entry['evidence'][0]['text'] if entry.get('evidence') else ""
                self._apply_grounding(stmt, text)
            
            return stmt
            
        except Exception as e:
            logger.warning(f"Error creating statement from JSON: {e}")
            raise
    
    def _apply_grounding(self, stmt, context_text):
        """Apply grounding to all agents in a statement."""
        # Get all agents from the statement
        agents = stmt.agent_list()
        
        for agent in agents:
            if agent and agent.name:
                # Apply grounding
                grounding_result = self.grounder(agent.name, context_text)
                if grounding_result:
                    # Update db_refs with grounding results
                    agent.db_refs.update(grounding_result)
                
                # Standardize the agent name
                standardize_agent_name(agent, standardize_refs=True)

    def extract_statements(self):
        self.statements = []
        for entry in self.data:
            try: 
                stmt = self.extract_statement(entry)
            except Exception as e:
                logger.warning(f"Error processing entry: {e}")
                logger.debug(f"Entry data: {entry}")
                continue
            self.statements.append(stmt)


def default_grounder_wrapper(text, context=None):
    # Import here to avoid this when working in INDRA World context
    from indra.preassembler.grounding_mapper.gilda import get_grounding
    grounding, _ = get_grounding(text, context=context, mode='local')
    return grounding
