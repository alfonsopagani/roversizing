"""Lettura dei file di input: unità, validazione, messaggi d'errore."""
import math
from pathlib import Path

import pytest

from dimensionamento import inputs
from dimensionamento.inputs import InputError

EXAMPLE = Path(__file__).resolve().parent / "riferimento.toml"


def test_unit_suffixes():
    assert inputs.si_name("v_flat_kmh") == ("v_flat", pytest.approx(1 / 3.6))
    assert inputs.si_name("drive_specific_mass_kg_kw") == ("drive_specific_mass", pytest.approx(1e-3))
    assert inputs.si_name("specific_energy_wh_kg") == ("specific_energy", pytest.approx(3600.0))
    assert inputs.si_name("shield_g_cm2") == ("shield", pytest.approx(10.0))
    assert inputs.si_name("slope_deg")[1] == pytest.approx(math.pi / 180)
    assert inputs.si_name("crr") == ("crr", 1.0)


def test_common_is_course_version():
    c = inputs.load_common()
    assert c.unchanged, "common.toml è stato modificato: aggiornare COMMON_FINGERPRINT solo se voluto"
    assert c.mission.mass_limit == 7500
    assert c.mission.v_flat == pytest.approx(5 / 3.6)
    assert c.environment.sol == pytest.approx(24.65 * 3600)


def test_override():
    d, _ = inputs.load_design(EXAMPLE, ["mobility.crr=0.6"])
    assert d.mobility.crr == pytest.approx(0.6)
    with pytest.raises(InputError):
        inputs.load_design(EXAMPLE, ["mobility.crrr=0.6"])


def _raw():
    import tomllib
    with open(EXAMPLE, "rb") as fh:
        return tomllib.load(fh)


def _set(raw, section, key, value):
    raw[section][key] = value


def _del(raw, section, key, _value):
    del raw[section][key]


@pytest.mark.parametrize("change, section, key, value, message", [
    (_set, "mobility", "ccr", 0.2, "ccr"),                        # chiave sconosciuta
    (_del, "mobility", "eta", None, "eta"),                       # chiave mancante
    (_set, "mobility", "crr", 1.5, "massimo"),                    # fuori intervallo
    (_set, "architecture", "power", "nucleare", "non ammesso"),   # valore non ammesso
])
def test_input_errors_are_reported(change, section, key, value, message):
    raw = _raw()
    change(raw, section, key, value)
    with pytest.raises(InputError, match=message):
        inputs.validate(raw, "prova.toml")


def test_item_needs_mass_or_fraction():
    raw = _raw()
    raw["items"][0]["mass_kg"] = 100.0           # la prima voce ha già fraction
    with pytest.raises(InputError, match="non entrambi"):
        inputs.validate(raw, "prova.toml")


def test_sequence_must_match_counts():
    raw = _raw()
    raw["operations"]["sequence"] = ["EVA"] * 14
    with pytest.raises(InputError, match="sequence"):
        inputs.validate(raw, "prova.toml")


def test_no_name_collisions_in_schema():
    for section, specs in inputs.SCHEMA.items():
        names = [inputs.si_name(k)[0] for k in specs]
        assert len(names) == len(set(names)), section
