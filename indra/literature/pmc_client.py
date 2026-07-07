import re
import logging
import os
import time
import requests
from functools import lru_cache
from lxml import etree
import xml.etree.ElementTree as ET

from indra.literature import pubmed_client
from indra.util import UnicodeXMLTreeBuilder as UTB


logger = logging.getLogger(__name__)

pmc_url = 'https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/'
pmid_convert_url = 'https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/'
pmc_s3_base_url = 'https://pmc-oa-opendata.s3.amazonaws.com'
s3_nsmap = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}

# Paths to resource files
pmids_fulltext_path = os.path.join(os.path.dirname(__file__),
                                   'pmids_fulltext.txt')
pmids_oa_xml_path = os.path.join(os.path.dirname(__file__),
                                 'pmids_oa_xml.txt')
pmids_oa_txt_path = os.path.join(os.path.dirname(__file__),
                                 'pmids_oa_txt.txt')
pmids_auth_xml_path = os.path.join(os.path.dirname(__file__),
                                   'pmids_auth_xml.txt')
# Define global dict containing lists of PMIDs among mineable PMCs
# to be lazily initialized
pmids_fulltext_dict = {}


@lru_cache(maxsize=10000)
def get_s3_versions(pmcid):
    """Return available versions of a PMC article on the PMC Cloud S3 bucket.

    Parameters
    ----------
    pmcid : str
        A PubMed Central ID in 'PMC<digits>' form.

    Returns
    -------
    tuple of int
        Sorted tuple of available version numbers, or an empty tuple if the
        article is not present on the bucket.
    """
    params = {'prefix': f'{pmcid}.', 'delimiter': '/'}
    res = requests.get(pmc_s3_base_url, params=params)
    res.raise_for_status()
    tree = ET.fromstring(res.content)
    versions = []
    for prefix_el in tree.findall('s3:CommonPrefixes/s3:Prefix', s3_nsmap):
        m = re.match(rf'{re.escape(pmcid)}\.(\d+)/', prefix_el.text or '')
        if m:
            versions.append(int(m.group(1)))
    return tuple(sorted(versions))


def get_latest_s3_version(pmcid):
    """Return the latest available version of a PMC article on S3.

    Parameters
    ----------
    pmcid : str
        A PubMed Central ID in 'PMC<digits>' form.

    Returns
    -------
    Optional[int]
        The highest available version number, or None if the article is not
        present on the bucket.
    """
    versions = get_s3_versions(pmcid)
    return max(versions) if versions else None


def list_article_files_s3(pmcid, version=None):
    """List the S3 object keys for a PMC article on the PMC Cloud bucket.

    Parameters
    ----------
    pmcid : str
        A PubMed Central ID in 'PMC<digits>' form.
    version : Optional[int]
        The article version to list. If None, the latest available version
        is used.

    Returns
    -------
    list of str
        List of S3 object keys under the PMC<id>.<version>/ prefix. Empty
        if the article (or requested version) is not present.
    """
    if version is None:
        version = get_latest_s3_version(pmcid)
        if version is None:
            return []
    prefix = f'{pmcid}.{version}/'
    keys = []
    marker = ''
    while True:
        params = {'prefix': prefix, 'marker': marker}
        res = requests.get(pmc_s3_base_url, params=params)
        res.raise_for_status()
        tree = ET.fromstring(res.content)
        for contents in tree.findall('s3:Contents', s3_nsmap):
            key = contents.findtext('s3:Key', namespaces=s3_nsmap)
            if key:
                keys.append(key)
        truncated = tree.findtext('s3:IsTruncated', namespaces=s3_nsmap)
        if not truncated == 'true':
            break
        marker = keys[-1] if keys else ''
        if not marker:
            break
    return keys


