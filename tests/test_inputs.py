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
    d, _ = inputs.load_design(EXAMPLE, ["mobility.crr=0.6", "cabin.fem_min_margin=0.2"])
    assert d.mobility.crr == pytest.approx(0.6)
    assert d.cabin.fem_min_margin == pytest.approx(0.2)        # chiave facoltativa assente dal file
    with pytest.raises(InputError):
        inputs.load_design(EXAMPLE, ["mobility.crrr=0.6"])


def _raw():
    import tomllib
    with open(EXAMPLE, "rb") as fh:
        return tomllib.load(fh)


def _night_drive_without_loads(raw):
    raw["operations"]["sol_types"][0]["night_drive_h"] = 2.0
    del raw["loads"]["night_drive_kw"]


@pytest.mark.parametrize("change, message", [
    pytest.param(lambda r: r["mobility"].update(ccr=0.2), "ccr", id="chiave sconosciuta"),
    pytest.param(lambda r: r["mobility"].pop("eta"), "eta", id="chiave mancante"),
    pytest.param(lambda r: r["mobility"].update(crr=1.5), "massimo", id="fuori intervallo"),
    pytest.param(lambda r: r["architecture"].update(power="nucleare"), "non ammesso", id="valore non ammesso"),
    pytest.param(lambda r: r["items"][0].update(mass_kg=100.0), "non entrambi", id="massa e frazione"),
    pytest.param(lambda r: r["operations"].update(sequence=["EVA"] * 14), "sequence", id="sequence"),
    pytest.param(_night_drive_without_loads, "night_drive_kw", id="guida notturna senza carichi"),
    pytest.param(lambda r: r["eva_access"].update(airlock_evas=2), "airlock_gas_m3", id="airlock senza dati"),
    pytest.param(lambda r: r["eva_access"].update(suitport_cycles_per_eva=0), "suitport_cycles_per_eva",
                 id="suitport senza cicli"),
])
def test_input_errors_are_reported(change, message):
    raw = _raw()
    change(raw)
    with pytest.raises(InputError, match=message):
        inputs.validate(raw, "prova.toml")


def test_no_name_collisions_in_schema():
    for section, specs in inputs.SCHEMA.items():
        names = [inputs.si_name(k)[0] for k in specs]
        assert len(names) == len(set(names)), section
