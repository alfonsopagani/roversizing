"""Ciclo di massa, verifiche, sensitività e riga di comando sull'esempio."""
import copy
from pathlib import Path

import pytest

from dimensionamento import inputs, requirements, sizing
from dimensionamento.__main__ import main
from dimensionamento.sensitivity import sweep

EXAMPLE = Path(__file__).resolve().parent / "riferimento.toml"


@pytest.fixture(scope="module")
def common():
    return inputs.load_common()


@pytest.fixture(scope="module")
def example(common):
    d, raw = inputs.load_design(EXAMPLE)
    return d, raw, sizing.run(common, d)


def test_example_converges_to_the_fixed_point(common, example):
    d, _, res = example
    assert res.loop.converged
    assert 0.0 < res.loop.gain < 1.0
    # la soluzione soddisfa m = F(m) entro la tolleranza
    total = sizing.evaluate(common, d, res.fixed, res.loop.mass)[0].total
    assert total == pytest.approx(res.loop.mass, abs=0.2)
    # e non dipende dalla massa di partenza
    other = sizing.close_mass_loop(common, d, start=3000.0)
    assert other.mass == pytest.approx(res.loop.mass, abs=0.5)


def test_budget_identity(example):
    _, _, res = example
    b = res.budget
    assert b.total == pytest.approx(b.fixed + b.base_dry + b.mga + b.system_margin)
    assert sum(it.predicted for it in b.items) + b.system_margin == pytest.approx(b.total)


def test_fixed_masses_have_no_margin(example):
    _, _, res = example
    for it in res.budget.items:
        if it.subsystem in ("carico utile", "equipaggio", "consumabili") or it.name == "Tute EVA":
            assert it.fixed and it.mga == 0.0


def test_divergence_message(common, example):
    _, raw, _ = example
    data = copy.deepcopy(raw)
    data["items"][0]["fraction"] = 0.9            # telaio al 90% della massa totale
    d = inputs.validate(data, "prova.toml")
    loop = sizing.run(common, d).loop
    assert not loop.converged
    assert "somma delle frazioni" in loop.message


def test_requirements_table(example):
    _, _, res = example
    checks = requirements.check_all(res)
    ids = {c.mr for c in checks}
    for mr in ("MR-07", "MR-08", "MR-10", "MR-11", "MR-12", "MR-14", "MR-15",
               "MR-16", "MR-20", "MR-21"):
        assert mr in ids
    assert all(c.status in (requirements.OK, requirements.KO, requirements.NV, requirements.INFO)
               for c in checks)


@pytest.mark.parametrize("arch", ["rps", "fotovoltaico", "celle_combustibile", "batterie"])
def test_architectures_run(common, example, arch):
    _, raw, _ = example
    data = copy.deepcopy(raw)
    data["architecture"]["power"] = arch
    res = sizing.run(common, inputs.validate(data, "prova.toml"))
    if res.loop.converged:
        assert res.budget.total > 0
        requirements.check_all(res)
    else:
        assert res.loop.message


def test_hybrid_requires_declared_power(common, example):
    _, raw, _ = example
    data = copy.deepcopy(raw)
    data["architecture"]["power"] = "ibrido"
    with pytest.raises(sizing.SizingError):
        sizing.run(common, inputs.validate(data, "prova.toml"))
    data["rps"]["power_kw"] = 2.0
    data["pv"]["power_kw"] = 6.0
    sizing.run(common, inputs.validate(data, "prova.toml"))


def test_sol_hours_must_sum_to_a_sol(common, example):
    _, raw, _ = example
    data = copy.deepcopy(raw)
    data["operations"]["sol_types"][0]["day_h"] += 1.0
    with pytest.raises(sizing.SizingError, match="sol"):
        sizing.run(common, inputs.validate(data, "prova.toml"))


def test_sweep(common, example):
    _, raw, _ = example
    rows = sweep(common, raw, "riferimento.toml", "mobility.crr", [0.1, 0.3, 0.6])
    assert [r["value"] for r in rows] == [0.1, 0.3, 0.6]
    ok = [r for r in rows if r["converged"]]
    assert ok and all(a["total"] <= b["total"] for a, b in zip(ok, ok[1:]))
    # chiave intera: i valori restano interi
    rows = sweep(common, raw, "riferimento.toml", "operations.excursions", [12.0, 18.0])
    assert [r["value"] for r in rows] == [12, 18] and all(r["converged"] for r in rows)
    # valore non valido: la riga riporta l'errore, le altre restano
    rows = sweep(common, raw, "riferimento.toml", "mobility.crr", [0.2, 1.5])
    assert rows[0]["converged"] and not rows[1]["converged"] and "massimo" in rows[1]["note"]