def _get_s3_artifact(pmcid, ext, version=None):
    """Fetch a named artifact for a PMC article from the PMC Cloud S3 bucket.

    The artifact is fetched from the canonical key
    ``PMC<id>.<version>/PMC<id>.<version>.<ext>``.

    Parameters
    ----------
    pmcid : str
        A PubMed Central ID in 'PMC<digits>' form.
    ext : str
        The artifact file extension, e.g. 'xml', 'txt', 'json', or 'pdf'.
    version : Optional[int]
        The article version to fetch. If None, the latest available version
        is resolved via :func:`get_latest_s3_version`.

    Returns
    -------
    Optional[requests.Response]
        The HTTP response if the artifact was fetched successfully, or None
        if the article is not present on the bucket.
    """
    if version is None:
        version = get_latest_s3_version(pmcid)
        if version is None:
            return None
    url = f'{pmc_s3_base_url}/{pmcid}.{version}/{pmcid}.{version}.{ext}'
    res = requests.get(url)
    res.raise_for_status()
    return res


def get_metadata_s3(pmcid, version=None):
    """Return the JSON metadata for a PMC article from the PMC Cloud bucket.

    Parameters
    ----------
    pmcid : str
        A PubMed Central ID in 'PMC<digits>' form.
    version : Optional[int]
        The article version to fetch. If None, the latest available version
        is used.

    Returns
    -------
    Optional[dict]
        The parsed JSON metadata dict, containing keys such as 'pmid',
        'doi', 'title', 'citation', 'license_code', 'is_retracted', and
        s3:// URLs for the text/xml/pdf/media files. None if the article
        is not present on the bucket.
    """
    res = _get_s3_artifact(pmcid, 'json', version=version)
    return res.json() if res is not None else None


def get_xml_s3(pmcid, version=None):
    """Return the NLM XML for a PMC article from the PMC Cloud S3 bucket.

    Parameters
    ----------
    pmcid : str
        A PubMed Central ID in 'PMC<digits>' form.
    version : Optional[int]
        The article version to fetch. If None, the latest available version
        is used.

    Returns
    -------
    Optional[str]
        The XML content as a unicode string, or None if the article is not
        present on the bucket.
    """
    res = _get_s3_artifact(pmcid, 'xml', version=version)
    return res.text if res is not None else None


def get_text_s3(pmcid, version=None):
    """Return the plain text for a PMC article from the PMC Cloud S3 bucket.

    Parameters
    ----------
    pmcid : str
        A PubMed Central ID in 'PMC<digits>' form.
    version : Optional[int]
        The article version to fetch. If None, the latest available version
        is used.

    Returns
    -------
    Optional[str]
        The plain-text content as a unicode string, or None if the article
        is not present on the bucket.
    """
    res = _get_s3_artifact(pmcid, 'txt', version=version)
    return res.text if res is not None else None


def get_pdf_s3(pmcid, version=None):
    """Return the PDF for a PMC article from the PMC Cloud S3 bucket.

    Parameters
    ----------
    pmcid : str
        A PubMed Central ID in 'PMC<digits>' form.
    version : Optional[int]
        The article version to fetch. If None, the latest available version
        is used.

    Returns
    -------
    Optional[str]
        The PDF content or None if the article is not present on the bucket.
    """
    res = _get_s3_artifact(pmcid, 'pdf', version=version)
    return res.content if res is not None else None


def download_article_files_s3(pmcid, out_dir, version=None, include=None):
    """Download a PMC article's files from the PMC Cloud S3 bucket.

    Files are saved under ``<out_dir>/PMC<id>.<version>/<filename>``,
    mirroring the bucket's prefix layout.

    Parameters
    ----------
    pmcid : str
        A PubMed Central ID in 'PMC<digits>' form.
    out_dir : str
        Local directory where files will be written. Created if missing.
    version : Optional[int]
        The article version to fetch. If None, the latest available version
        is used.
    include : Optional[Iterable[str]]
        If given, only files whose lowercase extension matches one of these
        strings are downloaded (e.g. ``['xml', 'txt']``). Extensions should
        be given without the leading dot. If None, all files in the
        article's prefix are downloaded.

    Returns
    -------
    list of str
        Paths to the downloaded files. Empty if the article (or requested
        version) is not present on the bucket.
    """
    if version is None:
        version = get_latest_s3_version(pmcid)
        if version is None:
            return []
    keys = list_article_files_s3(pmcid, version=version)
    if include is not None:
        include = {ext.lower().lstrip('.') for ext in include}
        keys = [k for k in keys if k.rsplit('.', 1)[-1].lower() in include]
    article_dir = os.path.join(out_dir, f'{pmcid}.{version}')
    os.makedirs(article_dir, exist_ok=True)
    paths = []
    for key in keys:
        url = f'{pmc_s3_base_url}/{key}'
        filename = key.rsplit('/', 1)[-1]
        local_path = os.path.join(article_dir, filename)
        res = requests.get(url, stream=True)
        res.raise_for_status()
        with open(local_path, 'wb') as f:
            for chunk in res.iter_content(chunk_size=65536):
                f.write(chunk)
        paths.append(local_path)
    return paths


