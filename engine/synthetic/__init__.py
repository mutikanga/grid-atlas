"""Synthetic Central network and inputs (owner: F5).

Everything here is fake. It exists so the whole Grid Atlas pipeline can run end to
end before UETCL's real data arrives. Every file it writes is labelled SYNTHETIC,
and the planted outcomes the engine must reproduce are written to
``data/synthetic/truth.json`` for the golden tests.

Entry point: ``engine.synthetic.generate.main(argv)``, called by
``python -m engine.cli synth --variant base|line_bound|dirty --seed 42``.
"""
