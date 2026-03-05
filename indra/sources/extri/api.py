# -*- coding: utf-8 -*-

"""API for processing ExTRI supplementary tables into INDRA Statements."""

from pathlib import Path
from typing import Optional, Union

import pandas as pd

from .processor import ExtriProcessor

__all__ = [
    'process_from_file',
    'process_dataframe',
]

SENTENCE_SHEET = 'sentence_coverage'
PAIR_SHEET = 'pairs'

SENTENCE_ID_COL = 'PMID:Sentence ID:TF:TG'
TF_COL = 'Transcription Factor (Associated Gene Name)'
TG_COL = 'Target Gene (Associated Gene Name)'
SENTENCE_COL = 'Sentence'

PAIR_KEY_COL = 'TF:TG'
PAIR_PRESENT_COL = '[ExTRI] present'

SENTENCE_USECOLS = [
    SENTENCE_ID_COL,
    TF_COL,
    TG_COL,
    SENTENCE_COL,
]

PAIR_USECOLS = [
    PAIR_KEY_COL,
    PAIR_PRESENT_COL,
]


def process_from_file(
    sentence_coverage_file: Union[str, Path],
    pairs_file: Union[str, Path],
    sentence_sheet: str = SENTENCE_SHEET,
    pairs_sheet: str = PAIR_SHEET,
    require_text: bool = True,
    require_extri_present: bool = True,
) -> ExtriProcessor:
    """Process ExTRI XLSX files into INDRA Statements."""
    sentence_df = pd.read_excel(
        sentence_coverage_file,
        sheet_name=sentence_sheet,
        usecols=SENTENCE_USECOLS,
        dtype=str,
    )
    pairs_df = pd.read_excel(
        pairs_file,
        sheet_name=pairs_sheet,
        usecols=PAIR_USECOLS,
        dtype=str,
    )

    return process_dataframe(
        sentence_df,
        pairs_df=pairs_df,
        require_text=require_text,
        require_extri_present=require_extri_present,
    )


def process_dataframe(
    sentence_df: pd.DataFrame,
    pairs_df: Optional[pd.DataFrame],
    require_text: bool = True,
    require_extri_present: bool = True,
) -> ExtriProcessor:
    """Process ExTRI data frames into INDRA Statements."""
    processor = ExtriProcessor(
        sentence_df=sentence_df,
        pairs_df=pairs_df,
        require_text=require_text,
        require_extri_present=require_extri_present,
    )
    processor.extract_statements()
    return processor