def id_lookup(paper_id, idtype=None):
    """Return PMID, DOI and PMCID based on an input ID.

    This function takes a Pubmed ID, Pubmed Central ID, or DOI
    and use the Pubmed ID mapping service and looks up all other IDs from one
    of these. The IDs are returned in a dictionary.

    Parameters
    ----------
    paper_id : str
        A PubMed ID, PubMed Central ID, or DOI.
    idtype : Optional[str]
        The type of the input ID. If not given, the function will try to
        determine the type from the input ID. If given, it must be one of
        'pmid', 'pmcid', or 'doi'.

    Returns
    -------
    dict
        A dictionary with keys 'pmid', 'pmcid', and 'doi' containing the
        corresponding IDs, or an empty dict if lookup fails.
    """
    if idtype is not None and idtype not in ('pmid', 'pmcid', 'doi'):
        raise ValueError("Invalid idtype %s; must be 'pmid', 'pmcid', "
                         "or 'doi'." % idtype)
    if paper_id.upper().startswith('PMC'):
        idtype = 'pmcid'
    # Strip off any prefix
    if paper_id.upper().startswith('PMID'):
        paper_id = paper_id[4:]
    elif paper_id.upper().startswith('DOI'):
        paper_id = paper_id[3:]
    data = {'ids': paper_id}
    if idtype is not None:
        data['idtype'] = idtype
    try:
        tree = pubmed_client.send_request(pmid_convert_url, data)
    except Exception as e:
        logger.error('Error looking up PMID in PMC: %s' % e)
        return {}
    if tree is None:
        return {}
    record = tree.find('record')
    if record is None:
        return {}
    doi = record.attrib.get('doi')
    pmid = record.attrib.get('pmid')
    pmcid = record.attrib.get('pmcid')
    ids = {'doi': doi,
           'pmid': pmid,
           'pmcid': pmcid}
    return ids


def get_ids(search_term, retmax=1000):
    return pubmed_client.get_ids(search_term, retmax=retmax, db='pmc')


def _run_pmc_xml_request(pmc_params: dict, max_retries: int = 4):
    # Run a request to the PMC OAI service, return the XML tree if successful,
    # and handle 429 errors. Per the documentation at
    # https://pmc.ncbi.nlm.nih.gov/tools/oai/, the endpoint only handles 3
    # requests per second. If a 429 error is sent back, the server typically
    # penalizes the client for a longer period of time than that limit, hence
    # the exponential backoff.
    max_sleep = 60.0
    attempt = 0
    res = requests.get(pmc_url, params=pmc_params)
    while res.status_code == 429 and attempt < max_retries:
        sleep_time = min(3**attempt, max_sleep)
        logger.warning(
            f"Got 429 from PMC OAI service, retrying in {sleep_time} seconds"
        )
        time.sleep(sleep_time)
        attempt += 1
        res = requests.get(pmc_url, params=pmc_params)

    return res


