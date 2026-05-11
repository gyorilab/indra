from collections import Counter
from functools import lru_cache
from io import BytesIO
from urllib.request import urlopen

import joblib
import gilda
import numpy as np
import pandas as pd

from indra.ontology.bio import bio_ontology
from indra.sources import indra_db_rest
from indra.statements import modclass_to_inverse



class StatementTypeClassification:
    """Predict whether a statement type is correct based on polarity and evidence patterns within an agent-agent group."""

    MODEL_URL = (
        "https://bigmech.s3.us-east-1.amazonaws.com/classification_model.joblib"
    )

    def __init__(
            self,
            model_path=None,
            model=None,
            feature_cols=None,
            opposite_map=None,
            db_client=indra_db_rest,
    ):
        if model is not None:
            self.model = model
        else:
            self.model = self._load_model(model_path)

        self.db_client = db_client

        self.feature_cols = feature_cols or [
            "rel_evidence_log",
            "has_family_complex",
            "evidence_proportion_in_group",
            "supported_sources",
            "has_oppo_type_in_group",
            "oppo_type_count_ratio_in_pair",
            "pair_total_evidence_log",
        ]

        self.opposite_map = opposite_map or self._make_opposite_map()


    def _load_model(self, model_path):
        if model_path:
            return joblib.load(model_path)

        with urlopen(self.MODEL_URL) as response:
            return joblib.load(BytesIO(response.read()))

    @staticmethod
    def _make_opposite_map():
        return {
            **{k.__name__: v.__name__ for k, v in modclass_to_inverse.items()},

            "Gef": "Gap",
            "Gap": "Gef",

            "AddModification": "RemoveModification",
            "RemoveModification": "AddModification",

            "Activation": "Inhibition",
            "Inhibition": "Activation",

            "IncreaseAmount": "DecreaseAmount",
            "DecreaseAmount": "IncreaseAmount",
        }

    @staticmethod
    def merge_source_count_dicts(dicts):
        total = Counter()
        for d in dicts:
            total.update(d)
        return dict(total)

    @staticmethod
    @lru_cache(maxsize=500000)
    def is_family_complex(name):
        scored_matches = gilda.ground(name)
        if not scored_matches:
            return False

        ns, entity_id = scored_matches[0].term.get_curie().split(":")
        ent_type = bio_ontology.get_type(ns.upper(), entity_id)
        return ent_type == "protein_family_complex"

    @staticmethod
    def stmt_to_row(stmt, source_counts):
        agents = stmt.agent_list()

        if len(agents) != 2:
            return None

        if agents[0] is None or agents[1] is None:
            return None

        stmt_hash = stmt.get_hash()
        source_count = source_counts.get(stmt_hash, {})

        return {
            "subject": agents[0].name,
            "object": agents[1].name,
            "type": stmt.__class__.__name__,
            "hash": stmt_hash,
            "statement": str(stmt),
            "source_count": source_count,
            "rel_evidence": sum(source_count.values()),
            "in_signor": int("signor" in source_count),
        }

    def get_pair_df(self, subject, object):
        res = self.db_client.get_statements(subject=subject, object=object, ev_limit=1)

        source_counts = res.get_source_counts()
        source_counts = {
            stmt_hash: {
                source: count
                for source, count in source_dict.items()
                if count != 0
            }
            for stmt_hash, source_dict in source_counts.items()
        }
        rows = []
        for stmt in res.statements:
            row = self.stmt_to_row(stmt, source_counts)
            if row is not None:
                rows.append(row)

        return pd.DataFrame(rows)

    def build_pair_input(self, subject, object):
        df = self.get_pair_df(subject, object)

        if df.empty:
            return df

        df = df.groupby(["subject", "object", "type"], as_index=False).agg({
            "hash": list,
            "statement": list,
            "source_count": self.merge_source_count_dicts,
            "rel_evidence": "sum",
            "in_signor": "max",
        })

        df["has_family_complex"] = df.apply(
            lambda row: int(
                self.is_family_complex(row["subject"])
                or self.is_family_complex(row["object"])
            ),
            axis=1,
        )

        df["supported_sources"] = df["source_count"].apply(lambda x: len(x))

        df["pair_total_evidence"] = (
            df.groupby(["subject", "object"])["rel_evidence"].transform("sum")
        )

        df["evidence_proportion_in_group"] = (
                df["rel_evidence"] / df["pair_total_evidence"]
        )

        type_to_evidence = df.groupby("type")["rel_evidence"].sum().to_dict()

        df["has_oppo_type_in_group"] = df["type"].apply(
            lambda x: int(self.opposite_map.get(x) in type_to_evidence)
        )

        df["oppo_type_count_ratio_in_pair"] = df["type"].apply(
            lambda x: (
                df.loc[df["type"] == x, "rel_evidence"].iloc[0]
                / type_to_evidence[self.opposite_map[x]]
                if self.opposite_map.get(x) in type_to_evidence
                else 0
            )
        )

        df["rel_evidence_log"] = np.log1p(df["rel_evidence"])

        # Doing this twice for feature engineering
        df["pair_total_evidence_log"] = np.log1p(df["pair_total_evidence"])
        df["pair_total_evidence_log"] = np.log1p(df["pair_total_evidence_log"])

        df["supported_sources"] = np.log1p(df["supported_sources"])
        df["oppo_type_count_ratio_in_pair"] = np.log1p(
            df["oppo_type_count_ratio_in_pair"]
        )

        return df

    def predict_pair(self, subject, object):
        df_input = self.build_pair_input(subject, object)

        if df_input.empty:
            return df_input

        X = df_input[self.feature_cols].copy()

        df_input["pred_prob"] = self.model.predict_proba(X)[:, 1]
        df_input["pred_label"] = self.model.predict(X)

        first_cols = ["subject", "object", "type", "pred_prob", "pred_label"]
        other_cols = [col for col in df_input.columns if col not in first_cols]
        df_input = df_input[first_cols + other_cols]

        return df_input.sort_values("pred_prob", ascending=False)

    def build_input_from_rows(self, rows):
        df = pd.DataFrame(rows)

        if df.empty:
            return df

        df["rel_evidence"] = df["source_count"].apply(lambda x: sum(x.values()))
        df["in_signor"] = df["source_count"].apply(lambda x: int("signor" in x))

        df = df.groupby(["subject", "object", "type"], as_index=False).agg({
            "hash": list,
            "statement": list,
            "source_count": self.merge_source_count_dicts,
            "rel_evidence": "sum",
            "in_signor": "max",
        })

        df["has_family_complex"] = df.apply(
            lambda row: int(
                self.is_family_complex(row["subject"])
                or self.is_family_complex(row["object"])
            ),
            axis=1,
        )

        df["supported_sources"] = df["source_count"].apply(lambda x: len(x))

        df["pair_total_evidence"] = (
            df.groupby(["subject", "object"])["rel_evidence"].transform("sum")
        )

        df["evidence_proportion_in_group"] = (
                df["rel_evidence"] / df["pair_total_evidence"]
        )
        # Here handles rows to have multiple subject-object pairs
        df["opposite_type"] = df["type"].map(self.opposite_map)

        oppo_df = df[["subject", "object", "type", "rel_evidence"]].rename(
            columns={
                "type": "opposite_type",
                "rel_evidence": "opposite_rel_evidence",
            }
        )

        df = df.merge(
            oppo_df,
            on=["subject", "object", "opposite_type"],
            how="left",
        )

        df["has_oppo_type_in_group"] = (
            df["opposite_rel_evidence"].notna().astype(int)
        )

        df["oppo_type_count_ratio_in_pair"] = (
                df["rel_evidence"] / df["opposite_rel_evidence"]
        ).fillna(0)

        df["rel_evidence_log"] = np.log1p(df["rel_evidence"])

        df["pair_total_evidence_log"] = np.log1p(df["pair_total_evidence"])
        df["pair_total_evidence_log"] = np.log1p(df["pair_total_evidence_log"])

        df["supported_sources"] = np.log1p(df["supported_sources"])
        df["oppo_type_count_ratio_in_pair"] = np.log1p(
            df["oppo_type_count_ratio_in_pair"]
        )

        return df

    def predict_from_rows(self, rows):
        """
        A list of relation records. Each record is a dict with keys:
        ``subject`` (str), ``object`` (str), ``type`` (str),
        ``hash`` (int), ``statement`` (str), and
        ``source_count`` (dict[str, int]).
        e.g. rows = [
            {
                "subject": "MAP2K1",
                "object": "MAPK1",
                "type": "Phosphorylation",
                "hash": 123,
                "statement": "MAP2K1 phosphorylates MAPK1.",
                "source_count": {"reach": 3, "sparser": 1},
            }, ...]
        """

        df_input = self.build_input_from_rows(rows)

        if df_input.empty:
            return df_input

        X = df_input[self.feature_cols].copy()

        df_input["pred_prob"] = self.model.predict_proba(X)[:, 1]
        df_input["pred_label"] = self.model.predict(X)

        first_cols = ["subject", "object", "type", "pred_prob", "pred_label"]
        other_cols = [col for col in df_input.columns if col not in first_cols]

        df_input = df_input[first_cols + other_cols]

        return df_input.sort_values("pred_prob", ascending=False)

    def predict_from_hashes(self, hashes):
        """
        Given a list of statement hashes, return predicted labels in the same order.
        """

        hashes = [int(h) for h in hashes]

        res = self.db_client.get_statements_by_hash(hashes)

        hash_to_pair = {}

        for stmt in res.statements:
            agents = stmt.agent_list()

            if len(agents) != 2 or agents[0] is None or agents[1] is None:
                continue

            stmt_hash = int(stmt.get_hash())
            hash_to_pair[stmt_hash] = (agents[0].name, agents[1].name)

        pair_to_pred_df = {}

        for subject, obj in set(hash_to_pair.values()):
            pair_to_pred_df[(subject, obj)] = self.predict_pair(subject, obj)

        hash_to_label = {}

        for pred_df in pair_to_pred_df.values():
            if pred_df.empty:
                continue

            for _, row in pred_df.iterrows():
                for stmt_hash in row["hash"]:
                    hash_to_label[int(stmt_hash)] = int(row["pred_label"])

        return {h: hash_to_label.get(h) for h in hashes}
