"""The synthetic validation dataset can never be written to a staging or production database."""

import pytest

from scripts import seed_validation_dataset as seed


@pytest.mark.parametrize("environment", ["production", "staging", "", "something-else"])
def test_the_seed_refuses_outside_development_and_test(monkeypatch, environment):
    monkeypatch.setenv("MDARIX_ENV", environment)

    def no_database(*_args, **_kwargs):
        raise AssertionError("the database must not be opened")

    monkeypatch.setattr(seed, "SessionLocal", no_database)
    with pytest.raises(seed.SyntheticSeedRefused):
        seed.refuse_outside_local()
    # Refused before anything is read or written, with or without --apply.
    assert seed.main(["--apply"]) == 2
    assert seed.main([]) == 2


@pytest.mark.parametrize("environment", ["development", "test"])
def test_the_seed_runs_on_local_databases(monkeypatch, environment, capsys):
    monkeypatch.setenv("MDARIX_ENV", environment)
    seed.refuse_outside_local()
    assert seed.main([]) == 0  # the dry run: nothing written without --apply
    assert "Dry run only" in capsys.readouterr().out
