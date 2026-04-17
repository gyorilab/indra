"""API for processing ExTRI supplementary tables into INDRA Statements.

The API allows processing a local download of the Excel spreadsheets
that contain the ExTRI data. To download this, go to
https://doi.org/10.1016/j.bbagrm.2021.194778 and download
"Supplementary Table 1. ExTRI sentences."
"""

import pandas as pd

from .processor import ExtriProcessor

__all__ = ['process_from_file', 'process_dataframe']


def process_from_file(data_file):
    """Process ExTRI input files into INDRA Statements.

    Parameters
    ----------
    data_file : str or pathlib.Path
        Path to the ExTRI sentence-level table.

    Returns
    -------
    ExtriProcessor
        A processor with extracted statements in ``statements``.
    """
    df = pd.read_excel(data_file, dtype=str)
    return process_dataframe(df)


def process_dataframe(df):
    """Process ExTRI dataframes into INDRA Statements.

    Parameters
    ----------
    df : pandas.DataFrame
        Sentence-level ExTRI dataframe.

    Returns
    -------
    ExtriProcessor
        A processor with extracted statements in ``statements``.
    """
    processor = ExtriProcessor(df=df)
    processor.extract_statements()
    return processor
