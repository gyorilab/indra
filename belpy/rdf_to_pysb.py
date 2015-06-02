import re
import sys
import keyword
import urllib
import collections

import rdflib
from rdflib import URIRef, Namespace
from rdflib.namespace import RDF

from pysb import *
from pysb.core import SelfExporter, InvalidComponentNameError, \
                      ComplexPattern, ReactionPattern

from belpy.statements import *

SelfExporter.do_export = False

BEL = Namespace("http://www.openbel.org/")

prefixes = """
    PREFIX belvoc: <http://www.openbel.org/vocabulary/>
    PREFIX belsc: <http://www.openbel.org/bel/>
    PREFIX belns: <http://www.openbel.org/bel/namespace/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>"""

phospho_mods = [
    'PhosphorylationSerine',
    'PhosphorylationThreonine',
    'PhosphorylationTyrosine',
    'Phosphorylation',
]

def name_from_uri(uri):
    """Make the URI term usable as a valid Python identifier, if possible.

    First strips of the extra URI information by calling term_from_uri,
    then checks to make sure the name is a valid Python identifier.
    Currently fixes identifiers starting with numbers by prepending with
    the letter 'p'. For other cases it raises an exception.

    This function should be called when the string that is returned is to be
    used as a PySB component name, which are required to be valid Python
    identifiers.
    """
    name = term_from_uri(uri)
    # Handle the case where the string starts with a number
    if name[0].isdigit():
        name = 'p' + name
    if re.match("[_A-Za-z][_a-zA-Z0-9]*$", name) \
            and not keyword.iskeyword(name):
        pass
    else:
        raise InvalidComponentNameError(name)

    return name

def gene_name_from_uri(uri):
    return name_from_uri(uri).upper()

def term_from_uri(uri):
    """Basic conversion of RDF URIs to more friendly strings.

    Removes prepended URI information, and replaces spaces and hyphens with
    underscores.
    """
    if uri is None:
        return None
    # Strip gene name off from URI
    term = uri.rsplit('/')[-1]
    # Decode URL to handle spaces, special characters
    term = urllib.unquote(term)
    # Replace any spaces, hyphens, or periods with underscores
    term = term.replace(' ', '_')
    term = term.replace('-', '_')
    term = term.replace('.', '_')
    term = term.encode('ascii', 'ignore')
    return term

def strip_statement(uri):
    uri = uri.replace(r'http://www.openbel.org/bel/', '')
    uri = uri.replace(r'http://www.openbel.org/vocabulary/', '')
    return uri