def get_xml(pmc_id: str, raise_for_status: bool = False, max_retries: int = 4):
    """Returns XML for the article corresponding to a PMC ID

    Parameters
    ----------
    pmc_id :
        A PubMed Central ID in 'PMC<digits>' form.
    raise_for_status :
        If True, raise an HTTPError if the request fails. If False, return
        None on failure.
    max_retries :
        Maximum number of retries to make if the request fails with a 429
        error.

    Returns
    -------
    : str | None
        The XML content as a unicode string, or None if the request fails
        and raise_on_status is False.

    Notes
    -----
    The endpoint this function relies on is aggressively rate limited and should
    only be used for single requests. To do bulk requesting, consider using the
    PMC Cloud S3 endpoints instead, which are not rate limited and with a more
    robust API.
    See https://pmc.ncbi.nlm.nih.gov/tools/oai/ for more information.

    See Also
    --------
    The following functions are available from the PMC client module to interact
    with the PMC Cloud Service hosted on AWS S3:
    - :func:`download_article_files_s3`
    - :func:`get_metadata_s3`
    - :func:`get_pdf_s3`
    - :func:`get_text_s3`
    - :func:`get_xml_s3`
    """
    if pmc_id.upper().startswith('PMC'):
        pmc_id = pmc_id[3:]
    # Request params
    params = {}
    params['verb'] = 'GetRecord'
    params['identifier'] = 'oai:pubmedcentral.nih.gov:%s' % pmc_id
    params['metadataPrefix'] = 'pmc'
    # Submit the request
    res = _run_pmc_xml_request(params, max_retries=max_retries)
    if raise_for_status:
        res.raise_for_status()
    if not res.status_code == 200:
        logger.warning(f"Couldn't download {pmc_id}. Got status {res.status_code}")
        return None
    # Read the bytestream
    xml_bytes = res.content
    # Check for any XML errors; xml_str should still be bytes
    tree = ET.XML(xml_bytes, parser=UTB())
    xmlns = "http://www.openarchives.org/OAI/2.0/"
    err_tag = tree.find('{%s}error' % xmlns)
    if err_tag is not None:
        err_code = err_tag.attrib['code']
        err_text = err_tag.text
        logger.warning('PMC client returned with error %s: %s'
                       % (err_code, err_text))
        return None
    # If no error, return the XML as a unicode string
    else:
        return xml_bytes.decode('utf-8')


def extract_text(xml_string):
    """Get plaintext from the body of the given NLM XML string.

    This plaintext consists of all paragraphs returned by
    indra.literature.pmc_client.extract_paragraphs separated
    by newlines and then finally terminated by a newline.
    See the DocString of extract_paragraphs for more information.

    Parameters
    ----------
    xml_string : str
        String containing valid NLM XML.

    Returns
    -------
    str
        Extracted plaintext.
    """
    paragraphs = extract_paragraphs(xml_string)
    if paragraphs:
        return '\n'.join(paragraphs) + '\n'
    else:
        return None


