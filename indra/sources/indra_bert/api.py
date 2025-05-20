__all__ = ['process_text']

import os
import logging

logger = logging.getLogger(__name__)

try:
    from indra_bert import IndraStructuredExtractor
except ImportError as e:
    logger.error("""Could not import indra_bert for reading with INDRA BERT.
                 Please make sure the indra_bert extra dependencies of 
                 INDRA are installed.""")
    raise ImportError(e)

from .processor import IndraBertProcessor

MODELS_BASE = os.path.join(os.path.expanduser('~'), '.data', 'indra_bert')

MODEL_PATHS = {
    'ner': os.path.join(MODELS_BASE, 'ner_agent_detection',
                        'checkpoint-2450'),
    'stmt': os.path.join(MODELS_BASE, 'indra_stmt_classifier',
                         'checkpoint-790'),
    'role': os.path.join(MODELS_BASE, 'indra_stmt_agents_role_assigner',
                         'checkpoint-790')
}


def process_text(text, ner_model_path=MODEL_PATHS['ner'],
                 stmt_model_path=MODEL_PATHS['stmt'],
                 role_model_path=MODEL_PATHS['role'],
                 stmt_conf_threshold=0.95,
                 grounder=None):
    ise = IndraStructuredExtractor(ner_model_path, stmt_model_path,
                                   role_model_path, stmt_conf_threshold)
    res = ise.extract_structured_statements(text)
    ip = IndraBertProcessor(res, grounder=grounder)
    return ip
