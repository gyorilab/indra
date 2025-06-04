from indra.statements import *
from indra.ontology.standardize import standardize_agent_name

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

    def get_agent(self, agent_info, context=None):
        name = agent_info['text']
        db_refs = self.grounder(name, context)
        db_refs['TEXT'] = name
        agent = Agent(name, db_refs=db_refs)
        standardize_agent_name(agent, standardize_refs=True)
        return agent

    def extract_statement(self, entry):
        stmt_type = entry['stmt_pred']['label']
        roles = entry['role_pred']['roles']
        text = entry['original_text']

        agents_by_role = {}
        raw_texts = {}
        coords = {}
        for agent_info in roles:
            role = agent_info['role']
            agents_by_role[role] = self.get_agent(agent_info, text)
            raw_texts[role] = agent_info['text']
            coords[role] = ([agent_info['start'], agent_info['end']])

        evidence = Evidence(
            source_api=self.source_api,
            text=text,
        )

        stmt_class = get_statement_by_name(stmt_type)
        if issubclass(stmt_class, Complex):
            members = [agent for role, agent in agents_by_role.items()]
            raw_texts = [raw_text for role, raw_text in raw_texts.items()]
            coords = [coord for role, coord in coords.items()]
            annotations = {
                'agents': {
                    'raw_text': raw_texts,
                    'coords': coords
                }
            }
            evidence.annotations = annotations
            stmt = Complex(members, evidence=[evidence])
            return stmt
        elif issubclass(stmt_class, (RegulateAmount, RegulateActivity)):
            subj = agents_by_role.get('subj')
            obj = agents_by_role.get('obj')
            raw_texts = [raw_texts.get('subj'), raw_texts.get('obj')]
            coords = [coords.get('subj'), coords.get('obj')]
            annotations = {
                'agents': {
                    'raw_text': raw_texts,
                    'coords': coords
                }
            }
            evidence.annotations = annotations
            stmt = stmt_class(subj, obj, evidence=[evidence])
            return stmt
        elif issubclass(stmt_class, Modification):
            enz = agents_by_role.get('enz')
            sub = agents_by_role.get('sub')
            raw_texts = [raw_texts.get('enz'), raw_texts.get('sub')]
            coords = [coords.get('enz'), coords.get('sub')]
            annotations = {
                'agents': {
                    'raw_text': raw_texts,
                    'coords': coords
                }
            }
            evidence.annotations = annotations
            stmt = stmt_class(enz, sub, evidence=[evidence])
            return stmt
        else:
            assert False, "Unsupported statement type: %s" % stmt_class

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
