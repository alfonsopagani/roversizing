"""Formule elementari controllate a mano.

Ogni test riporta il conto fatto a mano nel commento: se un modello viene
modificato, questi test mostrano subito che cosa cambia.
"""
import math
from types import SimpleNamespace as NS

import pytest

from dimensionamento import eclss, habitability, mobility, power, radiation, structure, thermal
from dimensionamento.constants import HOUR, KWH
from dimensionamento.margins import Item, apply_margins


# --- Abitabilità ------------------------------------------------------------
def test_pressurized_volume():
    # 9,7 / 0,8 + 1,36 = 13,485 m^3
    assert habitability.pressurized_volume(9.7, 0.8, 1.36) == pytest.approx(13.485)


def test_cabin_hemispherical_heads():
    # D = 2 m, V = 10 m^3: fondi = 4/3·π = 4,1888 m^3
    # L_c = (10 - 4,1888) / π = 1,8498 m;  A = 2π·1·1,8498 + 4π = 24,19 m^2
    g = habitability.cabin_geometry(10.0, 2.0, "semisferici")
    assert g.cylinder_length == pytest.approx(1.8498, abs=1e-4)
    assert g.area == pytest.approx(24.19, abs=0.01)
    assert g.length == pytest.approx(3.8498, abs=1e-4)


def test_elliptical_heads_area():
    # semiellissoide oblato a = 1, c = 0,5: area dell'ellissoide completo = 8,672 m^2
    v, a = habitability.head_volume_area(1.0, 0.5, "ellittici")
    assert a == pytest.approx(8.672, abs=1e-3)
    assert v == pytest.approx(4 / 3 * math.pi * 0.5)
    # con k = 1 si ritrova la sfera
    assert habitability.head_volume_area(1.0, 1.0, "ellittici")[1] == pytest.approx(4 * math.pi)


def test_cabin_too_wide():
    with pytest.raises(ValueError):
        habitability.cabin_geometry(5.0, 3.0, "semisferici")       # sfera da 14,1 m^3 > 5 m^3


# --- ECLSS -------------------------------------------------------------------
def test_cabin_gas_density():
    # Scheda: circa 0,68 kg/m^3 a 57 kPa e 34% di O2
    rho, w_o2 = eclss.cabin_gas(57e3, 0.34, 295.0)
    assert rho == pytest.approx(0.68, abs=0.01)
    assert w_o2 == pytest.approx(0.34 * 32.0 / (0.34 * 32.0 + 0.66 * 28.0), abs=1e-3)


def test_crew_time():
    # 2 persone × 10 s + (4 - 2) × 3 s + 2 × 1 s = 28 persona·s
    assert eclss.crew_time(2, 10.0, 4, 3.0, 1.0) == pytest.approx(28.0)


def test_access_gas_loss():
    e = NS(suitport_evas=10, suitport_cycles_per_eva=2, suitport_loss=0.03,
           airlock_evas=2, airlock_cycles_per_eva=1, airlock_loss_fraction=0.1, airlock_gas=3.7)
    # suitport 10·2·2·0,03 = 1,2 kg; airlock 2·1·0,1·3,7·0,68 = 0,503 kg
    assert eclss.access_gas_loss(e, 2, 0.68) == pytest.approx(1.2 + 0.50320)


# --- Radiazioni --------------------------------------------------------------
def test_spe_dose_interpolation():
    # 40 mSv senza schermo, 25 mSv a 10 g/cm^2 (100 kg/m^2): a metà spessore 40·(25/40)^0,5 = 31,6 mSv
    assert radiation.spe_dose(0.0, 40.0, 25.0, 100.0) == pytest.approx(40.0)
    assert radiation.spe_dose(50.0, 40.0, 25.0, 100.0) == pytest.approx(31.62, abs=0.01)
    assert radiation.spe_dose(100.0, 40.0, 25.0, 100.0) == pytest.approx(25.0)
    assert radiation.spe_dose(200.0, 40.0, 25.0, 100.0) == pytest.approx(25.0)    # nessuna estrapolazione


def test_shelter_mass():
    # 10 g/cm^2 = 100 kg/m^2; 6 m^2 -> 600 kg; acqua 100 kg al 50% -> 50 kg; aggiunta 550 kg
    s = radiation.shelter_mass(100.0, 6.0, 100.0, 0.5, 0.0)
    assert (s.required, s.from_water, s.added) == pytest.approx((600.0, 50.0, 550.0))


# --- Struttura ---------------------------------------------------------------
def test_fem_override():
    cab = NS(fem_shell=300.0, fem_nonmodeled_fraction=0.1, shell_areal=8.0, interior_areal=6.0,
             insulation_thickness=0.02, insulation_density=100.0)
    m = structure.cabin_masses(30.0, cab)
    assert m.shell == pytest.approx(330.0) and m.shell_source == "FEM"
    assert m.interior == pytest.approx(180.0) and m.insulation == pytest.approx(60.0)


