"""Processor for ExTRI transcription-factor target-gene interactions."""

import logging
from typing import List, Optional, Set, Tuple

import pandas as pd

from indra.databases import hgnc_client
from indra.ontology.standardize import get_standard_agent
from indra.statements import Agent, Evidence, RegulateAmount

__all__ = ['ExtriProcessor']

logger = logging.getLogger(__name__)


class ExtriProcessor:
    """Extract INDRA Statements from ExTRI tables.

    Parameters
    ----------
    sentence_df : pandas.DataFrame
        Sentence-level ExTRI table (`mmc6`).
    pairs_df : Optional[pandas.DataFrame]
        Pair-level ExTRI table (`mmc7`).
    require_text : bool
        If True, rows with missing sentence text are skipped.
    require_extri_present : bool
        If True, only TF:TG pairs marked as ExTRI in `mmc7` are processed.

    Attributes
    ----------
    statements : list[indra.statements.RegulateAmount]
        Extracted INDRA statements.
    skipped : int
        Number of rows skipped during processing.
    """

    def __init__(
        self,
        sentence_df: pd.DataFrame,
        pairs_df: Optional[pd.DataFrame],
        require_text: bool = True,
        require_extri_present: bool = True,
    ):
        self.sentence_df = sentence_df
        self.pairs_df = pairs_df
        self.require_text = require_text
        self.require_extri_present = require_extri_present
        self.statements: List[RegulateAmount] = []
        self.skipped: int = 0

    def extract_statements(self) -> List[RegulateAmount]:
        """Extract statements from loaded dataframes.

        Returns
        -------
        list[indra.statements.RegulateAmount]
            Extracted statements.
        """
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
        valid_pairs: Optional[Set[str]],
    ) -> Optional[RegulateAmount]:
        extri_entry = _get_str(row, 'PMID:Sentence ID:TF:TG')
        if not extri_entry:
            return None

        parsed = _parse_extri_entry(extri_entry)
        if parsed is None:
            logger.debug(
                'Could not parse ExTRI entry identifier: %s',
                extri_entry,
            )
            return None

        pmid, sentence_id, tf_from_key, tg_from_key = parsed

        tf_name = (
            _get_str(row, 'Transcription Factor (Associated Gene Name)')
            or tf_from_key
        )
        tg_name = (
            _get_str(row, 'Target Gene (Associated Gene Name)')
            or tg_from_key
        )
        sentence_text = _get_str(row, 'Sentence')
        if self.require_text and not sentence_text:
            return None

        pair_key = '%s:%s' % (tf_from_key, tg_from_key)
        if valid_pairs is not None and pair_key not in valid_pairs:
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
                # Raw sentence-level entry key from the mmc6 table.
                'extri_entry': extri_entry,
                'sentence_id': sentence_id,
                'pair_key': pair_key,
            },
        )
        return RegulateAmount(subj, obj, evidence=[evidence])

    def _get_valid_pairs(self) -> Optional[Set[str]]:
        if not self.require_extri_present:
            return None
        if self.pairs_df is None:
            raise ValueError(
                'pairs_df is required when require_extri_present=True.'
            )

        valid_pairs: Set[str] = set()
        for _, row in self.pairs_df.iterrows():
            pair_key = _get_str(row, 'TF:TG')
            present = _get_str(row, '[ExTRI] present')
            if pair_key and present == 'ExTRI':
                valid_pairs.add(pair_key)
        return valid_pairs

    @staticmethod
    def _make_gene_agent(name: str) -> Agent:
        db_refs = {'TEXT': name}

        hgnc_id = hgnc_client.get_current_hgnc_id(name)
        if isinstance(hgnc_id, list):
            hgnc_id = hgnc_id[0] if len(hgnc_id) == 1 else None
        if not hgnc_id:
            hgnc_id = hgnc_client.get_hgnc_id(name)

        if hgnc_id:
            db_refs['HGNC'] = hgnc_id
            up_id = hgnc_client.get_uniprot_id(hgnc_id)
            if up_id and ',' not in up_id:
                db_refs['UP'] = up_id

        return get_standard_agent(name, db_refs)


def _get_str(row: pd.Series, key: str) -> Optional[str]:
    val = row.get(key)
    if val is None or pd.isna(val):
        return None
    val = str(val).strip()
    if not val or val.lower() == 'nan':
        return None
    return val


def _parse_extri_entry(extri_entry: str) -> Optional[Tuple[str, str, str, str]]:
    parts = extri_entry.split(':', 3)
    if len(parts) != 4:
        return None
    pmid, sentence_id, tf, tg = parts
    if not pmid.isdigit() or not sentence_id.isdigit():
        return None
    return pmid, sentence_id, tf, tg