def extract_paragraphs(xml_string):
    """Returns list of paragraphs in an NLM XML.

    This returns a list of the plaintexts for each paragraph and title in
    the input XML, excluding some paragraphs with text that should not
    be relevant to biomedical text processing.

    Relevant text includes titles, abstracts, and the contents of many body
    paragraphs. Within figures, tables, and floating elements, only captions
    are retained (One exception is that all paragraphs within floating
    boxed-text elements are retained. These elements often contain short
    summaries enriched with useful information.) Due to captions, nested
    paragraphs can appear in an NLM XML document. Occasionally there are
    multiple levels of nesting. If nested paragraphs appear in the input
    document their texts are returned in a pre-ordered traversal. The text
    within child paragraphs is not included in the output associated to the
    parent. Each parent appears in the output before its children. All children
    of an element appear before the elements following sibling.

    All tags are removed from each paragraph in the list that is returned.
    LaTeX surrounded by <tex-math> tags is removed entirely.

    Note: Some articles contain subarticles which are processed slightly
    differently from the article body. Only text from the body element
    of a subarticle is included, and all unwanted elements are excluded
    along with their captions. Boxed-text elements are excluded as well.

    Parameters
    ----------
    xml_string : str
        String containing valid NLM XML.

    Returns
    -------
    list of str
        List of extracted paragraphs from the input NLM XML
    """
    output = []
    tree = etree.fromstring(xml_string.encode('utf-8'))
    # Remove namespaces if any exist
    if tree.tag.startswith('{'):
        for element in tree.getiterator():
            # The following code will throw a ValueError for some
            # exceptional tags such as comments and processing instructions.
            # It's safe to just leave these tag names unchanged.
            try:
                element.tag = etree.QName(element).localname
            except ValueError:
                continue
        etree.cleanup_namespaces(tree)

    if _is_pmc_ocr_xml(tree):
        return _extract_from_pmc_ocr(tree)

    # Strip out latex
    _remove_elements_by_tag(tree, 'tex-math')
    # Strip out all content in unwanted elements except the captions
    _replace_unwanted_elements_with_their_captions(tree)
    # First process front element. Titles alt-titles and abstracts
    # are pulled from here.
    front_elements = _select_from_top_level(tree, 'front')
    for element in front_elements:
        output.extend(_extract_from_front(element))
    # All paragraphs except those in unwanted elements are extracted
    # from the article body
    body_elements = _select_from_top_level(tree, 'body')
    for element in body_elements:
        output.extend(_extract_from_body(element))
    # Only the body sections of subarticles are processed. All
    # unwanted elements are removed entirely, including captions.
    # Even boxed-text elements are removed.
    subarticles = _select_from_top_level(tree, 'sub-article')
    for element in subarticles:
        output.extend(_extract_from_subarticle(element))
    return output


def filter_pmids(pmid_list, source_type):
    """Filter a list of PMIDs for ones with full text from PMC.

    Parameters
    ----------
    pmid_list : list of str
        List of PMIDs to filter.
    source_type : string
        One of 'fulltext', 'oa_xml', 'oa_txt', or 'auth_xml'.

    Returns
    -------
    list of str
        PMIDs available in the specified source/format type.
    """
    global pmids_fulltext_dict
    # Check args
    if source_type not in ('fulltext', 'oa_xml', 'oa_txt', 'auth_xml'):
        raise ValueError("source_type must be one of: 'fulltext', 'oa_xml', "
                         "'oa_txt', or 'auth_xml'.")
    # Check if we've loaded this type, and lazily initialize
    if pmids_fulltext_dict.get(source_type) is None:
        fulltext_list_path = os.path.join(os.path.dirname(__file__),
                                          'pmids_%s.txt' % source_type)
        with open(fulltext_list_path, 'rb') as f:
            fulltext_list = set([line.strip().decode('utf-8')
                                 for line in f.readlines()])
            pmids_fulltext_dict[source_type] = fulltext_list
    return list(set(pmid_list).intersection(
                                pmids_fulltext_dict.get(source_type)))



def _is_pmc_ocr_xml(tree):
    """Return True if this JATS XML contains PMC OCR text."""
    preformats = tree.findall(".//preformat")
    for pre in preformats:
        if pre.get("preformat-type") == "pmc-ocr-text":
            return True
    return False


