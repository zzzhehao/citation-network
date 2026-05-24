import json
import math
import os
from typing import List, Dict, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class NetworkVisualizer:
    def __init__(
        self,
        publications: Dict,
        edges: List[Tuple[str, str]],
        seed_origins: Dict = None,
        stats: Dict = None,
    ):
        self.publications = publications
        self.edges = edges
        self.seed_origins = seed_origins or {}
        self.stats = stats or {}  # [NEW] Accept stats dictionary

        self.connectedness = {doi: 0 for doi in self.publications}
        for source, target in self.edges:
            if source in self.connectedness:
                self.connectedness[source] += 1
            if target in self.connectedness:
                self.connectedness[target] += 1

    def generate_html(self, output_path: str = "network.html") -> None:
        nodes = self._prepare_nodes()
        links = self._prepare_links()

        template_path = Path(__file__).parent / "templates" / "template.html"
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            html_content = html_content.replace("__NODES_JSON__", nodes)
            html_content = html_content.replace("__LINKS_JSON__", links)

            # [NEW] Inject Stats JSON
            html_content = html_content.replace(
                "__STATS_JSON__", json.dumps(self.stats)
            )

        except FileNotFoundError:
            logger.error(f"Template not found at {template_path}")
            raise

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info(f"HTML visualization saved to {output_path}")

    def _prepare_nodes(self) -> str:
        # [CHANGE 2] Filter nodes based on network filter threshold
        initial_core_count = sum(
            1 for origin in self.seed_origins.values() if origin == "initial"
        )
        # Calculate sum of secondary core importance scores
        secondary_core_scores = [
            pub.importance_score
            for doi, pub in self.publications.items()
            if doi in self.seed_origins and self.seed_origins[doi] != "initial"
        ]
        secondary_core_count = len(secondary_core_scores)
        secondary_core_mean = (
            sum(secondary_core_scores) / secondary_core_count
            if secondary_core_count > 0
            else 0.0
        )
        network_filter = self.stats.get("Network Filter Parameter", 0.2)
        req_min = (initial_core_count + secondary_core_mean) * network_filter

        # [DEBUG] Log filtering info
        # print(f"\n=== VISUALIZER FILTERING ===")
        # print(f"Initial cores: {initial_core_count}")
        # print(f"Secondary cores count: {secondary_core_count}")
        # print(f"Secondary core mean score: {secondary_core_mean:.2f}")
        # print(f"Network filter parameter: {network_filter}")
        # print(f"\nPublications to filter: {len(self.publications)}")

        # Only include core papers or peripherals that meet the threshold
        filtered_publications = {}
        included_peripherals = 0
        excluded_peripherals = 0
        for doi, pub in self.publications.items():
            if doi in self.seed_origins:
                # Include all core papers
                filtered_publications[doi] = pub
            elif pub.importance_score >= req_min:
                # Include peripherals that meet the threshold
                filtered_publications[doi] = pub
                included_peripherals += 1
            else:
                excluded_peripherals += 1

        # print(f"\nFiltering results:")
        # print(
        #     f"  Core papers: {sum(1 for doi in filtered_publications if doi in self.seed_origins)}"
        # )
        # print(f"  Peripherals included: {included_peripherals}")
        # print(f"  Peripherals excluded: {excluded_peripherals}")
        # print(f"  Total in network: {len(filtered_publications)}")
        # print(f"=========================\n")

        # Store filtered publications for use in _prepare_links
        self.filtered_publications = filtered_publications

        nodes = []
        year_range = [pub.year for pub in filtered_publications.values()]
        min_year = min(year_range) if year_range else 2000
        max_year = max(year_range) if year_range else 2024

        periph_scores = [
            pub.importance_score
            for doi, pub in filtered_publications.items()
            if doi not in self.seed_origins
        ]
        max_periph_imp = max(periph_scores) if periph_scores else 1.0
        min_periph_imp = min(periph_scores) if periph_scores else 0.0
        score_range = max_periph_imp - min_periph_imp

        for doi, pub in filtered_publications.items():
            year_val = (
                (pub.year - min_year) / (max_year - min_year + 1)
                if max_year > min_year
                else 0.5
            )

            if score_range > 0:
                imp_val = (pub.importance_score - min_periph_imp) / score_range
            else:
                imp_val = 0.5

            calc_size = math.log10(pub.citation_count + 1) * 2 + 10
            node_size = max(10, min(15, calc_size))
            is_secondary = (
                doi in self.seed_origins and self.seed_origins[doi] != "initial"
            )

            nodes.append(
                {
                    "id": doi,
                    "title": pub.title[:50] + "..."
                    if len(pub.title) > 50
                    else pub.title,
                    "size": node_size,
                    "citations": pub.citation_count,
                    "importance": pub.importance_score,
                    "imp_color_val": imp_val,
                    "year_color_val": year_val,
                    "year": pub.year,
                    "authors": pub.authors[:2],
                    "journal": pub.journal,
                    "fullTitle": pub.title,
                    "is_secondary": is_secondary,
                    "is_core": doi in self.seed_origins,
                }
            )
        return json.dumps(nodes)

    def _prepare_links(self) -> str:
        links = []
        for source, target in self.edges:
            if (
                source in self.filtered_publications
                and target in self.filtered_publications
            ):
                weight = (self.connectedness[source] + self.connectedness[target]) / 2.0
                links.append({"source": source, "target": target, "weight": weight})
        return json.dumps(links)
