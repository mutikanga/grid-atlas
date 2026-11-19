"""Grid Atlas engine: database access, the run framework and the analysis stages.

Entry point: `python -m engine.cli <command>` (see engine/cli.py).
Numeric code is pure (DataFrames and pandapower nets in, DataFrames out); database
reads and writes stay in engine/stages/*.py through the RunContext (engine/context.py).
"""