class BelProcessor(object):
    def __init__(self, g):
        self.g = g
        self.belpy_stmts = []
        self.all_stmts = []
        self.converted_stmts = []
        self.degenerate_stmts = []
        self.indirect_stmts = []

    def get_evidence(self, statement):
        evidence = None
        citation = None
        annotations = []

        # Query for evidence text and citation
        q_evidence = prefixes + """
            SELECT ?evidenceText ?citation
            WHERE {
                <%s> belvoc:hasEvidence ?evidence .
                ?evidence belvoc:hasEvidenceText ?evidenceText .
                ?evidence belvoc:hasCitation ?citation .
            }
        """ % statement.format()
        res_evidence = self.g.query(q_evidence)
        for stmt in res_evidence:
            try:
                evidence = stmt[0].format()
                citation = stmt[1].format()
            except KeyError:
                warnings.warn('Problem converting evidence/citation string')

        # Query for all annotations of the statement
        q_annotations = prefixes + """
            SELECT ?annotation
            WHERE {
                <%s> belvoc:hasEvidence ?evidence .
                ?evidence belvoc:hasAnnotation ?annotation .
            }
        """ % statement.format()
        res_annotations = self.g.query(q_annotations)
        for stmt in res_annotations:
            annotations.append(stmt[0].format())

        return (citation, evidence, annotations)

    def get_modifications(self):
        q_phospho = prefixes + """
            SELECT ?enzName ?actType ?substrateName ?mod ?pos ?subject ?object
                   ?stmt
            WHERE {
                ?stmt a belvoc:Statement .
                ?stmt belvoc:hasRelationship belvoc:DirectlyIncreases .
                ?stmt belvoc:hasSubject ?subject .
                ?stmt belvoc:hasObject ?object .
                ?subject a belvoc:AbundanceActivity .
                ?subject belvoc:hasActivityType ?actType .
                ?subject belvoc:hasChild ?enzyme .
                ?enzyme a belvoc:ProteinAbundance .
                ?enzyme belvoc:hasConcept ?enzName .
                ?object a belvoc:ModifiedProteinAbundance .
                ?object belvoc:hasModificationType ?mod .
                ?object belvoc:hasChild ?substrate .
                ?substrate belvoc:hasConcept ?substrateName .
                OPTIONAL { ?object belvoc:hasModificationPosition ?pos . }
            }
        """

        # Now make the PySB for the phosphorylation
        res_phospho = self.g.query(q_phospho)

        for stmt in res_phospho:
            (citation, evidence, annotations) = self.get_evidence(stmt[7])
            # Parse out the elements of the query
            enz_name = gene_name_from_uri(stmt[0])
            act_type = name_from_uri(stmt[1])
            sub_name = gene_name_from_uri(stmt[2])
            mod = term_from_uri(stmt[3])
            mod_pos = term_from_uri(stmt[4])
            subj = term_from_uri(stmt[5])
            obj = term_from_uri(stmt[6])
            stmt_str = strip_statement(stmt[7])
            # Mark this as a converted statement
            self.converted_stmts.append(stmt_str)

            if act_type == 'Kinase' and mod in phospho_mods:
                self.belpy_stmts.append(
                        Phosphorylation(enz_name, sub_name, mod, mod_pos,
                                        stmt_str,
                                        citation, evidence, annotations))
            elif act_type == 'Catalytic':
                if mod == 'Hydroxylation':
                    self.belpy_stmts.append(
                            Hydroxylation(enz_name, sub_name, mod, mod_pos,
                                        stmt_str,
                                        citation, evidence, annotations))
                elif mod == 'Sumoylation':
                    self.belpy_stmts.append(
                            Sumoylation(enz_name, sub_name, mod, mod_pos,
                                        stmt_str,
                                        citation, evidence, annotations))
                elif mod == 'Acetylation':
                    self.belpy_stmts.append(
                            Acetylation(enz_name, sub_name, mod, mod_pos,
                                        stmt_str,
                                        citation, evidence, annotations))
                elif mod == 'Ubiquitination':
                    self.belpy_stmts.append(
                            Ubiquitination(enz_name, sub_name, mod, mod_pos,
                                        stmt_str,
                                        citation, evidence, annotations))
                else:
                    print "Warning: Unknown modification type!"
                    print("Activity: %s, Mod: %s, Mod_Pos: %s" %
                          (act_type, mod, mod_pos))
            else:
                print "Warning: Unknown modification type!"
                print("Activity: %s, Mod: %s, Mod_Pos: %s" %
                      (act_type, mod, mod_pos))

    def get_dephosphorylations(self):
        q_phospho = prefixes + """
            SELECT ?phosName ?substrateName ?mod ?pos ?subject ?object ?stmt
            WHERE {
                ?stmt a belvoc:Statement .
                ?stmt belvoc:hasRelationship belvoc:DirectlyDecreases .
                ?stmt belvoc:hasSubject ?subject .
                ?stmt belvoc:hasObject ?object .
                ?subject belvoc:hasActivityType belvoc:Phosphatase .
                ?subject belvoc:hasChild ?phosphatase .
                ?phosphatase a belvoc:ProteinAbundance .
                ?phosphatase belvoc:hasConcept ?phosName .
                ?object a belvoc:ModifiedProteinAbundance .
                ?object belvoc:hasModificationType ?mod .
                ?object belvoc:hasChild ?substrate .
                ?substrate belvoc:hasConcept ?substrateName .
                OPTIONAL { ?object belvoc:hasModificationPosition ?pos . }
            }
        """

        # Now make the PySB for the phosphorylation
        res_phospho = self.g.query(q_phospho)

        for stmt in res_phospho:
            (citation, evidence, annotations) = self.get_evidence(stmt[6])
            # Parse out the elements of the query
            phos_name = gene_name_from_uri(stmt[0])
            sub_name = gene_name_from_uri(stmt[1])
            mod = term_from_uri(stmt[2])
            mod_pos = term_from_uri(stmt[3])
            subj = term_from_uri(stmt[4])
            obj = term_from_uri(stmt[5])
            stmt_str = strip_statement(stmt[6])
            # Mark this as a converted statement
            self.converted_stmts.append(stmt_str)
            self.belpy_stmts.append(
                    Dephosphorylation(phos_name, sub_name, mod, mod_pos,
                                    stmt_str, citation,
                                    evidence, annotations))
    
    def get_composite_activating_mods(self):
        # To eliminate multiple matches, we use pos1 < pos2 but this will only work
        # if the pos is given, otherwise multiple matches of the same mod combination
        # may appear in the result
        q_mods = prefixes + """
            SELECT ?speciesName ?actType ?mod1 ?pos1 ?mod2 ?pos2 ?subject1 ?subject2 ?object ?rel ?stmt
            WHERE {
                ?stmt a belvoc:Statement .
                ?stmt belvoc:hasRelationship ?rel .
                ?stmt belvoc:hasSubject ?subject .
                ?stmt belvoc:hasObject ?object .
                ?object belvoc:hasActivityType ?actType .
                ?object belvoc:hasChild ?species .
                ?species a belvoc:ProteinAbundance .
                ?species belvoc:hasConcept ?speciesName .
                ?subject a belvoc:CompositeAbundance .
                ?subject belvoc:hasChild ?subject1 .
                ?subject1 a belvoc:ModifiedProteinAbundance .
                ?subject1 belvoc:hasModificationType ?mod1 .
                ?subject1 belvoc:hasChild ?species .
                ?subject belvoc:hasChild ?subject2 .
                ?subject2 a belvoc:ModifiedProteinAbundance .
                ?subject2 belvoc:hasModificationType ?mod2 .
                ?subject2 belvoc:hasChild ?species .
                OPTIONAL { ?subject1 belvoc:hasModificationPosition ?pos1 . }
                OPTIONAL { ?subject2 belvoc:hasModificationPosition ?pos2 . }
                FILTER ((?rel = belvoc:DirectlyIncreases ||
                        ?rel = belvoc:DirectlyDecreases) &&
                        ?pos1 < ?pos2)
            }
        """

        # Now make the PySB for the phosphorylation
        res_mods = self.g.query(q_mods)

        for stmt in res_mods:
            (citation, evidence, annotations) = self.get_evidence(stmt[9])
            # Parse out the elements of the query
            species_name = gene_name_from_uri(stmt[0])
            act_type = term_from_uri(stmt[1])
            mod1 = term_from_uri(stmt[2])
            mod_pos1 = term_from_uri(stmt[3])
            mod2 = term_from_uri(stmt[4])
            mod_pos2 = term_from_uri(stmt[5])
            subj1 = term_from_uri(stmt[6])
            subj2 = term_from_uri(stmt[7])
            obj = term_from_uri(stmt[8])
            rel = term_from_uri(stmt[9])
            stmt_str = strip_statement(stmt[10])
            # Mark this as a converted statement
            self.converted_stmts.append(stmt_str)
            self.belpy_stmts.append(
                    ActivityModification(species_name, (mod1, mod2), 
                                            (mod_pos1, mod_pos2),
                                            rel, act_type, stmt_str,
                                           citation, evidence, annotations))


    def get_activating_mods(self):
        q_mods = prefixes + """
            SELECT ?speciesName ?actType ?mod ?pos ?subject ?object ?rel ?stmt
            WHERE {
                ?stmt a belvoc:Statement .
                ?stmt belvoc:hasRelationship ?rel .
                ?stmt belvoc:hasSubject ?subject .
                ?stmt belvoc:hasObject ?object .
                ?object belvoc:hasActivityType ?actType .
                ?object belvoc:hasChild ?species .
                ?species a belvoc:ProteinAbundance .
                ?species belvoc:hasConcept ?speciesName .
                ?subject a belvoc:ModifiedProteinAbundance .
                ?subject belvoc:hasModificationType ?mod .
                ?subject belvoc:hasChild ?species .
                OPTIONAL { ?subject belvoc:hasModificationPosition ?pos . }
                FILTER (?rel = belvoc:DirectlyIncreases ||
                        ?rel = belvoc:DirectlyDecreases)
            }
        """

        # Now make the PySB for the phosphorylation
        res_mods = self.g.query(q_mods)

        for stmt in res_mods:
            (citation, evidence, annotations) = self.get_evidence(stmt[5])
            # Parse out the elements of the query
            species_name = gene_name_from_uri(stmt[0])
            act_type = term_from_uri(stmt[1])
            mod = term_from_uri(stmt[2])
            mod_pos = term_from_uri(stmt[3])
            subj = term_from_uri(stmt[4])
            obj = term_from_uri(stmt[5])
            rel = term_from_uri(stmt[6])
            stmt_str = strip_statement(stmt[7])
            # Mark this as a converted statement
            self.converted_stmts.append(stmt_str)
            self.belpy_stmts.append(
                    ActivityModification(species_name, (mod,), (mod_pos,), rel,
                                           act_type, stmt_str,
                                           citation, evidence, annotations))

    def get_complexes(self):
        # Find all complexes described in the corpus
        q_cmplx = prefixes + """
            SELECT ?complexTerm ?childName
            WHERE {
                ?complexTerm a belvoc:Term .
                ?complexTerm a belvoc:ComplexAbundance .
                ?complexTerm belvoc:hasChild ?child .
                ?child belvoc:hasConcept ?childName .
            }
        """
        # Run the query
        res_cmplx = self.g.query(q_cmplx)

        # Store the members of each complex in a dict of lists, keyed by the
        # term for the complex
        cmplx_dict = collections.defaultdict(list)
        for stmt in res_cmplx:
            cmplx_name = term_from_uri(stmt[0])
            child_name = gene_name_from_uri(stmt[1])
            cmplx_dict[cmplx_name].append(child_name)
        # Now iterate over the stored complex information and create binding
        # statements
        for cmplx_name, cmplx_list in cmplx_dict.iteritems():
            if len(cmplx_list) < 2:
                msg = 'Complex %s has less than 2 members! Skipping.' % \
                       cmplx_name
                warnings.warn(msg)
            else:
                self.belpy_stmts.append(Complex(cmplx_list))

    def get_activating_subs(self):
        """
        p_HGNC_NRAS_sub_Q_61_K_DirectlyIncreases_gtp_p_HGNC_NRAS
        p_HGNC_KRAS_sub_G_12_R_DirectlyIncreases_gtp_p_PFH_RAS_Family
        p_HGNC_BRAF_sub_V_600_E_DirectlyIncreases_kin_p_HGNC_BRAF
        """
        q_mods = prefixes + """
            SELECT ?enzyme_name ?sub_label ?act_type ?subject ?object ?stmt
            WHERE {
                ?stmt a belvoc:Statement .
                ?stmt belvoc:hasRelationship belvoc:DirectlyIncreases .
                ?stmt belvoc:hasSubject ?subject .
                ?stmt belvoc:hasObject ?object .
                ?subject a belvoc:ProteinAbundance .
                ?subject belvoc:hasConcept ?enzyme_name .
                ?subject belvoc:hasChild ?sub_expr .
                ?sub_expr rdfs:label ?sub_label .
                ?object a belvoc:AbundanceActivity .
                ?object belvoc:hasActivityType ?act_type .
                ?object belvoc:hasChild ?enzyme .
                ?enzyme a belvoc:ProteinAbundance .
                ?enzyme belvoc:hasConcept ?enzyme_name .
            }
        """

        # Now make the PySB for the phosphorylation
        res_mods = self.g.query(q_mods)

        for stmt in res_mods:
            (citation, evidence, annotations) = self.get_evidence(stmt[5])
            # Parse out the elements of the query
            enz_name = gene_name_from_uri(stmt[0])
            sub_expr = term_from_uri(stmt[1])
            act_type = term_from_uri(stmt[2])
            # Parse the WT and substituted residues from the node label.
            # Strangely, the RDF for substituted residue doesn't break the
            # terms of the BEL expression down into their meaning, as happens
            # for modified protein abundances. Instead, the substitution
            # just comes back as a string, e.g., "sub(V,600,E)". This code
            # parses the arguments back out using a regular expression.
            match = re.match('sub\(([A-Z]),([0-9]*),([A-Z])\)', sub_expr)
            if match:
                matches = match.groups()
                wt_residue = matches[0]
                position = matches[1]
                sub_residue = matches[2]
            else:
                print("Warning: Could not parse substitution expression %s" %
                      sub_expr)
                continue

            subj = term_from_uri(stmt[3])
            obj = term_from_uri(stmt[4])
            stmt_str = strip_statement(stmt[5])
            # Mark this as a converted statement
            self.converted_stmts.append(stmt_str)
            self.belpy_stmts.append(
                    ActivatingSubstitution(enz_name, wt_residue, position,
                                           sub_residue, act_type,
                                           stmt_str,
                                           citation, evidence, annotations))

    def get_activity_activity(self):
        # Query for all statements where the activity of one protein
        # directlyIncreases the activity of another protein, without reference
        # to a modification.
        q_stmts = prefixes + """
            SELECT ?subjName ?subjActType ?rel ?objName ?objActType
                   ?subj ?obj ?stmt
            WHERE {
                ?stmt a belvoc:Statement .
                ?stmt belvoc:hasSubject ?subj .
                ?stmt belvoc:hasObject ?obj .
                ?stmt belvoc:hasRelationship ?rel .
                ?subj belvoc:hasActivityType ?subjActType .
                ?subj belvoc:hasChild ?subjProt .
                ?subjProt belvoc:hasConcept ?subjName .
                ?obj belvoc:hasActivityType ?objActType .
                ?obj belvoc:hasChild ?objProt .
                ?objProt belvoc:hasConcept ?objName .
                FILTER (?rel = belvoc:DirectlyIncreases ||
                        ?rel = belvoc:DirectlyDecreases)
            }
        """
        res_stmts = self.g.query(q_stmts)

        for stmt in res_stmts:
            (citation, evidence, annotations) = self.get_evidence(stmt[7])
            subj_name = gene_name_from_uri(stmt[0])
            subj_activity = name_from_uri(stmt[1])
            rel = term_from_uri(stmt[2])
            obj_name = gene_name_from_uri(stmt[3])
            obj_activity = name_from_uri(stmt[4])
            subj = term_from_uri(stmt[5])
            obj = term_from_uri(stmt[6])
            stmt_str = strip_statement(stmt[7])
            # Mark this as a converted statement
            self.converted_stmts.append(stmt_str)

            # Distinguish the case when the activator is a RasGTPase
            # (since this may involve unique and stereotyped mechanisms)
            if subj_activity == 'GtpBound':
                self.belpy_stmts.append(
                     RasGtpActivityActivity(subj_name, subj_activity,
                                      rel, obj_name, obj_activity,
                                      stmt_str,
                                      citation, evidence, annotations))
            # If the object is a Ras-like GTPase, and the subject *increases*
            # its GtpBound activity, then the subject is a RasGEF
            elif obj_activity == 'GtpBound' and \
                 rel == 'DirectlyIncreases':
                self.belpy_stmts.append(
                        RasGef(subj_name, subj_activity, obj_name, 
                               stmt_str, citation, evidence, annotations))
            # If the object is a Ras-like GTPase, and the subject *decreases*
            # its GtpBound activity, then the subject is a RasGAP
            elif obj_activity == 'GtpBound' and \
                 rel == 'DirectlyDecreases':
                self.belpy_stmts.append(
                        RasGap(subj_name, subj_activity, obj_name, 
                               stmt_str, citation, evidence, annotations))
            # Otherwise, create a generic Activity->Activity statement
            else:
                self.belpy_stmts.append(
                     ActivityActivity(subj_name, subj_activity,
                                      rel, obj_name, obj_activity,
                                      stmt_str,
                                      citation, evidence, annotations))

            """
            #print "--------------------------------"
            print stmt_str
            print("This statement says that:")
            print("%s activity increases activity of %s" %
                  (subj_name, obj_name))
            print "It doesn't specify the site."
            act_mods = []
            for bps in self.belpy_stmts:
                if type(bps) == ActivatingModification and \
                   bps.monomer_name == obj_name:
                    act_mods.append(bps)
            # If we know about an activation modification...
            if act_mods:
                print "However, I happen to know about the following"
                print "activating modifications for %s:" % obj_name
                for act_mod in act_mods:
                    print "    %s at %s" % (act_mod.mod, act_mod.mod_pos)
        """

    def get_all_direct_statements(self):
        """Get all directlyIncreases/Decreases statements in the corpus.
        Stores the results of the query in self.all_stmts.
        """
        print "Getting all direct statements...\n"
        q_stmts = prefixes + """
            SELECT ?stmt
            WHERE {
                ?stmt a belvoc:Statement .
                ?stmt belvoc:hasSubject ?subj .
                ?stmt belvoc:hasObject ?obj .
                {
                  { ?subj a belvoc:AbundanceActivity . }
                  UNION
                  { ?subj a belvoc:ComplexAbundance . }
                  UNION
                  { ?subj a belvoc:ProteinAbundance . }
                  UNION
                  { ?subj a belvoc:ModifiedProteinAbundance . }
                }
                {
                  { ?obj a belvoc:AbundanceActivity . }
                  UNION
                  { ?obj a belvoc:ComplexAbundance . }
                  UNION
                  { ?obj a belvoc:ProteinAbundance . }
                  UNION
                  { ?obj a belvoc:ModifiedProteinAbundance . }
                }

                {
                  { ?stmt belvoc:hasRelationship belvoc:DirectlyIncreases . }
                  UNION
                  { ?stmt belvoc:hasRelationship belvoc:DirectlyDecreases . }
                }
            }
        """
        q_stmts = prefixes + """
            SELECT ?stmt
            WHERE {
                ?stmt a belvoc:Statement .
                {
                  { ?stmt belvoc:hasRelationship belvoc:DirectlyIncreases . }
                  UNION
                  { ?stmt belvoc:hasRelationship belvoc:DirectlyDecreases . }
                }
            }
        """

        res_stmts = self.g.query(q_stmts)
        self.all_stmts = [strip_statement(stmt[0]) for stmt in res_stmts]

    def get_indirect_statements(self):
        q_stmts = prefixes + """
            SELECT ?stmt
            WHERE {
                ?stmt a belvoc:Statement .
                {
                  { ?stmt belvoc:hasRelationship belvoc:Increases . }
                  UNION
                  { ?stmt belvoc:hasRelationship belvoc:Decreases . }
                }
            }
        """

        res_stmts = self.g.query(q_stmts)
        self.indirect_stmts = [strip_statement(stmt[0]) for stmt in res_stmts]

    def get_degenerate_statements(self):
        print "Checking for 'degenerate' statements...\n"
        # Get rules of type protein X -> activity Y
        q_stmts = prefixes + """
            SELECT ?stmt
            WHERE {
                ?stmt a belvoc:Statement .
                ?stmt belvoc:hasSubject ?subj .
                ?stmt belvoc:hasObject ?obj .
                {
                  { ?stmt belvoc:hasRelationship belvoc:DirectlyIncreases . }
                  UNION
                  { ?stmt belvoc:hasRelationship belvoc:DirectlyDecreases . }
                }
                {
                  { ?subj a belvoc:ProteinAbundance . }
                  UNION
                  { ?subj a belvoc:ModifiedProteinAbundance . }
                }
                ?subj belvoc:hasConcept ?xName .
                {
                  {
                    ?obj a belvoc:ProteinAbundance .
                    ?obj belvoc:hasConcept ?yName .
                  }
                  UNION
                  {
                    ?obj a belvoc:ModifiedProteinAbundance .
                    ?obj belvoc:hasChild ?proteinY .
                    ?proteinY belvoc:hasConcept ?yName .
                  }
                  UNION
                  {
                    ?obj a belvoc:AbundanceActivity .
                    ?obj belvoc:hasChild ?objChild .
                    ?objChild a belvoc:ProteinAbundance .
                    ?objChild belvoc:hasConcept ?yName .
                  }
                }
                FILTER (?xName != ?yName)
            }
        """
        res_stmts = self.g.query(q_stmts)

        print "Protein -> Protein/Activity statements:"
        print "---------------------------------------"
        for stmt in res_stmts:
            stmt_str = strip_statement(stmt[0])
            print stmt_str
            self.degenerate_stmts.append(stmt_str)

    def print_statement_coverage(self):
        """Display how many of the direct statements have been converted,
        and how many are considered 'degenerate' and not converted."""

        if not self.all_stmts:
            self.get_all_direct_statements()
        if not self.degenerate_stmts:
            self.get_degenerate_statements()
        if not self.indirect_stmts:
            self.get_indirect_statements()

        print
        print("Total indirect statements: %d" % len(self.indirect_stmts))
        print("Total direct statements: %d" % len(self.all_stmts))
        print("Converted statements: %d" % len(self.converted_stmts))
        print("Degenerate statements: %d" % len(self.degenerate_stmts))
        print(">> Total unhandled statements: %d" %
              (len(self.all_stmts) - len(self.converted_stmts) -
               len(self.degenerate_stmts)))

        print
        print "--- Unhandled statements ---------"
        for stmt in self.all_stmts:
            if not (stmt in self.converted_stmts or
                    stmt in self.degenerate_stmts):
                print stmt

    def print_statements(self):
        for i, stmt in enumerate(self.belpy_stmts):
            print "%s: %s" % (i, stmt)

    def make_model(self):
        model = Model()
        for stmt in self.belpy_stmts:
            stmt.monomers(model)
        for stmt in self.belpy_stmts:
            stmt.assemble(model)
        return model

