"""D1: PMC efetch parse regression — accept NCBI's current article-id types.

Root cause of the empty `pmc_articles` table (0 rows despite a daily schedule
and hundreds of SUCCESS runs): the parser matched only
``<article-id pub-id-type="pmc">``, but NCBI's PMC efetch XML now tags the PMC
id as ``pmcid`` (e.g. ``PMC13236199``) / ``pmcaid`` (numeric). Every fetched
article was silently dropped.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from connectors.pmc import PMCConnector

# Current NCBI shape: pmcid + pmcaid, no plain "pmc"
CURRENT_XML = """<pmc-articleset>
  <article article-type="research-article">
    <front><article-meta>
      <article-id pub-id-type="pmcid">PMC13236199</article-id>
      <article-id pub-id-type="pmcaid">13236199</article-id>
      <article-id pub-id-type="doi">10.1/x</article-id>
    </article-meta></front>
  </article>
</pmc-articleset>"""

# Legacy shape: plain "pmc" numeric
LEGACY_XML = """<pmc-articleset>
  <article><front><article-meta>
      <article-id pub-id-type="pmc">9999999</article-id>
  </article-meta></front></article>
</pmc-articleset>"""

NO_PMC_XML = """<pmc-articleset>
  <article><front><article-meta>
      <article-id pub-id-type="doi">10.1/y</article-id>
  </article-meta></front></article>
</pmc-articleset>"""


def _first_article(xml: str) -> ET.Element:
    return ET.fromstring(xml).find(".//article")


def test_extracts_current_pmcid_type():
    pid = PMCConnector._extract_pmc_id(_first_article(CURRENT_XML))
    assert pid == "PMC13236199"


def test_extracts_legacy_pmc_type():
    pid = PMCConnector._extract_pmc_id(_first_article(LEGACY_XML))
    assert pid == "9999999"


def test_returns_none_when_no_pmc_id():
    assert PMCConnector._extract_pmc_id(_first_article(NO_PMC_XML)) is None


def test_fetch_pmc_articles_finds_current_shape(monkeypatch):
    """The full _fetch_pmc_articles path yields the article with a PMC-prefixed id."""
    c = PMCConnector()

    class _Resp:
        status_code = 200
        content = CURRENT_XML.encode()

    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp())
    out = c._fetch_pmc_articles(["13236199"])
    assert len(out) == 1
    assert out[0][0] == "PMC13236199"
