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


class ExtriProcessor:
    """Extract INDRA Statements from ExTRI tables."""

    def __init__(self, sentence_df: pd.DataFrame, pairs_df: pd.DataFrame):
        self.sentence_df = sentence_df
        self.pairs_df = pairs_df
        self.statements: List[RegulateAmount] = []
        self.skipped: int = 0

    def extract_statements(self) -> List[RegulateAmount]:
        """Extract statements from the loaded dataframe."""
        valid_pairs = self._get_valid_pairs()
        for _, row in self.sentence_df.iterrows():
            stmt = self._process_row(row, valid_pairs)
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

    def _process_row(
        self,
        row: pd.Series,
        valid_pairs: Set[str],
    ) -> Optional[RegulateAmount]:
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
        if pair_key not in valid_pairs:
            return None
        subj = self._make_gene_agent(tf_name)
        obj = self._make_gene_agent(tg_name)
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

    def _get_valid_pairs(self) -> Set[str]:
        valid_pairs: Set[str] = set()
        for _, row in self.pairs_df.iterrows():
            pair_key = get_str(row, PAIR_KEY_COL)
            present = get_str(row, PAIR_PRESENT_COL)
            if present == 'ExTRI':
                valid_pairs.add(pair_key)
        return valid_pairs

    @staticmethod
    def _make_gene_agent(name: str) -> Agent:
        hgnc_id = hgnc_client.get_current_hgnc_id(name)
        if isinstance(hgnc_id, str):
            return get_standard_agent(name, {'HGNC': hgnc_id})
        return Agent(name)


def get_str(row: pd.Series, key: str) -> Optional[str]:
    val = row.get(key)
    if pd.isna(val):
        return None
    val = str(val).strip()
    return val or None


def parse_extri_entry(extri_entry: str) -> Tuple[str, str, str, str]:
    return tuple(extri_entry.split(':', 3))