# --- Mobilità ----------------------------------------------------------------
def test_traction_power_flat_and_slope():
    # 0,2 · 1000 kg · 3,72 m/s^2 · 1 m/s / 1 = 744 W
    assert mobility.traction_power(1000, 3.72, 0.2, 0.0, 1.0, 1.0) == pytest.approx(744.0)
    # 30°: (0,2·cos30 + sin30)·3720 = (0,17321 + 0,5)·3720 = 2504,3 W
    assert mobility.traction_power(1000, 3.72, 0.2, math.radians(30), 1.0, 1.0) == pytest.approx(2504.3, abs=0.1)


def test_peak_power_case():
    p, case = mobility.peak_power(1000, 3.72, 0.3, 1.0, 5 / 3.6, math.radians(15), 1 / 3.6)
    assert case == "piano" and p == pytest.approx(0.3 * 3720 * 5 / 3.6)


def test_traction_energy():
    # (1 + 0,05) · (0,1·1000·3,72·1000 + 1000·3,72·100) / 0,5 = 1,05 · 744 000 / 0,5 J
    e = mobility.traction_energy(1000, 3.72, 0.1, 0.5, 1000.0, 100.0, 0.05)
    assert e == pytest.approx(1.05 * (372e3 + 372e3) / 0.5)


def test_max_speed_inverts_power():
    p = mobility.traction_power(5000, 3.72, 0.25, 0.1, 2.0, 0.8)
    assert mobility.max_speed(p, 5000, 3.72, 0.25, 0.1, 0.8) == pytest.approx(2.0)


def test_tipping_angle():
    assert math.degrees(mobility.tipping_angle(2.0, 1.0)) == pytest.approx(45.0)


# --- Termico -----------------------------------------------------------------
def test_radiator_area_and_sink_temperature():
    # A = 1000 / (5,670e-8 · 300^4) = 2,177 m^2  (ε = 1, pozzo a 0 K)
    assert thermal.radiator_area(1000.0, 300.0, 0.0, 1.0) == pytest.approx(2.177, abs=1e-3)
    # pozzo: cielo con F = 0, suolo con F = 1
    assert thermal.sink_temperature(247.0, 179.5, 0.0) == pytest.approx(179.5)
    assert thermal.sink_temperature(247.0, 179.5, 1.0) == pytest.approx(247.0)


def test_radiator_colder_than_sink():
    with pytest.raises(ValueError):
        thermal.radiator_area(1000.0, 200.0, 220.0, 0.84)


# --- Margini -----------------------------------------------------------------
def test_margins():
    margins = NS(mga_new=0.2, mga_modified=0.1, mga_existing=0.05, system=0.15)
    items = [Item("a", "x", 100.0, "da_progettare"), Item("b", "x", 100.0, "esistente"),
             Item("c", "y", 50.0, None, fixed=True)]
    b = apply_margins(items, margins)
    # prevista 120 + 105 = 225; sistema 0,15·200 = 30; totale 225 + 30 + 50 = 305
    assert b.predicted_dry == pytest.approx(225.0)
    assert b.system_margin == pytest.approx(30.0)
    assert b.total == pytest.approx(305.0)


# --- Potenza -----------------------------------------------------------------
def test_battery_capacity_units():
    # energia: 10 kWh / 0,8 = 12,5 kWh; potenza: 50 kW / 2 h^-1 = 25 kWh -> governa la potenza
    cap, crit = power.battery_capacity(10 * KWH, 0.8, 50e3, 0.0, 2.0)
    assert cap == pytest.approx(25 * KWH) and crit == "potenza di picco"
    cap, crit = power.battery_capacity(30 * KWH, 0.8, 50e3, 0.0, 2.0)
    assert cap == pytest.approx(37.5 * KWH) and crit == "energia"


def test_allowed_cycles_step():
    dod, cyc = [1.0, 0.8, 0.6, 0.4, 0.2], [250, 500, 1000, 3000, 10000]
    assert power.allowed_cycles(0.55, dod, cyc) == (1000, 0.6)
    assert power.allowed_cycles(0.80, dod, cyc) == (500, 0.8)
    assert power.allowed_cycles(0.81, dod, cyc) == (250, 1.0)


def _sol(name, drive, eva, day, night, count=1):
    return NS(name=name, count=count, drive=drive * HOUR, eva=eva * HOUR, day=day * HOUR, night=night * HOUR)


