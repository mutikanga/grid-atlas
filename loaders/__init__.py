"""Spec-driven loaders: read delivered files, validate every row against
templates/spec/*.toml, log problems in meta.import_issue, and write good rows to ts.*.

  manifest.py  read and check data/<root>/<dataset>/manifest.toml
  spec.py      the template specs as typed objects
  units.py     turn cell values into dates, numbers, Y/N and so on
  names.py     map substation and plant names to canonical codes
  vector.py    read GIS layers and reproject them to WGS 84
  generic.py   load one dataset folder (and the config registers into ref.*)
"""