def _extract_from_pmc_ocr(tree):
    """Extract PMC OCR text as a list of paragraphs."""
    paragraphs = []

    for pre in tree.findall(".//preformat"):
        if pre.get("preformat-type") != "pmc-ocr-text":
            continue

        text = "".join(pre.itertext())
        # Remove xml BOM and unify newline formats
        text = text.replace("\ufeff", "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        raw_paragraphs = re.split(r"\n\s*\n+", text)

        for para in raw_paragraphs:
            lines = [line.strip() for line in para.splitlines() if line.strip()]
            if lines:
                paragraphs.append(" ".join(lines))

    return paragraphs


def _select_from_top_level(tree, tag):
    """Select direct children of the article element of a tree by tag.

    Different versions of NLM XML place the article element in different
    places. We cannot rely on a hard coded path to the article element.  This
    helper function helps select top level elements beneath article from their
    tag name. We use this to pull out the front, body, and sub-article elements
    of an article.

    An assumption is made that there is only one article element in the input
    XML tree. If this is not the case, only the firt article will be
    processed.

    Parameters
    ----------
    tree : :py:class:`lxml.etree._Element`
        lxml element for entire tree of a valid NLM XML

    tag : str
        Tag of top level elements to return
    Returns
    -------
    list
        List containing lxml Element objects of selected top level elements.
        Typically there is only one front and one body that are direct chilren
        of the article element, but there can be multiple subarticles.
    """
    if tree.tag == 'article':
        article = tree
    else:
        article = tree.xpath('.//article')
        if not len(article):
            raise ValueError('Input XML contains no article element')
        # Assume there is only one article
        article = article[0]
    output = []
    xpath = './%s' % tag
    for element in article.xpath(xpath):
        output.append(element)
    return output


def _extract_from_front(front_element):
    """Return list of titles and paragraphs from front of NLM XML

    Parameters
    ----------
    front_element : :py:class:`lxml.etree._Element`
        etree element for front of a valid NLM XML
    Returns
    -------
    list of str
        List of relevant plain text titles and paragraphs taken from front
        section of NLM XML. These include the article title, alt title,
        and paragraphs within abstracts. Unwanted paragraphs such as
        author statements are excluded.
    """
    output = []
    title_xpath = './article-meta/title-group/article-title'
    alt_title_xpath = './article-meta/title-group/alt-title'
    abstracts_xpath = './article-meta/abstract'
    for element in front_element.xpath(_xpath_union(title_xpath,
                                                    alt_title_xpath,
                                                    abstracts_xpath)):
        if element.tag == 'abstract':
            # Extract paragraphs from abstracts
            output.extend(_extract_paragraphs_from_tree(element))
        else:
            # No paragraphs in titles, Just strip tags
            output.append(' '.join(element.itertext()))
    return output


def _extract_from_body(body_element):
    """Return list of paragraphs from main article body of NLM XML

    See DocString for extract_paragraphs for more info
    """
    return _extract_paragraphs_from_tree(body_element)


def _extract_from_subarticle(subarticle_element):
    """Return list of relevant paragraphs from a subarticle

    See DocString for extract_paragraphs for more info.
    """
    # Get only body element
    body = subarticle_element.xpath('./body')
    if not body:
        return []
    body = body[0]
    # Remove float elements. From observation these do not appear to
    # contain any meaningful information within sub-articles.
    for element in body.xpath(".//*[@position='float']"):
        element.getparent().remove(element)
    return _extract_paragraphs_from_tree(body)


def _remove_elements_by_tag(tree, *tags):
    """Remove elements with given tags

    Removes all element along with all of its content.
    Modifies input tree inplace

    Parameters
    ----------
    tree : :py:class:`lxml.etree._Element`
        etree element for valid NLM XML
    """
    bad_xpath = _xpath_union(*['.//%s' % tag for tag in tags])
    for element in tree.xpath(bad_xpath):
        element.getparent().remove(element)


def _replace_unwanted_elements_with_their_captions(tree):
    """Replace all unwanted elements with their captions

    Modifies input tree inplace.

    Parameters
    ----------
    tree : :py:class:`lxml.etree._Element`
        etree element for valid NLM XML
    """
    floats_xpath = "//*[@position='float']"
    figs_xpath = './/fig'
    tables_xpath = './/table-wrap'
    unwanted_xpath = _xpath_union(floats_xpath, figs_xpath, tables_xpath)
    unwanted = tree.xpath(unwanted_xpath)
    # Iterating through xpath nodes in reverse leads to processing these
    # nodes from bottom up.
    for element in unwanted[::-1]:
        # Don't remove floats that are boxed-text elements. These often contain
        # useful information
        if element.tag == 'boxed-text':
            continue
        captions = element.xpath('./caption')
        captions_element = etree.Element('captions')
        for caption in captions:
            captions_element.append(caption)
        element.getparent().replace(element, captions_element)


def _retain_only_pars(tree):
    """Strip out all tags except title and p tags

    Function also changes title tags into p tags. This is a helpful
    preprocessing step that makes it easier to extract paragraphs in
    the order of a pre-ordered traversal.

    Modifies input tree inplace.

    Parameters
    ----------
    tree : :py:class:`lxml.etree._Element`
        etree element for valid NLM XML
    """
    for element in tree.xpath('.//*'):
        if element.tag == 'title':
            element.tag = 'p'
    for element in tree.xpath('.//*'):
        parent = element.getparent()
        if parent is not None and element.tag != 'p':
            etree.strip_tags(element.getparent(), element.tag)


def _pull_nested_paragraphs_to_top(tree):
    """Flatten nested paragraphs in pre-ordered traversal

    Requires _retain_only_pars to be run first.

    Modifies input tree inplace.

    Parameters
    ----------
    tree : :py:class:`lxml.etree._Element`
        etree element for valid NLM XML
    """
    # Since _retain_only_pars must be called first, input will contain only p
    # tags except for possibly the outer most tag. p elements directly beneath
    # the root will be called depth 1, those beneath depth 1 elements will be
    # called depth 2 and so on.  Proceed iteratively. At each step identify all
    # p elements with depth 2.  Cut all of the depth 2 p elements out of each
    # parent and append them in order as siblings following the parent (these
    # depth 2 elements may themselves be the parents of additional p elements).
    # The algorithm terminates when there are no depth 2 elements remaining.
    # Find depth 2 p elements
    nested_paragraphs = tree.xpath('./p/p')
    while nested_paragraphs:
        # This points to the location where the next depth 2 p element will
        # be appended
        last = None
        # Store parent of previously processed element to track when parent
        # changes.
        old_parent = None
        for p in nested_paragraphs:
            parent = p.getparent()
            # When the parent changes last must be set to the new parent
            # element. This ensures children will be appended in order
            # after there parents.
            if parent != old_parent:
                last = parent
            # Remove child element from its parent
            parent.remove(p)
            # The parents text occuring after the current child p but before
            # p's following sibling is stored in p.tail. Append this text to
            # the parent's text and then clear out p.tail
            if not parent.text and p.tail:
                parent.text = p.tail
                p.tail = ''
            elif parent.text and p.tail:
                parent.text += ' ' + p.tail
                p.tail = ''
            # Place child in its new location
            last.addnext(p)
            last = p
        nested_paragraphs = tree.xpath('./p/p')


def _extract_paragraphs_from_tree(tree):
    """Preprocess tree and return it's paragraphs."""
    _retain_only_pars(tree)
    _pull_nested_paragraphs_to_top(tree)
    paragraphs = []
    for element in tree.xpath('./p'):
        paragraph = ''.join([x.strip() for x in element.itertext()])
        paragraphs.append(paragraph)
    return paragraphs


def _xpath_union(*xpath_list):
    """Form union of xpath expressions"""
    return ' | '.join(xpath_list)


def get_title(pmcid):
    xml_string = get_xml_s3(pmcid)
    if not xml_string:
        return
    tree = etree.fromstring(xml_string.encode('utf-8'))
    # Remove namespaces if any exist
    if tree.tag.startswith('{'):
        for element in tree.getiterator():
            # The following code will throw a ValueError for some
            # exceptional tags such as comments and processing instructions.
            # It's safe to just leave these tag names unchanged.
            try:
                element.tag = etree.QName(element).localname
            except ValueError:
                continue
        etree.cleanup_namespaces(tree)
    # Strip out latex
    _remove_elements_by_tag(tree, 'tex-math')
    # Strip out all content in unwanted elements except the captions
    _replace_unwanted_elements_with_their_captions(tree)
    # First process front element. Titles alt-titles and abstracts
    # are pulled from here.
    front_elements = _select_from_top_level(tree, 'front')
    title_xpath = './article-meta/title-group/article-title'
    for front_element in front_elements:
        for element in front_element.xpath(title_xpath):
            return ' '.join(element.itertext())
