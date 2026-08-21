"""Opportunity Radar — a self-healing pipeline for opportunity listings.

Built for the WeMakeDevs "Into the Scrape-Verse" hackathon on top of
Bright Data Scraper Studio. The pipeline runs custom Scraper Studio
collectors, validates every run against a schema and health thresholds,
and — when a target site changes under the scraper — automatically
invokes `brightdata scraper heal` to repair it, then retries.
"""

__version__ = "0.1.0"
