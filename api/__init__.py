"""Grid Atlas read-only API.

The API serves only the `api.*` views of the database, through the `atlas_ro` role.
It never writes. Every response carries the provenance of the current run, so a
synthetic or approximate number can never leave the Atlas without its label.
"""
