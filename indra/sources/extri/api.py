"""API for processing ExTRI supplementary tables into INDRA Statements."""

from pathlib import Path
from typing import Union

import pandas as pd

from .processor import ExtriProcessor, PAIR_COLUMNS, SENTENCE_COLUMNS

__all__ = [
    'process_from_file',
    'process_dataframe',
]


def process_from_file(
    sentence_coverage_file: Union[str, Path],
    pairs_file: Union[str, Path],
) -> ExtriProcessor:
    """Process ExTRI input files into INDRA Statements.

    Parameters
    ----------
    sentence_coverage_file : str or pathlib.Path
        Path to the ExTRI sentence-level table (`mmc6`, XLSX).
    pairs_file : str or pathlib.Path
        Path to the ExTRI pair-level table (`mmc7`, XLSX).

    Returns
    -------
    ExtriProcessor
        A processor with extracted statements in ``statements``.
    """
    sentence_df = pd.read_excel(
        sentence_coverage_file,
        usecols=list(SENTENCE_COLUMNS),
        dtype=str,
    )
    pairs_df = pd.read_excel(
        pairs_file,
        usecols=list(PAIR_COLUMNS),
        dtype=str,
    )
    return process_dataframe(sentence_df, pairs_df)


def process_dataframe(
    sentence_df: pd.DataFrame,
    pairs_df: pd.DataFrame,
) -> ExtriProcessor:
    """Process ExTRI dataframes into INDRA Statements.

    Parameters
    ----------
    sentence_df : pandas.DataFrame
        Sentence-level ExTRI dataframe.
    pairs_df : pandas.DataFrame
        Pair-level ExTRI dataframe.

    Returns
    -------
    ExtriProcessor
        A processor with extracted statements in ``statements``.
    """
    processor = ExtriProcessor(sentence_df=sentence_df, pairs_df=pairs_df)
    processor.extract_statements()
    return processor
