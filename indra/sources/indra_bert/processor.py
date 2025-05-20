from indra.statements import *


class IndraBertProcessor:
    def __init__(self, data):
        self.data = data
        self.statements = []
        self.source_api = 'indra_bert'
        self.extract_statements()

    def get_agent(self, agent_info):
        name = agent_info['text']
        agent = Agent(name, db_refs={'TEXT': name})
        # TODO: grounding
        return agent

    def extract_statement(self, entry):
        stmt_type = entry['stmt_pred']['label']
        roles = entry['role_pred']['roles']

        raw_texts = []
        coords = []

        agents_by_role = {}
        for agent_info in roles:
            agents_by_role[agent_info['role']] = self.get_agent(agent_info)
            raw_texts.append(agent_info['text'])
            coords.append([agent_info['start'], agent_info['end']])

        evidence = Evidence(
            source_api=self.source_api,
            text=entry['original_text'],
            annotations={
                'agents': {
                    'raw_text': raw_texts,
                    'coords': coords
                }
            }
        )

        stmt_class = get_statement_by_name(stmt_type)
        if issubclass(stmt_class, Complex):
            members = [agent for role, agent in agents_by_role.items()
                       if role.startswith('member')]
            stmt = Complex(members, evidence=[evidence])
            return stmt
        elif issubclass(stmt_class, (RegulateAmount, RegulateActivity)):
            subj = agents_by_role.get('subject')
            obj = agents_by_role.get('object')
            stmt = stmt_class(subj, obj, evidence=[evidence])
            return stmt
        elif issubclass(stmt_class, Modification):
            enz = agents_by_role.get('enz')
            sub = agents_by_role.get('sub')
            stmt = stmt_class(enz, sub, evidence=[evidence])
            return stmt
        else:
            assert False, "Unsupported statement type: %s" % stmt_class

    def extract_statements(self):
        self.statements = []
        for entry in self.data:
            stmt = self.extract_statement(entry)
            self.statements.append(stmt)
