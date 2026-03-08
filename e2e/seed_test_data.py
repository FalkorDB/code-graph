#!/usr/bin/env python3
"""Seed FalkorDB with test data for Playwright e2e tests."""

import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from api.project import Project

REPOS = [
    "https://github.com/FalkorDB/GraphRAG-SDK",
    "https://github.com/pallets/flask",
]


def main():
    for url in REPOS:
        logger.info("Seeding %s ...", url)
        proj = Project.from_git_repository(url)
        proj.analyze_sources()
        logger.info("Done seeding %s", url)

    logger.info("All test data seeded successfully.")


if __name__ == "__main__":
    main()
