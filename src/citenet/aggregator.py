import csv
import json
from typing import List, Dict, Tuple
import logging
from tqdm import tqdm
from .doi_resolver import MetadataRetriever

logger = logging.getLogger(__name__)


class NetworkAggregator:
    def __init__(self, config):
        self.config = config

    def build_network_recursive(
        self, seed_dois: List[str], builder
    ) -> Tuple[Dict, List[Tuple[str, str]], Dict, Dict]:
        all_edges_set = set()
        global_scraped = {}

        current_seeds = set(seed_dois)
        seed_origins = {doi: "initial" for doi in seed_dois}

        retriever = MetadataRetriever(self.config)

        for doi in tqdm(current_seeds, desc="Fetching seed metadata", unit="paper"):
            pub = retriever.get_metadata(doi)
            if pub:
                global_scraped[doi] = pub

        # --- RECURSIVE EXPANSION PHASE ---
        for iteration in range(self.config.max_iterations):
            current_core_count = len(seed_origins)

            # Asymptotic Logarithmic Curve
            initial_pct = self.config.recursive_expansion_threshold
            current_pct = 1.0 - (1.0 - initial_pct) * (
                self.config.penalty_factor**iteration
            )

            threshold = max(2.0, float(current_core_count * current_pct))

            logger.info(
                f"\n--- Iteration {iteration + 1} (Core count: {current_core_count}, Promotability Pct: {current_pct * 100:.1f}%, Upgrade Score Required: >={threshold:.2f}) ---"
            )

            # [NEW] Print the absolute threshold directly to the console above the progress bar
            tqdm.write(
                f"\n🔄 Iteration {iteration + 1} | Core Count: {current_core_count} | Promotability Curve: {current_pct * 100:.1f}% | Absolute Upgrade Score: >= {threshold:.2f}"
            )

            if not current_seeds:
                break

            for doi in tqdm(
                current_seeds,
                desc=f"Iter {iteration + 1}: Fetching connections",
                unit="paper",
            ):
                upstream = builder.get_upstream_papers(doi)
                downstream = builder.get_downstream_papers(doi)

                global_scraped.update(upstream)
                global_scraped.update(downstream)

                for ref_doi in upstream:
                    all_edges_set.add((doi, ref_doi))
                for citing_doi in downstream:
                    all_edges_set.add((citing_doi, doi))

            # --- Start of New Scoring Logic ---

            # Define core and peripheral papers for this iteration
            core_papers = set(seed_origins.keys())
            peripheral_papers = {
                doi for doi in global_scraped.keys() if doi not in core_papers
            }

            # 1. Calculate scores for core papers
            core_scores = {doi: 0.0 for doi in core_papers}
            for source, target in all_edges_set:
                if source in core_scores:
                    core_scores[source] += (
                        1.0 if target in core_papers else self.config.peripheral_vote
                    )
                if target in core_scores:
                    core_scores[target] += (
                        1.0 if source in core_papers else self.config.peripheral_vote
                    )

            # 2. Get max secondary core score for seed paper calculations
            max_secondary_core_score = 0
            for doi, score in core_scores.items():
                if seed_origins[doi] != "initial":
                    max_secondary_core_score = max(max_secondary_core_score, score)

            # 3. Calculate scores for peripheral papers (candidates)
            candidate_scores = {doi: 0.0 for doi in peripheral_papers}

            # Base score for peripherals
            for source, target in all_edges_set:
                if source in candidate_scores:
                    candidate_scores[source] += (
                        1.0 if target in core_papers else self.config.peripheral_vote
                    )
                if target in candidate_scores:
                    candidate_scores[target] += (
                        1.0 if source in core_papers else self.config.peripheral_vote
                    )

            # Add core award bonus to peripherals
            for doi in candidate_scores:
                paper_connections = set()
                for source, target in all_edges_set:
                    if source == doi:
                        paper_connections.add(target)
                    if target == doi:
                        paper_connections.add(source)

                connected_cores = paper_connections & core_papers
                for core_doi in connected_cores:
                    if seed_origins[core_doi] == "initial":
                        candidate_scores[doi] += (
                            self.config.core_award * max_secondary_core_score
                        )
                    else:
                        candidate_scores[doi] += (
                            self.config.core_award * core_scores.get(core_doi, 0.0)
                        )

            secondary_candidates = {}
            for doi, score in candidate_scores.items():
                if score >= threshold:
                    secondary_candidates[doi] = score

            if not secondary_candidates:
                break

            # [SAFEGUARD] Check if too many new cores identified in this iteration
            new_core_count = len(secondary_candidates)
            if new_core_count > 20:
                tqdm.write(
                    f"\n⚠️  WARNING: {new_core_count} new secondary cores identified in this iteration!"
                )
                tqdm.write(
                    "This is a lot of new cores. There might be even more in the next iterations. Proceeding will take very long time, and might get you API banned. Please consider adjusting your configuration parameters (e.g., increase recursive-threshold, decrease penalty-factor, or reduce core-award) to control the growth of the network."
                )
                tqdm.write("\nProceed at your own risk.\n")

                user_input = (
                    input("❓ Continue? (type `yes` or `y` to continue): ")
                    .strip()
                    .lower()
                )
                if user_input not in ["yes", "y"]:
                    logger.info(
                        "User aborted network expansion due to excessive secondary cores."
                    )
                    tqdm.write("\n🛑 Network expansion aborted by user.\n")
                    break

            # [CHANGE 1] Only promote new cores if not the last iteration
            if iteration < self.config.max_iterations - 1:
                current_seeds = set(secondary_candidates.keys())
                for doi in current_seeds:
                    seed_origins[doi] = f"secondary_iter{iteration + 1}"
            else:
                logger.info("Last iteration reached. No new cores promoted.")
                tqdm.write("\\n⚠️  Last iteration reached. No new cores promoted.\\n")
                break

        # --- FINAL PRUNING & SCORING PHASE ---
        # Calculate final scores with new importance calculation
        core_papers = set(seed_origins.keys())
        final_scores = {doi: 0.0 for doi in global_scraped.keys()}

        # Calculate scores for core papers
        core_scores = {doi: 0.0 for doi in core_papers}
        for source, target in all_edges_set:
            if source in core_scores:
                core_scores[source] += (
                    1.0 if target in core_papers else self.config.peripheral_vote
                )
            if target in core_scores:
                core_scores[target] += (
                    1.0 if source in core_papers else self.config.peripheral_vote
                )

        # Get max secondary core score
        max_secondary_core_score = 0
        for doi, score in core_scores.items():
            if seed_origins[doi] != "initial":
                max_secondary_core_score = max(max_secondary_core_score, score)

        # Calculate final scores for all papers
        peripheral_papers = {
            doi for doi in global_scraped.keys() if doi not in core_papers
        }

        # Base scores for all papers
        for source, target in all_edges_set:
            final_scores[source] += (
                1.0 if target in core_papers else self.config.peripheral_vote
            )
            final_scores[target] += (
                1.0 if source in core_papers else self.config.peripheral_vote
            )

        # Add core award bonus to peripheral papers
        for doi in peripheral_papers:
            paper_connections = set()
            for source, target in all_edges_set:
                if source == doi:
                    paper_connections.add(target)
                if target == doi:
                    paper_connections.add(source)

            connected_cores = paper_connections & core_papers
            for core_doi in connected_cores:
                if seed_origins[core_doi] == "initial":
                    final_scores[doi] += (
                        self.config.core_award * max_secondary_core_score
                    )
                else:
                    final_scores[doi] += self.config.core_award * core_scores.get(
                        core_doi, 0.0
                    )

        # [CHANGE 2] Calculate new threshold based on initial cores + network_filter * mean of secondary cores
        initial_core_count = sum(
            1 for origin in seed_origins.values() if origin == "initial"
        )
        secondary_core_scores = [
            core_scores.get(doi, 0.0)
            for doi, origin in seed_origins.items()
            if origin != "initial"
        ]
        secondary_core_count = len(secondary_core_scores)
        secondary_core_mean = (
            sum(secondary_core_scores) / secondary_core_count
            if secondary_core_count > 0
            else 0.0
        )

        req_min = (
            initial_core_count + secondary_core_mean
        ) * self.config.network_filter

        final_core_count = len(seed_origins)

        logger.info(f"\n--- Finalizing Network ---")
        logger.info(f"Final Core Size: {final_core_count} papers")
        logger.info(f"Initial Cores: {initial_core_count}")
        logger.info(f"Secondary Cores Count: {secondary_core_count}")
        logger.info(f"Secondary Cores Mean Score: {secondary_core_mean:.2f}")
        logger.info(f"Network Filter Parameter: {self.config.network_filter}")
        logger.info(f"Peripheral Visibility Threshold: {req_min:.2f}")
        logger.info(f"Peripheral Visibility Threshold: >={req_min:.2f} score")

        # [DEBUG] Print core scores
        logger.info(f"\n--- Core Paper Scores ---")
        for doi, origin in seed_origins.items():
            score = core_scores.get(doi, 0.0)
            logger.info(f"  {doi[:20]}... ({origin}): {score:.2f}")

        # [NEW] Print the final pruning threshold to the console
        tqdm.write(
            f"\n✅ Finalizing Network | Final Core Size: {final_core_count} | Peripheral Visibility Score: >= {req_min:.2f}\n"
        )

        final_publications = {}
        peripheral_count = 0
        for doi, pub in global_scraped.items():
            if doi in seed_origins:
                final_publications[doi] = pub
            elif final_scores.get(doi, 0.0) >= req_min:
                final_publications[doi] = pub
                peripheral_count += 1
                # [DEBUG] Log each peripheral that makes the cut
                logger.debug(
                    f"  ✓ Peripheral included: {{doi[:20]}}... (score: {{final_scores.get(doi, 0.0):.2f}}) >= {{req_min:.2f}}"
                )
            else:
                # [DEBUG] Log peripherals that don't make the cut (sample first 5)
                if peripheral_count < 5:
                    logger.debug(
                        f"  ✗ Peripheral excluded: {{doi[:20]}}... (score: {{final_scores.get(doi, 0.0):.2f}}) < {{req_min:.2f}}"
                    )

        logger.info(f"\n--- Final Network Composition ---")
        logger.info(f"Total papers in final network: {{len(final_publications)}}")
        logger.info(f"  Core papers: {{final_core_count}}")
        logger.info(
            f"  Peripheral papers included: {{len(final_publications) - final_core_count}}"
        )
        logger.info(
            f"  Peripheral papers excluded: {{len(global_scraped) - len(final_publications)}}"
        )

        final_edges_set = set()
        for source, target in all_edges_set:
            if source in final_publications and target in final_publications:
                final_edges_set.add((source, target))

        for doi, pub in global_scraped.items():
            if doi in seed_origins and seed_origins[doi] == "initial":
                pub.importance_score = 999.0
            else:
                pub.importance_score = float(max(1.0, final_scores.get(doi, 0.0)))

        return final_publications, list(final_edges_set), global_scraped, seed_origins


class DataExporter:
    @staticmethod
    def to_csv(publications: Dict, output_path: str, seed_origins: Dict = None) -> None:
        seed_origins = seed_origins or {}
        sorted_pubs = sorted(
            publications.values(), key=lambda pub: pub.importance_score, reverse=True
        )

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "doi",
                    "title",
                    "authors",
                    "year",
                    "journal",
                    "citation_count",
                    "importance_score",
                    "role",
                ],
            )
            writer.writeheader()
            for pub in sorted_pubs:
                row = pub.to_dict()
                if pub.doi in seed_origins:
                    row["role"] = (
                        "Core (Initial Seed)"
                        if seed_origins[pub.doi] == "initial"
                        else "Core (Secondary)"
                    )
                else:
                    row["role"] = "Peripheral"
                writer.writerow(row)
        logger.info(f"Exported {len(publications)} publications to {output_path}")

    @staticmethod
    def to_json(
        publications: Dict, edges: List[Tuple[str, str]], output_path: str
    ) -> None:
        data = {
            "nodes": [pub.to_dict() for pub in publications.values()],
            "links": [{"source": s, "target": t} for s, t in edges],
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
