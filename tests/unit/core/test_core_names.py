"""Name normalisation and resolution (loaders/names.py)."""
import pandas as pd
import pytest

from loaders.names import NameResolver, alias_rows, normalise


@pytest.mark.parametrize("raw, expected", [
    ("Kawanda S/S 132kV", "KAWANDA"),
    ("Kawanda Substation", "KAWANDA"),
    ("kawanda ss", "KAWANDA"),
    ("KAWANDA 220/132/33 kV", "KAWANDA"),
    ("Kampala-North", "KAMPALA NORTH"),
    ("Kampala Nth.", "KAMPALA NTH"),
    ("Mutundwe 33/11", "MUTUNDWE"),
    ("Mutundwe 132", "MUTUNDWE"),
    ("Namanve Power Station", "NAMANVE"),
    ("Bujagali PS", "BUJAGALI"),
    ("  queens   way ", "QUEENS WAY"),
    (None, ""),
])
def test_normalise(raw, expected):
    assert normalise(raw) == expected


def _resolver():
    subs = pd.DataFrame({"ss_code": ["KAW", "KNO", "QWY"], "name": ["Kawanda", "Kampala North", "Queensway"]})
    plants = pd.DataFrame({"plant_code": ["NMVT"], "name": ["Namanve thermal"]})
    aliases = pd.DataFrame({"alias": ["Kampala Nth", "Queens Way", "Namanve"], "entity_type": ["substation", "substation", "plant"],
                            "canonical_id": ["KNO", "QWY", "NMVT"], "source": ["t", "t", "t"]})
    return NameResolver.from_frames(alias_rows(aliases, subs, plants), subs, plants)


def test_resolve_by_name_alias_and_code():
    r = _resolver()
    assert r.resolve("Kawanda S/S", "substation").code == "KAW"
    assert r.resolve("KAW", "substation").code == "KAW"
    assert r.resolve("Kampala Nth", "substation").code == "KNO"
    assert r.resolve("Queens Way 132kV", "substation").code == "QWY"
    assert r.resolve("Namanve", "plant").code == "NMVT"
    # entity types are kept apart
    assert r.resolve("Namanve", "substation").code is None


def test_unresolved_gives_suggestion_but_no_code():
    r = _resolver()
    found = r.resolve("Kawandaa", "substation")
    assert found.code is None
    assert found.suggestion and found.suggestion.startswith("KAW")
    nothing = r.resolve("Totally Elsewhere", "substation")
    assert nothing.code is None and nothing.suggestion is None


def test_alias_conflict_is_refused():
    subs = pd.DataFrame({"ss_code": ["KAW", "MUT"], "name": ["Kawanda", "Mutundwe"]})
    plants = pd.DataFrame({"plant_code": [], "name": []})
    aliases = pd.DataFrame({"alias": ["Kawanda S/S"], "entity_type": ["substation"], "canonical_id": ["MUT"], "source": ["x"]})
    with pytest.raises(ValueError, match="maps to both"):
        alias_rows(aliases, subs, plants)


def test_config_aliases_are_consistent():
    """The shipped config files build an alias table without conflicts or unknown codes."""
    from engine.config import CONFIG_DIR
    read = lambda n: pd.read_csv(CONFIG_DIR / n, dtype=str, keep_default_na=False)
    subs, plants, aliases = read("substations.csv"), read("plants.csv"), read("aliases.csv")
    table = alias_rows(aliases, subs, plants)
    assert set(table.loc[table.entity_type == "substation", "canonical_id"]) <= set(subs.ss_code)
    assert set(table.loc[table.entity_type == "plant", "canonical_id"]) <= set(plants.plant_code)
    assert len(subs) == 15 and subs.ss_code.str.fullmatch(r"[A-Z]{3}").all()
    assert set(subs.loc[subs.in_central == "false", "ss_code"]) == {"BUJ", "NAL", "MBR", "KAR"}
