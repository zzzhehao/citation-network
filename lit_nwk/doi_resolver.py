import requests
import time
import re
import html
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Safely remove HTML tags and decode HTML entities from API responses."""
    if not text or not isinstance(text, str):
        return "Unknown"

    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return " ".join(text.split())


@dataclass
class NetworkConfig:
    min_year: int = 2000
    min_cocitation_upstream: float = 1.0
    min_cocitation_downstream: float = 1.0
    max_results_per_query: int = 50
    recursive_expansion_threshold: float = 0.25
    max_iterations: int = 3
    run_name: str = "network_run"
    peripheral_vote: float = 0.5
    penalty_factor: float = 0.5
    core_award: float = 0.5  # [NEW] Multiplier for core inheritance
    errors: List[str] = field(default_factory=list)
    max_iterations: int = 5
    peripheral_vote: float = 0.25
    network_filter: float = 0.5


@dataclass
class Publication:
    doi: str
    title: str
    authors: List[str]
    year: int
    journal: str
    citation_count: int
    importance_score: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "doi": self.doi,
            "title": self.title,
            "authors": ", ".join(self.authors[:3])
            + ("..." if len(self.authors) > 3 else ""),
            "year": self.year,
            "journal": self.journal,
            "citation_count": self.citation_count,
            "importance_score": round(self.importance_score, 4),
        }


class MetadataRetriever:
    def __init__(self, config: NetworkConfig):
        self.config = config
        self.crossref_url = "https://api.crossref.org/works"
        self.headers = {"User-Agent": "LitReview/1.0"}

    def get_metadata(self, doi: str) -> Optional[Publication]:
        try:
            response = requests.get(
                f"{self.crossref_url}/{doi}", headers=self.headers, timeout=10
            )
            response.raise_for_status()
            data = response.json()["message"]

            title_raw = data.get("title", [""])[0] if data.get("title") else "Unknown"
            journal_raw = (
                data.get("container-title", ["Unknown"])[0]
                if data.get("container-title")
                else "Unknown"
            )

            return Publication(
                doi=doi,
                title=clean_text(title_raw),
                authors=[
                    f"{author.get('family', '')} {author.get('given', '')}".strip()
                    for author in data.get("author", [])
                ],
                year=data.get("issued", {}).get("date-parts", [[2000]])[0][0],
                journal=clean_text(journal_raw),
                citation_count=data.get("is-referenced-by-count", 0),
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                self.config.errors.append(f"[CrossRef 404] DOI not found: {doi}")
            else:
                self.config.errors.append(f"[CrossRef HTTP Error] {doi}: {e}")
            return None
        except Exception as e:
            self.config.errors.append(f"[CrossRef Fetch Error] {doi}: {e}")
            return None


class CitationNetworkBuilder:
    def __init__(self, config: NetworkConfig):
        self.config = config
        self.retriever = MetadataRetriever(config)

    def get_upstream_papers(self, doi: str) -> Dict[str, Publication]:
        try:
            response = requests.get(f"https://api.crossref.org/works/{doi}", timeout=10)
            response.raise_for_status()
            data = response.json()["message"]

            upstream = {}
            references = data.get("reference", [])[: self.config.max_results_per_query]

            for ref in references:
                ref_doi = ref.get("DOI")
                if ref_doi:
                    pub = self.retriever.get_metadata(ref_doi)
                    if pub and pub.year >= self.config.min_year:
                        upstream[ref_doi] = pub
            return upstream
        except requests.exceptions.HTTPError as e:
            if e.response.status_code != 404:
                self.config.errors.append(f"[CrossRef Upstream Error] {doi}: {e}")
            return {}
        except Exception as e:
            self.config.errors.append(f"[CrossRef Upstream Error] {doi}: {e}")
            return {}

    def get_downstream_papers(self, doi: str) -> Dict[str, Publication]:
        try:
            time.sleep(0.1)
            url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}/citations"
            params = {
                "fields": "title,authors,year,venue,citationCount,externalIds",
                "limit": self.config.max_results_per_query,
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 404:
                self.config.errors.append(
                    f"[SemScholar 404] No downstream data for DOI: {doi}"
                )
                return {}

            response.raise_for_status()
            data = response.json().get("data", [])

            downstream = {}
            for item in data:
                citing_paper = item.get("citingPaper")
                if not citing_paper:
                    continue

                ids = citing_paper.get("externalIds", {})
                ref_doi = ids.get("DOI")
                year = citing_paper.get("year")

                if ref_doi and year and year >= self.config.min_year:
                    authors = [
                        a.get("name", "")
                        for a in citing_paper.get("authors", [])
                        if a.get("name")
                    ]

                    title_raw = citing_paper.get("title", "Unknown") or "Unknown"
                    journal_raw = citing_paper.get("venue", "Unknown") or "Unknown"

                    pub = Publication(
                        doi=ref_doi,
                        title=clean_text(title_raw),
                        authors=authors,
                        year=year,
                        journal=clean_text(journal_raw),
                        citation_count=citing_paper.get("citationCount", 0) or 0,
                    )
                    downstream[ref_doi] = pub
            return downstream
        except Exception as e:
            self.config.errors.append(f"[SemScholar Downstream Error] {doi}: {e}")
            return {}
