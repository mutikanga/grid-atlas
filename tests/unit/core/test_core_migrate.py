"""Migration ordering and change rules (engine/migrate.py plan_migrations)."""
import pytest

from engine.migrate import MigrationError, MigrationFile, discover, kind_of, plan_migrations


def mf(name, sha="a"):
    return MigrationFile(name, int(name[:3]), sha)


FILES = [mf("900_api_core.sql"), mf("001_meta.sql"), mf("100_ts_generated.sql"), mf("210_results_losses.sql"),
         mf("002_ref.sql"), mf("910_api_losses.sql")]


def actions(steps):
    return [(s.action, s.name) for s in steps]


def test_kinds():
    assert kind_of(1) == "once" and kind_of(99) == "once"
    assert kind_of(100) == "rebuild" and kind_of(199) == "rebuild"
    assert kind_of(210) == "once" and kind_of(899) == "once"
    assert kind_of(900) == "view" and kind_of(999) == "view"


def test_fresh_database_applies_all_in_order_views_last():
    steps = plan_migrations(FILES, {})
    assert actions(steps) == [("apply", "001_meta.sql"), ("apply", "002_ref.sql"), ("apply", "100_ts_generated.sql"),
                              ("apply", "210_results_losses.sql"), ("apply", "900_api_core.sql"), ("apply", "910_api_losses.sql")]


def test_second_run_only_reapplies_views():
    applied = {f.name: f.sha256 for f in FILES}
    steps = plan_migrations(FILES, applied)
    assert [n for a, n in actions(steps) if a == "apply"] == ["900_api_core.sql", "910_api_losses.sql"]


def test_changed_once_file_is_an_error():
    applied = {f.name: f.sha256 for f in FILES}
    changed = [mf("001_meta.sql", "b") if f.name == "001_meta.sql" else f for f in FILES]
    with pytest.raises(MigrationError, match="001_meta.sql"):
        plan_migrations(changed, applied)
    changed = [mf("210_results_losses.sql", "b") if f.name.startswith("210") else f for f in FILES]
    with pytest.raises(MigrationError):
        plan_migrations(changed, applied)


def test_changed_ts_file_rebuilds_ts():
    files = FILES + [mf("101_ts_extra.sql")]
    applied = {f.name: f.sha256 for f in files}
    changed = [mf("100_ts_generated.sql", "new") if f.name.startswith("100") else f for f in files]
    steps = actions(plan_migrations(changed, applied))
    i = steps.index(("reset_ts", ""))
    # every 1NN file is re-applied after the reset, then the views
    assert steps[i + 1:i + 3] == [("apply", "100_ts_generated.sql"), ("apply", "101_ts_extra.sql")]
    assert ("skip", "001_meta.sql") in steps and steps[-1] == ("apply", "910_api_losses.sql")


def test_changed_view_is_fine():
    applied = {f.name: f.sha256 for f in FILES}
    changed = [mf("900_api_core.sql", "new") if f.name.startswith("900") else f for f in FILES]
    assert ("apply", "900_api_core.sql") in actions(plan_migrations(changed, applied))


def test_repo_migrations_are_well_named():
    names = [f.name for f in discover()]
    # Other owners add files (005_scenarios, 2NN, 9NN), so check order, not exact positions.
    core = ["001_meta.sql", "002_ref.sql", "003_gis.sql", "004_results_core.sql", "100_ts_generated.sql"]
    assert [n for n in names if n in core] == core and names == sorted(names)
    assert "900_api_core.sql" in names
