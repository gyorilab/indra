"""This module implements an SQLite back end to the
INDRA BioOntology."""

import os
import json
import sqlite3
import logging
from collections import defaultdict
from indra.ontology.ontology_graph import IndraOntology
from indra.ontology.bio.ontology import CACHE_DIR, BioOntology


logger = logging.getLogger(__name__)


DEFAULT_SQLITE_ONTOLOGY = os.path.join(CACHE_DIR, 'bio_ontology.db')


class SqliteOntology(IndraOntology):
    def __init__(self, db_path=DEFAULT_SQLITE_ONTOLOGY):
        super().__init__()
        self.db_path = db_path
        build_sqlite_ontology(db_path)
        conn = sqlite3.connect(db_path)
        self.cur = conn.cursor()
        self._initialized = True

    def initialize(self):
        pass

    def isa_or_partof(self, ns1, id1, ns2, id2):
        q = """SELECT 1 FROM relationships
               WHERE child_id=? AND child_ns=? AND parent_id=? AND parent_ns=?
               LIMIT 1;"""
        self.cur.execute(q, (id1, ns1, id2, ns2))
        return self.cur.fetchone() is not None

    def child_rel(self, ns, id, rel_types):
        q = """SELECT children FROM child_lookup
               WHERE parent_id=? AND parent_ns=?
               LIMIT 1;"""
        if rel_types and 'isa' in rel_types or 'partof' in rel_types:
            rel_types |= {'isa_or_partof'}
        self.cur.execute(q, (id, ns))
        res = self.cur.fetchone()
        if res is None:
            yield from []
        else:
            children = res[0].split(',')
            for child in children:
                curie, rel_type = child.split('|', 1)
                if rel_type in rel_types:
                    yield tuple(curie.split(':', 1))

    def get_parents(self, ns, id):
        # Note that for isa/partof ontological child/parent is the
        # opposite of the graph-based child/parent
        return list(self.child_rel(ns, id, {'isa_or_partof'}))

    def get_children(self, ns, id, ns_filter=None):
        # Note that for isa/partof ontological child/parent is the
        # opposite of the graph-based child/parent
        children = list(self.parent_rel(ns, id, {'isa_or_partof'}))
        if ns_filter:
            children = [(cns, cid) for cns, cid in children
                        if cns in ns_filter]
        return children

    def parent_rel(self, ns, id, rel_types):
        q = """SELECT parents FROM parent_lookup
               WHERE child_id=? AND child_ns=?
               LIMIT 1;"""
        if rel_types and 'isa' in rel_types or 'partof' in rel_types:
            rel_types |= {'isa_or_partof'}
        self.cur.execute(q, (id, ns))
        res = self.cur.fetchone()
        if res is None:
            yield from []
        else:
            parents = res[0].split(',')
            for parent in parents:
                curie, rel_type = parent.split('|', 1)
                if rel_type in rel_types:
                    yield tuple(curie.split(':', 1))

    def get_node_property(self, ns, id, property):
        q = """SELECT properties FROM node_properties
               WHERE id=? AND ns=?
               LIMIT 1;"""
        self.cur.execute(q, (id, ns))
        res = self.cur.fetchone()
        if res is None:
            return None
        props = json.loads(res[0])
        return props.get(property)

    def get_id_from_name(self, ns, name):
        return None