def test_simulate_battery_only():
    # carico costante 1 kW per 2 sol da 24 h, nessuna generazione: debito 48 kWh, un ciclo
    sols = [_sol("a", 0, 0, 12, 12, 2)]
    p = {"drive": 1e3, "eva": 1e3, "day": 1e3, "night": 1e3}
    sim = power.simulate(power.sol_sequence(sols), p, 0.0, power.Generation(), 24 * HOUR, 1.0, False)
    assert sim.max_deficit == pytest.approx(48 * KWH)
    assert len(sim.cycles) == 1


def test_simulate_pv_daily_cycle():
    # 1 kW costante; ala con 2 kW nominali e 12 h equivalenti: 24 kWh di giorno = carico del sol.
    # Di giorno l'ala fornisce 2 kW per 12 h: surplus 12 kWh; di notte debito 12 kWh, un ciclo per sol.
    sols = [_sol("a", 0, 0, 12, 12, 3)]
    p = {"drive": 1e3, "eva": 1e3, "day": 1e3, "night": 1e3}
    gen = power.Generation(pv=2e3)
    sim = power.simulate(power.sol_sequence(sols), p, 0.0, gen, 24 * HOUR, 12 * HOUR, False)
    assert sim.max_deficit == pytest.approx(12 * KWH)
    assert len(sim.cycles) == 3


def test_sol_sequence_round_robin_and_declared():
    a, b = _sol("a", 1, 0, 11, 12, 2), _sol("b", 0, 0, 12, 12, 1)
    assert [s.name for s in power.sol_sequence([a, b])] == ["a", "b", "a"]
    assert [s.name for s in power.sol_sequence([a, b], ["a", "a", "b"])] == ["a", "a", "b"]


def test_return_trip_duration():
    # 50 km a 3 km/h = 16,67 h di guida, 10 h per sol: 1 sol completo + 6,67 h = 24,65 + 6,67 h
    r = power.return_trip(50e3, 3 / 3.6, 10 * HOUR, 24.65 * HOUR, 1e3, 0.0, power.Generation(), 1.0, 1.0, 0.0)
    assert r.duration / HOUR == pytest.approx(24.65 + 50 / 3 - 10, abs=1e-6)
    assert r.energy_need == pytest.approx(1e3 * r.duration)


# --- fotovoltaico: ala ripiegata durante la guida -------------------------------
def test_pv_share_integrates_to_one():
    light = 12 * HOUR
    assert power.pv_share(0.0, light, light) == pytest.approx(1.0)
    assert power.pv_share(0.0, light / 2, light) == pytest.approx(0.5)
    assert power.pv_share(light, 2 * light, light) == 0.0


def test_pv_no_production_while_driving():
    sol = 24.65 * HOUR
    s = NS(name="guida", count=1, drive=4 * HOUR, eva=0.0, day=8.65 * HOUR, night=12 * HOUR)
    p = {"drive": 1000.0, "eva": 0.0, "day": 0.0, "night": 0.0}
    gen = power.Generation(pv=10_000.0)
    # solo la guida consuma: con l'ala ripiegata nessuna produzione la compensa
    stowed = power.simulate([s], p, 0.0, gen, sol, 9 * HOUR, False, pv_while_driving=False)
    assert stowed.max_deficit == pytest.approx(4 * HOUR * 1000.0)
    open_ = power.simulate([s], p, 0.0, gen, sol, 9 * HOUR, False, pv_while_driving=True)
    assert open_.max_deficit < stowed.max_deficit


def test_pv_auto_sizing_uses_collectable_share():
    sol = 24.65 * HOUR
    s = NS(name="guida", count=1, drive=6.325 * HOUR, eva=0.0, day=6.325 * HOUR, night=12 * HOUR)
    p = {"drive": 1000.0, "eva": 0.0, "day": 1000.0, "night": 1000.0}
    d = NS(pv=NS(power=0.0, sun_hours=9 * HOUR, deployed_while_driving=False))
    gen = power.generation("fotovoltaico", d, [s], p, 0.0, 0.0, sol, sol)
    e_sol = 1000.0 * sol
    # guida a metà del periodo di luce: si raccoglie metà dell'energia giornaliera
    assert gen.pv == pytest.approx(e_sol / (9 * HOUR * 0.5), rel=1e-3)


def test_cad_geometry_override():
    g = habitability.cabin_geometry(13.5, 2.5, "semisferici")
    assert habitability.apply_cad(g, 0.0, 0.0) is g
    c = habitability.apply_cad(g, 15.0, 40.0)
    assert (c.volume, c.area, c.diameter) == (15.0, 40.0, g.diameter)
    assert c.source == "CAD (volume e superficie)"
    only_area = habitability.apply_cad(g, 0.0, 40.0)
    assert only_area.volume == g.volume and only_area.area == 40.0
