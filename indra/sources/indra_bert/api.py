__all__ = ['process_text']

import os
from tqdm import tqdm
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

def create_extractor(
    ner_model_path="thomaslim6793/indra_bert_ner_agent_detection", 
    stmt_model_path="thomaslim6793/indra_bert_indra_stmt_classifier",
    role_model_path="thomaslim6793/indra_bert_indra_stmt_agents_role_assigner",
    stmt_conf_threshold=0.95
):
    try: 
        ise = IndraStructuredExtractor(
            ner_model_path=ner_model_path, 
            stmt_model_path=stmt_model_path,
            role_model_path=role_model_path, 
            stmt_conf_threshold=stmt_conf_threshold
        )
    except Exception as e:
        logger.info(f"Error - {e}")
        logger.info("Downloading models from Hugging Face")
        ise = IndraStructuredExtractor(
            ner_model_path="thomaslim6793/indra_bert_ner_agent_detection",
            stmt_model_path="thomaslim6793/indra_bert_indra_stmt_classifier",
            role_model_path="thomaslim6793/indra_bert_indra_stmt_agents_role_assigner",
            stmt_conf_threshold=stmt_conf_threshold
        )
    logger.info(f"Loaded ner_model from: {ise.ner_model_local_path}")
    logger.info(f"Loaded stmt_model from: {ise.stmt_model_local_path}")
    logger.info(f"Loaded role_model from: {ise.role_model_local_path}")
    return ise

def process_text(text, 
                 ner_model_path="thomaslim6793/indra_bert_ner_agent_detection",
                 stmt_model_path="thomaslim6793/indra_bert_indra_stmt_classifier",
                 role_model_path="thomaslim6793/indra_bert_indra_stmt_agents_role_assigner",
                 stmt_conf_threshold=0.95,
                 grounder=None):
    ise = create_extractor(
        ner_model_path=ner_model_path, 
        stmt_model_path=stmt_model_path,
        role_model_path=role_model_path, 
        stmt_conf_threshold=stmt_conf_threshold
    )
    res = ise.extract_structured_statements_batch(text)
    ip = IndraBertProcessor(res, grounder=grounder)
    return ip, ise

def process_texts(texts, 
                  ner_model_path="thomaslim6793/indra_bert_ner_agent_detection",
                  stmt_model_path="thomaslim6793/indra_bert_indra_stmt_classifier",
                  role_model_path="thomaslim6793/indra_bert_indra_stmt_agents_role_assigner",
                  stmt_conf_threshold=0.95,
                  grounder=None):
    
    if not isinstance(texts, list):
        raise ValueError("Input must be a list of texts.")
    
    ise = create_extractor(
        ner_model_path=ner_model_path, 
        stmt_model_path=stmt_model_path,
        role_model_path=role_model_path, 
        stmt_conf_threshold=stmt_conf_threshold
    )

    ips = []
    for text in tqdm(texts, desc="Processing texts"):
        res = ise.extract_structured_statements_batch(text)
        ip = IndraBertProcessor(res, grounder=grounder)
        ips.append(ip)
    return ips, ise
