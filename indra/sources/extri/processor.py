"""Processor for ExTRI transcription-factor target-gene interactions."""

import logging
from typing import List, Optional, Set, Tuple

import pandas as pd

from indra.databases import hgnc_client
from indra.ontology.standardize import get_standard_agent
from indra.statements import Agent, Evidence, RegulateAmount

__all__ = ['ExtriProcessor']

logger = logging.getLogger(__name__)

SENTENCE_COLUMNS = (
    'PMID:Sentence ID:TF:TG',
    'Transcription Factor (Associated Gene Name)',
    'Target Gene (Associated Gene Name)',
    'Sentence',
)
PAIR_COLUMNS = (
    'TF:TG',
    '[ExTRI] present',
)

SENTENCE_ID_COL, TF_COL, TG_COL, SENTENCE_COL = SENTENCE_COLUMNS
PAIR_KEY_COL, PAIR_PRESENT_COL = PAIR_COLUMNS


famplex_mappings = {
    'NFY': 'NFY',
    'NFKB': 'NFkappaB',
    'AP1': 'AP1',
}

gene_name_mappings = {
    '2020-12-01 00:00:00': 'DEC1',
    '2020-03-07 00:00:00': 'MARCH7',
    '2020-09-09 00:00:00': 'SEPT9',
}


class ExtriProcessor:
    """Extract INDRA Statements from ExTRI tables."""

    def __init__(self, df):
        self.df = df
        self.statements = []
        self.skipped: int = 0
        self.non_gene_agents = set()

    def extract_statements(self):
        """Extract statements from the loaded dataframe."""
        for _, row in self.df.iterrows():
            stmt = self._process_row(row)
            if stmt is None:
                self.skipped += 1
                continue
            self.statements.append(stmt)

        logger.info(
            'ExTRI processing complete: extracted=%d skipped=%d',
            len(self.statements),
            self.skipped,
        )
        return self.statements

    def _process_row(self, row):
        extri_entry = get_str(row, SENTENCE_ID_COL)
        tf_name = get_str(row, TF_COL)
        tg_name = get_str(row, TG_COL)
        sentence_text = get_str(row, SENTENCE_COL)
        if not extri_entry or not tf_name or not tg_name or not sentence_text:
            return None

        pmid, sentence_id, tf_from_key, tg_from_key = parse_extri_entry(
            extri_entry
        )
        pair_key = '%s:%s' % (tf_from_key, tg_from_key)
        subj = self._make_gene_agent(tf_name)
        obj = self._make_gene_agent(tg_name)
        if subj is None or obj is None:
            return None

        evidence = Evidence(
            source_api='extri',
            source_id=extri_entry,
            pmid=pmid,
            text=sentence_text,
            text_refs={'PMID': pmid},
            annotations={
                'sentence_id': sentence_id,
                'pair_key': pair_key,
            },
        )
        return RegulateAmount(subj, obj, evidence=[evidence])

    def _make_gene_agent(self, name: str):
        db_refs = {}
        if name in famplex_mappings:
            db_refs['FPLX'] = famplex_mappings[name]
        else:
            if name in gene_name_mappings:
                name = gene_name_mappings[name]
            hgnc_id = hgnc_client.get_current_hgnc_id(name)
            # There is a rare corner case where the original gene is not valid
            # anymore and was split into multiple genes. We skip these cases.
            if isinstance(hgnc_id, str):
                db_refs['HGNC'] = hgnc_id
            else:
                return None
        return get_standard_agent(name, db_refs)


def get_str(row: pd.Series, key: str) -> Optional[str]:
    val = row.get(key)
    if pd.isna(val):
        return None
    val = str(val).strip()
    return val or None


def parse_extri_entry(extri_entry: str):
    return tuple(extri_entry.split(':', 3))