def test_cli_runs_and_writes(tmp_path, capsys):
    assert main([str(EXAMPLE), "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Budget di massa" in out and "Verifica dei requisiti" in out
    assert (tmp_path / "report.md").exists()
    assert any(p.suffix == ".csv" for p in tmp_path.iterdir())


def test_cli_reports_input_errors(tmp_path, capsys):
    bad = tmp_path / "rotto.toml"
    bad.write_text("[group\nname = 1", encoding="utf-8")
    assert main([str(bad)]) == 1
    assert "Errore" in capsys.readouterr().err


def test_set_optional_key_absent_from_file(common):
    d, _ = inputs.load_design(EXAMPLE, ['operations.sequence=["EVA","EVA","EVA","EVA","EVA","EVA","EVA",'
                                        '"trasferimento","trasferimento","trasferimento","trasferimento",'
                                        '"guida ed EVA","guida ed EVA","guida ed EVA"]'])
    assert d.operations.sequence[0] == "EVA"
    assert sizing.run(common, d).loop.converged


def test_center_of_gravity_ignores_massless_items():
    from dimensionamento.margins import Item
    items = [Item("a", "x", 100.0, "esistente", position=[0.0, 0.0, 1.0]),
             Item("b", "x", 100.0, "esistente", position=[2.0, 0.0, 3.0]),
             Item("vuota", "x", 0.0, "esistente")]
    cg, missing = sizing.center_of_gravity(items)
    assert missing == [] and cg == pytest.approx([1.0, 0.0, 2.0])


def test_excursions_outside_mr07_fail(common, example):
    _, raw, _ = example
    data = copy.deepcopy(raw)
    data["operations"]["excursions"] = 5
    res = sizing.run(common, inputs.validate(data, "prova.toml"))
    row = next(c for c in requirements.check_all(res) if c.description.startswith("Escursioni"))
    assert row.status == requirements.KO


def test_partial_positions_reported(common, example):
    from dimensionamento import report
    _, raw, _ = example
    data = copy.deepcopy(raw)
    data["positions"] = {"battery": [6.0, 0.0, 1.0]}
    res = sizing.run(common, inputs.validate(data, "prova.toml"))
    assert res.cg is None and "Batteria" not in res.cg_missing
    rows = report.performance_table(res)[2]
    assert any(r[0].startswith("Baricentro") and "Guscio della cabina" in r[1] for r in rows)


def test_positions_give_center_of_gravity_used_by_mr11(common, example):
    _, raw, res0 = example
    data = copy.deepcopy(raw)
    keys = ("cabin", "tanks", "crew", "suits", "shield", "radiator", "drive", "payload",
            "battery", "rps")
    data["positions"] = {k: [4.0, 0.0, 3.0] for k in keys}
    for it in data["items"]:
        it["position_m"] = [4.0, 0.0, 3.0]
    assert data["mobility"]["cg_height_m"] != 3.0          # valore dichiarato, da ignorare
    res = sizing.run(common, inputs.validate(data, "prova.toml"))
    assert res.cg_missing == [] and res.cg == pytest.approx([4.0, 0.0, 3.0])
    assert res.loop.mass == pytest.approx(res0.loop.mass)       # le posizioni non cambiano le masse
    assert res.cg_height == pytest.approx(3.0)
    row = next(c for c in requirements.check_all(res) if c.description.startswith("Angolo di ribaltamento"))
    assert "h_G = 3,00 m, dalle posizioni" in row.obtained
    h, origin = requirements.cg_height_used(res.design, res)
    assert h == pytest.approx(3.0) and origin == "dalle posizioni"


def _rows(res, mr):
    return [c for c in requirements.check_all(res) if c.mr == mr]


def test_mr12_night_shorter_than_common_fails(common, example):
    _, raw, _ = example
    data = copy.deepcopy(raw)
    for s in data["operations"]["sol_types"]:          # notte di 10 h, ore spostate nella sosta
        s["day_h"] += s["night_h"] - 10.0
        s["night_h"] = 10.0
    res = sizing.run(common, inputs.validate(data, "prova.toml"))
    night = next(c for c in _rows(res, "MR-12") if c.description.startswith("Durata della notte"))
    assert night.status == requirements.KO
    energy = next(c for c in _rows(res, "MR-12") if c.description.startswith("Energia"))
    expected = res.fixed.p_service["night"] * common.environment.night / 3.6e6   # 12 h, non 10
    assert f"{expected:.1f}".replace(".", ",") in energy.required


def test_mr04_more_evas_accepted_and_fewer_fail(common, example):
    _, raw, res0 = example
    data = copy.deepcopy(raw)
    data["eva_access"]["suitport_evas"] = 12
    res = sizing.run(common, inputs.validate(data, "prova.toml"))
    assert _rows(res, "MR-04")[0].status == requirements.OK
    assert res.fixed.cons.o2 > res0.fixed.cons.o2      # consumabili sulle EVA dichiarate
    data["eva_access"]["suitport_evas"] = 8
    res = sizing.run(common, inputs.validate(data, "prova.toml"))
    assert _rows(res, "MR-04")[0].status == requirements.KO


def test_traction_on_planned_distance(common, example):
    d, _, res = example
    planned = sum(s.count * s.drive for s in d.operations.sol_types) * d.operations.v_mean
    assert res.dep.distance == pytest.approx(max(planned, common.mission.distance))


def test_mr22_fem_results(common, example):
    _, raw, _ = example
    data = copy.deepcopy(raw)
    data["cabin"].update(fem_shell_kg=300.0, fem_min_margin=0.1, fem_freq_lateral_hz=6.0)
    res = sizing.run(common, inputs.validate(data, "prova.toml"))
    st = [c.status for c in _rows(res, "MR-22")]
    assert st == [requirements.INFO, requirements.OK, requirements.KO, requirements.NV]


def test_mr19_mandatory_and_optional_fairing(common, example):
    _, raw, _ = example
    data = copy.deepcopy(raw)
    data["envelope"] = {"length_m": 7.0, "width_m": 3.5, "height_m": 3.8,
                        "orientation": "perpendicolare"}
    res = sizing.run(common, inputs.validate(data, "prova.toml"))
    assert [c.status for c in _rows(res, "MR-19")] == [requirements.OK, requirements.KO]
    data["envelope"]["orientation"] = "parallelo"
    res = sizing.run(common, inputs.validate(data, "prova.toml"))
    assert [c.status for c in _rows(res, "MR-19")] == [requirements.INFO, requirements.INFO]


def test_off_design_keeps_installed_hardware(common, example):
    d, raw, _ = example
    data = copy.deepcopy(raw)
    data["mobility"]["crr"] = 0.6
    nominal, off = sizing.off_design(common, d, inputs.validate(data, "prova.toml"))
    assert off.dep.p_peak == nominal.dep.p_peak
    assert off.dep.battery_capacity == nominal.dep.battery_capacity
    assert off.loop.mass == nominal.loop.mass
    assert off.dep.e_traction > nominal.dep.e_traction
    v10 = next(c for c in _rows(off, "MR-10") if c.description.startswith("Velocità in piano"))
    assert v10.status == requirements.KO                # a 0,6 i motori non bastano più


def test_frozen_sweep_lists_failed_requirements(common, example):
    _, raw, _ = example
    rows = sweep(common, raw, "riferimento.toml", "mobility.crr", [0.3, 0.6], frozen=True)
    assert "MR-10" not in rows[0]["failed"] and "MR-10" in rows[1]["failed"]
    rows = sweep(common, raw, "riferimento.toml", "mobility.crr", [0.6])
    assert "MR-20" in rows[0]["failed"]


def test_cli_off_design(capsys):
    assert main([str(EXAMPLE), "--fuori-progetto", "mobility.crr=0.6"]) == 0
    out = capsys.readouterr().out
    assert "Requisiti non soddisfatti fuori progetto" in out and "MR-10" in out


def test_common_assumptions_checked_on_design_values(common, example):
    d, raw, res = example
    assert all(c.status == requirements.OK for c in _rows(res, requirements.COMMON))
    data = copy.deepcopy(raw)
    data["mobility"]["crr"] = 0.08
    data["loads"]["day_kw"] = 3.6
    low = sizing.run(common, inputs.validate(data, "prova.toml"))
    assert [c.status for c in _rows(low, requirements.COMMON)] == [requirements.KO] * 2
    data = copy.deepcopy(raw)
    data["mobility"]["crr"] = 0.6                       # caso di verifica: resta il C_rr di progetto
    _, off = sizing.off_design(common, d, inputs.validate(data, "prova.toml"))
    assert all(c.status == requirements.OK for c in _rows(off, requirements.COMMON))


def test_radiator_sized_on_worst_case(common, example):
    _, raw, res = example
    fx, m = res.fixed, common.mission
    data = copy.deepcopy(raw)
    data["emergency"]["load_kw"] = 1.0                  # emergenza meno gravosa del caso nominale
    light = sizing.run(common, inputs.validate(data, "prova.toml")).fixed
    assert light.heat_case.startswith("nominale") and light.heat < fx.heat
    assert fx.heat_case.startswith("emergenza")
    assert fx.heat == pytest.approx(m.emergency_crew * 144 + 1.3 * 3000.0)


def test_mr14_fails_on_energy_not_duration(example):
    _, _, res = example
    em = res.emergency
    assert em.duration <= 72 * 3600                     # il rientro è nei tempi...
    assert em.energy_need > em.energy_available         # ...ma l'energia non basta
    row = next(c for c in _rows(res, "MR-14") if c.description.startswith("Rientro"))
    assert row.status == requirements.KO


def test_rps_declared_power(common, example):
    _, raw, res0 = example
    data = copy.deepcopy(raw)
    data["rps"]["power_kw"] = 6.0
    res = sizing.run(common, inputs.validate(data, "prova.toml"))
    assert res.dep.gen.rps == pytest.approx(6000.0)
    assert res.dep.rps_mass == pytest.approx(6000.0 / data["rps"]["specific_power_w_kg"])
    # più potenza continua della media: la batteria copre meno debito
    assert res.dep.battery_capacity < res0.dep.battery_capacity


def test_italian_number_format():
    from dimensionamento import report
    assert report.n(1234.5, 1) == "1.234,5"
    assert report.n(-1500) == "-1.500"
    assert report.n(0.123, 3) == "0,123"
    assert report.n(1e6) == "1.000.000"
    assert report.n(None) == "-" and report.n(float("nan")) == "-"
    assert requirements._n(7203.8) == "7.204"