def add_default_initial_conditions(model):
    try:
        default_ic = model.parameters['default_ic']
    except KeyError:
        default_ic = Parameter('default_ic', 100.)
        model.add_component(default_ic)

    # Iterate over all monomers
    for m in model.monomers:
        # Build up monomer pattern dict
        sites_dict = {}
        for site in m.sites:
            if site in m.site_states:
                sites_dict[site] = m.site_states[site][0]
            else:
                sites_dict[site] = None
        mp = m(**sites_dict)
        model.initial(mp, default_ic)

def rdf_to_pysb(rdf_filename, initial_conditions=True):
    # Parse the RDF
    g = rdflib.Graph()
    g.parse(rdf_filename, format='nt')
    # Build BelPy statements from RDF
    bp = BelProcessor(g)
    bp.get_complexes()
    bp.get_activating_subs()
    bp.get_modifications()
    bp.get_dephosphorylations()
    bp.get_activating_mods()
    bp.get_composite_activating_mods()
    bp.get_activity_activity()

    # Print some output about the process
    bp.print_statement_coverage()
    print "\n--- Converted BelPy Statements -------------"
    bp.print_statements()

    # Make the PySB model and return
    model = bp.make_model()
    if initial_conditions:
        add_default_initial_conditions(model)
    return (bp, model)

if __name__ == '__main__':
    # Make sure the user passed in an RDF filename
    if len(sys.argv) < 2:
        print "Usage: python rdf_to_pysb.py file.rdf"
        sys.exit()
    # We take the RDF filename as the argument
    rdf_filename = sys.argv[1]
    (bp, model) = rdf_to_pysb(rdf_filename, initial_conditions=True)
