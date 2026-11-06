"""Supporto vitale (ECLSS) a ciclo aperto: consumabili e serbatoi.

Parametri: Scheda dati, sezione *Equipaggio ed ECLSS*. Requisiti: MR-03,
MR-04, MR-05, MR-13, MR-14. Equazioni e ipotesi: MODELLI.md, §4.
"""
from __future__ import annotations

from dataclasses import dataclass

from .constants import M_N2, M_O2, R_UNIVERSAL


def crew_time(crew: int, duration: float, emergency_crew: int,
              emergency_duration: float, reserve: float) -> float:
    """Tempo-persona da rifornire [persona·s] (MODELLI §4).

        T = n·t_esc + (n_em - n)·t_em + n·t_riserva
    """
    return (crew * duration + max(0, emergency_crew - crew) * emergency_duration
            + crew * reserve)


def cabin_gas(pressure: float, o2_fraction: float, temperature: float) -> tuple[float, float]:
    """Densità della miscela di cabina [kg/m^3] e frazione in massa di O2 (MODELLI §4).

        M = x·M_O2 + (1 - x)·M_N2,   ρ = p·M / (R·T),   w_O2 = x·M_O2 / M
    """
    molar_mass = o2_fraction * M_O2 + (1.0 - o2_fraction) * M_N2
    rho = pressure * molar_mass / (R_UNIVERSAL * temperature)
    return rho, o2_fraction * M_O2 / molar_mass


@dataclass
class Consumables:
    o2_metabolic: float      # kg
    o2_eva: float            # kg, consumo delle tute
    gas_leak: float          # kg di miscela persa dalla cabina
    gas_access: float        # kg di miscela persa nei cicli di suitport e airlock
    o2: float                # kg di O2 da stivare
    n2: float                # kg di N2 da stivare
    water: float             # kg
    food: float              # kg, cibo confezionato
    sorbent: float           # kg di assorbitore di CO2 consumato
    food_volume: float       # m^3
    co2: float               # kg di CO2 prodotta (informativo)
    person_time: float       # tempo-persona rifornito [persona·s]

    @property
    def total(self) -> float:
        return self.o2 + self.n2 + self.water + self.food + self.sorbent


def access_gas_loss(e, eva_crew: int, rho: float) -> float:
    """Miscela persa nei cicli di uscita e rientro [kg] (MR-05, MODELLI §4).

        suitport: m_cicli = N_EVA,sp · n_EVA · c_sp · m_ciclo
        airlock:  m_cicli = N_EVA,al · c_al · f · V_gas · ρ
    """
    suitport = e.suitport_evas * eva_crew * e.suitport_cycles_per_eva * e.suitport_loss
    airlock = e.airlock_evas * e.airlock_cycles_per_eva * e.airlock_loss_fraction * e.airlock_gas * rho
    return suitport + airlock


def eva_count(d) -> int:
    """EVA per escursione dichiarate dal gruppo: suitport + airlock (MR-04 ne chiede almeno 10)."""
    return d.eva_access.suitport_evas + d.eva_access.airlock_evas


def consumables(c, d) -> Consumables:
    """Consumabili per un'escursione [kg] (MODELLI §4); c: dati comuni, d: progetto.

        O2   = r_O2·T·(1 - g_O2) + N_EVA·n_EVA·(r_O2,EVA·t_EVA + m_O2,fisso) + w_O2·(m_perdite + m_cicli)
        N2   = (1 - w_O2)·(m_perdite + m_cicli)
        H2O  = [(r_potabile + r_igiene)·T + N_EVA·n_EVA·r_H2O,EVA·t_EVA]·(1 - g_H2O)
        cibo = r_cibo·T + N_EVA·n_EVA·r_cibo,EVA·t_EVA
        assorbitore = k_CO2·r_CO2·T

    T è il tempo-persona di ``crew_time``, m_cicli la miscela di ``access_gas_loss``.
    """
    m, x, ops = c.mission, d.eclss, d.operations
    duration = m.excursion_sols * c.environment.sol
    person_time = crew_time(m.crew, duration, m.emergency_crew, m.emergency_duration, ops.reserve)
    n_eva = eva_count(d)                                          # EVA dichiarate (MR-04: almeno 10)
    eva_time = n_eva * m.eva_crew * m.eva_duration                # tempo-persona in EVA [persona·s]
    rho, w_o2 = cabin_gas(m.cabin_pressure, m.cabin_o2_fraction, x.cabin_temperature)

    o2_met = x.o2 * person_time * (1.0 - x.o2_recovery)
    o2_eva = x.eva_o2 * eva_time + n_eva * m.eva_crew * x.eva_o2_fixed
    leak = x.cabin_leak * duration
    access = access_gas_loss(d.eva_access, m.eva_crew, rho)
    o2 = o2_met + o2_eva + w_o2 * (leak + access)
    n2 = (1.0 - w_o2) * (leak + access)
    water = ((x.potable_water + x.hygiene_water) * person_time
             + x.eva_water * eva_time) * (1.0 - x.water_recovery)
    food = x.food * person_time + x.eva_food * eva_time
    co2 = x.co2 * person_time
    return Consumables(o2_met, o2_eva, leak, access, o2, n2, water, food,
                       x.co2_sorbent_ratio * co2, x.food_volume * person_time, co2, person_time)


def tank_mass(cons: Consumables, x) -> float:
    """Massa dei serbatoi [kg] (MODELLI §4).

        m = k_O2·m_O2 + k_N2·m_N2 + k_H2O·m_H2O
    """
    return x.o2_tank_ratio * cons.o2 + x.n2_tank_ratio * cons.n2 + x.water_tank_ratio * cons.water
