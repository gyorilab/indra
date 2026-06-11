import csv
import gzip
import json
import pickle
from collections import Counter, defaultdict
from functools import lru_cache
from tempfile import NamedTemporaryFile

import boto3
import joblib
import gilda
import numpy as np
import pandas as pd

from indra.ontology.bio import bio_ontology
from indra.sources import indra_db_rest
from indra.statements import AddModification, RemoveModification, \
    SelfModification, modclass_to_inverse



class StatementTypeClassification:
    """Predict whether a statement type is correct based on polarity and evidence patterns within an agent-agent group."""

    MODEL_BUCKET = "bigmech"
    MODEL_KEY = "classification_model.joblib"

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

        s3 = boto3.client("s3")
        with NamedTemporaryFile(suffix=".joblib") as tmp:
            s3.download_file(self.MODEL_BUCKET, self.MODEL_KEY, tmp.name)
            return joblib.load(tmp.name)

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

    def _make_stmt_row(self, subject, obj, stmt_type, stmt_hash, source_count,
                       statement=None):
        rel_evidence = sum(source_count.values())
        in_signor = int("signor" in source_count)
        row = {
            "subject": subject,
            "object": obj,
            "type": stmt_type,
            "hash": stmt_hash,
        }
        if statement is not None:
            row["statement"] = statement
        row.update({
            "source_count": source_count,
            "rel_evidence": rel_evidence,
            "in_signor": in_signor,
        })
        return row

    def _add_predictions(self, df_input):
        X = df_input[self.feature_cols].copy()
        df_input["pred_prob"] = self.model.predict_proba(X)[:, 1]
        df_input["pred_label"] = self.model.predict(X)
        return df_input

    @staticmethod
    def _pred_df_to_hash_labels(pred_df, cast_hash=False):
        hash_to_label = {}
        for _, row in pred_df.iterrows():
            label = int(row["pred_label"])
            hashes = row["hash"]
            if not isinstance(hashes, list):
                hashes = [hashes]
            for stmt_hash in hashes:
                if cast_hash:
                    stmt_hash = int(stmt_hash)
                hash_to_label[stmt_hash] = label
        return hash_to_label

    @staticmethod
    @lru_cache(maxsize=500000)
    def is_family_complex(name):
        scored_matches = gilda.ground(name)
        if not scored_matches:
            return False

        ns, entity_id = scored_matches[0].term.get_curie().split(":")
        ent_type = bio_ontology.get_type(ns.upper(), entity_id)
        return ent_type == "protein_family_complex"

    def stmt_to_row(self, stmt, source_counts):
        agents = stmt.agent_list()

        if len(agents) != 2:
            return None

        if agents[0] is None or agents[1] is None:
            return None

        stmt_hash = stmt.get_hash()
        source_count = source_counts.get(stmt_hash, {})

        return self._make_stmt_row(
            agents[0].name,
            agents[1].name,
            stmt.__class__.__name__,
            stmt_hash,
            source_count,
            statement=str(stmt),
        )

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

    def predict_pair(self, subject, object, simple_result=False):
        df_input = self.build_input_from_rows(
            self.get_pair_df(subject, object),
            pair_direction=(subject, object),
        )

        if df_input.empty:
            return {} if simple_result else df_input

        df_input = self._add_predictions(df_input)

        if simple_result:
            return self._pred_df_to_hash_labels(df_input)

        first_cols = ["subject", "object", "type", "pred_prob", "pred_label"]
        other_cols = [col for col in df_input.columns if col not in first_cols]
        df_input = df_input[first_cols + other_cols]

        return df_input.sort_values("pred_prob", ascending=False)

    def build_input_from_rows(self, rows, pair_direction=None):
        df = pd.DataFrame(rows)

        if df.empty:
            return df

        if pair_direction is not None:
            pair_subject, pair_object = pair_direction
            mask = (
                (df["type"] == "Complex")
                & (df["subject"] == pair_object)
                & (df["object"] == pair_subject)
            )
            df.loc[mask, ["subject", "object"]] = [
                pair_subject, pair_object
            ]

        df["rel_evidence"] = df["source_count"].apply(lambda x: sum(x.values()))
        df["in_signor"] = df["source_count"].apply(lambda x: int("signor" in x))

        agg_spec = {
            "hash": list,
            "source_count": self.merge_source_count_dicts,
            "rel_evidence": "sum",
            "in_signor": "max",
        }
        if "statement" in df.columns:
            agg_spec["statement"] = list

        df = df.groupby(["subject", "object", "type"], as_index=False).agg(
            agg_spec
        )

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
        ``hash`` (int), and ``source_count`` (dict[str, int]).
        e.g. rows = [
            {
                "subject": "MAP2K1",
                "object": "MAPK1",
                "type": "Phosphorylation",
                "hash": 123,
                "source_count": {"reach": 3, "sparser": 1},
            }, ...]
        """

        df_input = self.build_input_from_rows(rows)
        if df_input.empty:
            return {}

        df_input = self._add_predictions(df_input)
        return self._pred_df_to_hash_labels(df_input)

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

            hash_to_label.update(
                self._pred_df_to_hash_labels(pred_df, cast_hash=True)
            )

        return {h: hash_to_label.get(h) for h in hashes}

    @staticmethod
    @lru_cache(maxsize=1)
    def get_ptm_types():
        return {
            cls.__name__
            for cls in (
                AddModification.__subclasses__()
                + RemoveModification.__subclasses__()
                + SelfModification.__subclasses__()
            )
        }

    def get_consensus_rules(self):
        ptm_types = self.get_ptm_types()
        return [
            {
                "required_effect": {"Activation"},
                "required_mechanism": ptm_types | {"Complex"},
                "effect": "Activation",
            },
            {
                "required_effect": {"Inhibition"},
                "required_mechanism": ptm_types | {"Complex"},
                "effect": "Inhibition",
            },
            {
                "required_effect": {"IncreaseAmount"},
                "required_mechanism": ptm_types,
                "effect": "IncreaseAmount",
            },
            {
                "required_effect": {"DecreaseAmount"},
                "required_mechanism": ptm_types,
                "effect": "DecreaseAmount",
            },
        ]

    def resolve_opposite_mechanisms(self, mechanism_types, group):
        mechanism_types = set(mechanism_types)

        for mech in list(mechanism_types):
            opposite = self.opposite_map.get(mech)
            if opposite is None or opposite not in mechanism_types:
                continue

            mech_score = group[group["type"] == mech]["pred_prob"].max()
            opposite_score = group[group["type"] == opposite]["pred_prob"].max()

            if mech_score >= opposite_score:
                mechanism_types.discard(opposite)
            else:
                mechanism_types.discard(mech)

        return mechanism_types

    def consensus_from_rows(self, rows, pair_subject=None, pair_object=None):
        pair_direction = None
        if pair_subject is not None and pair_object is not None:
            pair_direction = (pair_subject, pair_object)

        df = self.build_input_from_rows(rows, pair_direction=pair_direction)

        if df.empty:
            return None

        df = self._add_predictions(df)

        true_df = df[df["pred_label"] == 1].copy()

        if true_df.empty:
            return None

        records = []

        for (subj, obj), group in true_df.groupby(["subject", "object"]):
            true_types = set(group["type"])
            candidates = []

            for rule in self.get_consensus_rules():
                effect_types = true_types & rule["required_effect"]
                mechanism_types = true_types & rule["required_mechanism"]

                if not effect_types:
                    continue

                mechanism_types = self.resolve_opposite_mechanisms(
                    mechanism_types,
                    group,
                )

                support_types = effect_types | mechanism_types
                support = group[group["type"].isin(support_types)]

                candidates.append(
                    {
                        "effect": rule["effect"],
                        "support_score": float(support["pred_prob"].mean()),
                        "effect_rel_evidence": int(
                            group[
                                group["type"].isin(effect_types)
                            ]["rel_evidence"].sum()
                        ),
                        "mechanism_rel_evidence": int(
                            group[
                                group["type"].isin(mechanism_types)
                            ]["rel_evidence"].sum()
                        ),
                        "effect_types": sorted(effect_types),
                        "mechanism_types": sorted(mechanism_types),
                    }
                )

            if not candidates and true_types == {"Complex"}:
                complex_group = group[group["type"] == "Complex"]

                candidates.append(
                    {
                        "effect": "Binding",
                        "support_score": float(
                            complex_group["pred_prob"].mean()
                        ),
                        "effect_rel_evidence": int(
                            complex_group["rel_evidence"].sum()
                        ),
                        "mechanism_rel_evidence": 0,
                        "effect_types": ["Complex"],
                        "mechanism_types": [],
                    }
                )

            if not candidates:
                continue

            primary = max(
                candidates,
                key=lambda x: (
                    x["effect_rel_evidence"],
                    x["mechanism_rel_evidence"],
                    x["support_score"],
                ),
            )

            records.append(
                {
                    "subject": subj,
                    "object": obj,
                    "primary": primary,
                    "alternatives": [
                        c for c in candidates
                        if c != primary
                    ],
                    "true_types": sorted(true_types),
                    "pair_total_evidence": int(
                        group["pair_total_evidence"].max()
                    ),
                }
            )

        return records

    @staticmethod
    def agents_are_grounded(agents):
        if len(agents) != 2:
            return False
        if agents[0] is None or agents[1] is None:
            return False
        return all(
            set(agent.db_refs) - {"TEXT", "TEXT_NORM"}
            for agent in agents
        )

    def dump_pair_to_rows(
            self,
            unique_stmts_fpath,
            source_counts_fpath,
            pair_to_rows_fpath,
            total=None,
            json_loader=json.loads,
    ):
        from indra.statements import stmt_from_json
        from tqdm import tqdm

        with open(source_counts_fpath, "rb") as fh:
            source_counts = pickle.load(fh)

        pair_to_rows = defaultdict(list)

        with gzip.open(unique_stmts_fpath, "rt") as fh:
            reader = csv.reader(fh, delimiter="\t")
            reader = tqdm(reader, total=total)

            for stmt_hash, stmt_json_str in reader:
                stmt_json = json_loader(stmt_json_str)
                stmt = stmt_from_json(stmt_json)
                agents = stmt.agent_list()
                if not self.agents_are_grounded(agents):
                    continue

                sub, obj = agents[0].name, agents[1].name
                stmt_hash = int(stmt_hash)
                source_count = source_counts.get(stmt_hash)
                row = self._make_stmt_row(
                    sub,
                    obj,
                    stmt.__class__.__name__,
                    stmt_hash,
                    source_count,
                )
                pair_to_rows[(sub, obj)].append(row)

        with open(pair_to_rows_fpath, "wb") as fh:
            pickle.dump(pair_to_rows, fh, protocol=pickle.HIGHEST_PROTOCOL)

        return pair_to_rows

    def dump_agent_pair_consensus_cache(
            self,
            pair_to_rows,
            cache_fpath,
    ):
        from tqdm import tqdm

        cache = {}
        pairs = tqdm(pair_to_rows.items(), total=len(pair_to_rows))

        for (pair_subject, pair_object), rows in pairs:
            if not rows:
                continue

            records = self.consensus_from_rows(
                rows,
                pair_subject=pair_subject,
                pair_object=pair_object,
            )

            if not records:
                continue

            for record in records:
                key = f'{record["subject"]}|{record["object"]}'
                cache[key] = record

        with gzip.open(cache_fpath, "wt") as fh:
            json.dump(cache, fh)

        return cache

    def all_stmt_prediction_dump(
            self,
            unique_stmts_fpath,
            source_counts_fpath,
            pair_to_rows_fpath,
            cache_fpath,
            total=None,
            json_loader=json.loads,
    ):
        pair_to_rows = self.dump_pair_to_rows(
            unique_stmts_fpath,
            source_counts_fpath,
            pair_to_rows_fpath,
            total=total,
            json_loader=json_loader,
        )
        return self.dump_agent_pair_consensus_cache(
            pair_to_rows,
            cache_fpath,
        )
