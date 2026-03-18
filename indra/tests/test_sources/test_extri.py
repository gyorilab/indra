# -*- coding: utf-8 -*-

"""Tests for the ExTRI processor."""

import pandas as pd

from indra.sources.extri import process_dataframe
from indra.statements import RegulateAmount


def test_extri_process_dataframe_minimal():
    sentence_df = pd.DataFrame([
        {
            'PMID:Sentence ID:TF:TG': '123456:1:TP53:CDKN1A',
            'Transcription Factor (Associated Gene Name)': 'TP53',
            'Target Gene (Associated Gene Name)': 'CDKN1A',
            'Sentence': 'TP53 increases CDKN1A expression.',
        }
    ])
    pairs_df = pd.DataFrame([
        {
            'TF:TG': 'TP53:CDKN1A',
            '[ExTRI] present': 'ExTRI',
        }
    ])

    processor = process_dataframe(sentence_df, pairs_df)

    assert len(processor.statements) == 1
    stmt = processor.statements[0]
    assert isinstance(stmt, RegulateAmount)
    assert stmt.subj.name == 'TP53'
    assert stmt.obj.name == 'CDKN1A'

    assert len(stmt.evidence) == 1
    ev = stmt.evidence[0]
    assert ev.source_api == 'extri'
    assert ev.source_id == '123456:1:TP53:CDKN1A'
    assert ev.pmid == '123456'
    assert ev.text == 'TP53 increases CDKN1A expression.'
    assert ev.annotations['sentence_id'] == '1'
    assert ev.annotations['pair_key'] == 'TP53:CDKN1A'


def test_extri_process_dataframe_requires_explicit_gene_names():
    sentence_df = pd.DataFrame([
        {
            'PMID:Sentence ID:TF:TG': '123456:1:TP53:CDKN1A',
            'Transcription Factor (Associated Gene Name)': None,
            'Target Gene (Associated Gene Name)': 'CDKN1A',
            'Sentence': 'TP53 increases CDKN1A expression.',
        }
    ])
    pairs_df = pd.DataFrame([
        {
            'TF:TG': 'TP53:CDKN1A',
            '[ExTRI] present': 'ExTRI',
        }
    ])

    processor = process_dataframe(sentence_df, pairs_df)

    assert len(processor.statements) == 0
    assert processor.skipped == 1


def test_extri_process_dataframe_filters_to_extri_pairs():
    sentence_df = pd.DataFrame([
        {
            'PMID:Sentence ID:TF:TG': '123456:1:TP53:CDKN1A',
            'Transcription Factor (Associated Gene Name)': 'TP53',
            'Target Gene (Associated Gene Name)': 'CDKN1A',
            'Sentence': 'TP53 increases CDKN1A expression.',
        }
    ])
    pairs_df = pd.DataFrame([
        {
            'TF:TG': 'TP53:CDKN1A',
            '[ExTRI] present': 'no',
        }
    ])

    processor = process_dataframe(sentence_df, pairs_df)

    assert len(processor.statements) == 0
    assert processor.skipped == 1
