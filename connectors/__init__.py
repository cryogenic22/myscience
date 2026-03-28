"""
Connector registry for Market-Zero.

To add a new data source:
1. Create a connector class in this package that extends BaseConnector.
2. Add it to CONNECTOR_REGISTRY below.
3. Done. The integration pipeline picks it up automatically.
"""

from connectors.base import BaseConnector, SourceType
from connectors.mesh import MeSHConnector
from connectors.orange_book import OrangeBookConnector
from connectors.clinical_trials import ClinicalTrialsConnector
from connectors.fda_shortages import FDAShortagesConnector
from connectors.pubmed import PubMedConnector
from connectors.sec_edgar import SECEdgarConnector
from connectors.openfda_faers import OpenFDAFAERSConnector
from connectors.openfda_labels import OpenFDALabelsConnector
from connectors.pmc import PMCConnector
from connectors.ema import EMAConnector
from connectors.nadac import NadacConnector
from connectors.news import PharmaNewsConnector
from connectors.chembl import ChEMBLConnector
from connectors.pubchem import PubChemConnector
from connectors.open_targets import OpenTargetsConnector

# Registry is populated as connectors are implemented.
CONNECTOR_REGISTRY: dict[SourceType, type[BaseConnector]] = {
    SourceType.MESH_ONTOLOGY: MeSHConnector,
    SourceType.FDA_ORANGE_BOOK: OrangeBookConnector,
    SourceType.CLINICAL_TRIALS_GOV: ClinicalTrialsConnector,
    SourceType.FDA_SHORTAGES: FDAShortagesConnector,
    SourceType.PUBMED: PubMedConnector,
    SourceType.SEC_EDGAR: SECEdgarConnector,
    SourceType.OPENFDA_FAERS: OpenFDAFAERSConnector,
    SourceType.OPENFDA_LABELS: OpenFDALabelsConnector,
    SourceType.PMC: PMCConnector,
    SourceType.EMA: EMAConnector,
    SourceType.NADAC: NadacConnector,
    SourceType.NEWS: PharmaNewsConnector,
    SourceType.CHEMBL: ChEMBLConnector,
    SourceType.PUBCHEM: PubChemConnector,
    SourceType.OPEN_TARGETS: OpenTargetsConnector,
    # SourceType.USER_DOCUMENT: UserDocumentConnector,   # Phase 7
    # SourceType.USER_URL: UserURLConnector,             # Phase 7
}


def get_connector(source_type: SourceType, **kwargs) -> BaseConnector:
    """Instantiate a connector by its SourceType."""
    cls = CONNECTOR_REGISTRY.get(source_type)
    if cls is None:
        raise ValueError(
            f"No connector registered for {source_type.value}. "
            f"Available: {[s.value for s in CONNECTOR_REGISTRY.keys()]}"
        )
    return cls(**kwargs)