def build_sqlite_ontology(db_path=DEFAULT_SQLITE_ONTOLOGY, force=False):
    # If the database already exists and we are not forcing a rebuild, return
    if os.path.exists(db_path) and not force:
        return

    if force:
        try:
            logger.info('Removing existing SQLite ontology at %s' % db_path)
            os.remove(db_path)
        except FileNotFoundError:
            pass

    # Initialize the bio ontology and build the transitive closure
    bio_ontology = BioOntology()
    bio_ontology.initialize()
    bio_ontology._build_transitive_closure()

    # Set up connection
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    logger.info('Building SQLite ontology at %s' % db_path)
    # First, we create the relationships table and populate
    # it with child/parent pairs
    q = """CREATE TABLE relationships (
        child_id TEXT NOT NULL,
        child_ns TEXT NOT NULL,
        parent_id TEXT NOT NULL,
        parent_ns TEXT NOT NULL,
        rel_type TEXT NOT NULL,
        UNIQUE (child_id, child_ns, parent_id, parent_ns)
    );"""
    cur.execute(q)

    # Insert into the database in chunks
    chunk_size = 10000
    # Note: the transitive closure consists of pairs with the first element
    # being the ontological child and the second the parent. However,
    # in a graph representation isa/partof edges point from the ontological
    # child to the ontological parent. Here, we need to follow the graph-based
    # parent->child relationships, not the ontological ones.
    tc = sorted(bio_ontology.transitive_closure)
    all_children = defaultdict(set)
    all_parents = defaultdict(set)
    for i in range(0, len(tc), chunk_size):
        chunk = tc[i:i+chunk_size]
        chunk_values = [(parent.split(':', 1)[1], parent.split(':')[0],
                         child.split(':', 1)[1], child.split(':')[0])
                        for child, parent in chunk]
        for cid, cns, pid, pns in chunk_values:
            all_children[(pid, pns)].add(
                '%s:%s|%s' % (cns, cid, 'isa_or_partof'))
            all_parents[(cid, cns)].add(
                '%s:%s|%s' % (pns, pid, 'isa_or_partof'))
        cur.executemany("""INSERT INTO relationships (parent_id, 
                            parent_ns, child_id, child_ns, rel_type)
                            VALUES (?, ?, ?, ?, 'isa_or_partof');""",
                        chunk_values)

    for parent, child, data in bio_ontology.edges(data=True):
        parent_ns, parent_id = bio_ontology.get_ns_id(parent)
        child_ns, child_id = bio_ontology.get_ns_id(child)
        rel_type = data.get('type')
        if rel_type in {'isa', 'partof'}:
            continue
        all_children[(parent_id, parent_ns)].add(
            '%s:%s|%s' % (child_ns, child_id, rel_type))
        all_parents[(child_id, child_ns)].add(
            '%s:%s|%s' % (parent_ns, parent_id, rel_type))
        cur.execute("""INSERT INTO relationships (parent_id,
                        parent_ns, child_id, child_ns, rel_type)
                        VALUES (?, ?, ?, ?, ?);""",
                    (parent_id, parent_ns, child_id, child_ns, rel_type))

    q = """CREATE INDEX idx_child_parent ON relationships 
        (child_id, child_ns, parent_id, parent_ns);"""
    cur.execute(q)

    # Next, create child and parent lookup tables and populate them
    q = """CREATE TABLE child_lookup (
        parent_id TEXT NOT NULL,
        parent_ns TEXT NOT NULL,
        children TEXT NOT NULL,
        UNIQUE (parent_id, parent_ns)
    );"""
    cur.execute(q)
    q = """CREATE TABLE parent_lookup (
        child_id TEXT NOT NULL,
        child_ns TEXT NOT NULL,
        parents TEXT NOT NULL,
        UNIQUE (child_id, child_ns)
    );"""
    cur.execute(q)
    for (pid, pns), children in all_children.items():
        cur.execute("INSERT INTO child_lookup (parent_id, parent_ns, children) "
                    "VALUES (?, ?, ?);",
                    (pid, pns, ','.join(children)))
    for (cid, cns), parents in all_parents.items():
        cur.execute("INSERT INTO parent_lookup (child_id, child_ns, parents) "
                    "VALUES (?, ?, ?);",
                    (cid, cns, ','.join(parents)))
    # Now add indices to the lookup tables
    q = """CREATE INDEX idx_child_lookup ON child_lookup 
        (parent_id, parent_ns);"""
    cur.execute(q)
    q = """CREATE INDEX idx_parent_lookup ON parent_lookup 
        (child_id, child_ns);"""
    cur.execute(q)

    # Create node property table
    # Here we just keep track of the namespace and ID,
    # and then put all the data into a json string
    q = """CREATE TABLE node_properties (
        id TEXT NOT NULL,
        ns TEXT NOT NULL,
        properties TEXT NOT NULL,
        UNIQUE (id, ns)
    );"""
    cur.execute(q)

    for node in bio_ontology.nodes:
        ns, id = bio_ontology.get_ns_id(node)
        props = json.dumps(bio_ontology.nodes[node])
        cur.execute("INSERT INTO node_properties (id, ns, properties) "
                    "VALUES (?, ?, ?);", (id, ns, props))

    conn.commit()
    conn.close()
    logger.info('Finished building SQLite ontology')
