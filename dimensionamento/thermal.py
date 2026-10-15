"""Controllo termico: radiatore della cabina e dispersioni dell'isolamento.

Parametri: Scheda dati, sezioni *Ambiente marziano* (temperature del suolo e
del cielo) e *Controllo termico* (massa areale e proprietà ottiche del
radiatore, temperatura dei radiatori, aerogel).

Il radiatore smaltisce il calore metabolico dell'equipaggio e la quota dei
carichi elettrici di servizio dissipata in cabina, nel caso più gravoso fra
quello nominale e l'emergenza con quattro persone (MR-14). Il calore di scarto
dell'RPS ha un radiatore proprio, che si considera compreso nella sua potenza
specifica (ipotesi: la Scheda riporta massa e superficie del radiatore senza
precisarlo).

Il modello trascura il calore solare assorbito dal radiatore e la quota
smaltita per convezione: la prima riduce la capacità del radiatore di giorno,
la seconda la aumenta di poco (Scheda: 227 W su 6.580 W nell'esempio GRC).
"""
from __future__ import annotations

from .constants import SIGMA_SB


def sink_temperature(t_ground: float, t_sky: float, ground_view: float) -> float:
    """Temperatura equivalente di pozzo [K].

        T_pozzo^4 = F_suolo·T_suolo^4 + (1 - F_suolo)·T_cielo^4

    F_suolo è il fattore di vista verso il suolo: 0 per un radiatore
    orizzontale rivolto verso l'alto, 0,5 per un radiatore verticale.
    """
    return (ground_view * t_ground**4 + (1.0 - ground_view) * t_sky**4) ** 0.25


def heat_load(crew: int, metabolic: float, p_service: float, dissipated: float) -> float:
    """Calore da smaltire [W]: Q = n·q_met + f_diss·P_servizio."""
    return crew * metabolic + dissipated * p_service


def radiator_area(heat: float, t_radiator: float, t_sink: float, emissivity: float) -> float:
    """Superficie radiante necessaria [m^2].

        A = Q / [ε·σ·(T_rad^4 - T_pozzo^4)]
    """
    if t_radiator <= t_sink:
        raise ValueError(f"radiatore: la temperatura del radiatore ({t_radiator:.0f} K) deve essere "
                         f"maggiore di quella di pozzo ({t_sink:.0f} K).")
    return heat / (emissivity * SIGMA_SB * (t_radiator**4 - t_sink**4))


def insulation_heat_loss(area: float, conductivity: float, thickness: float,
                         t_inside: float, t_outside: float) -> float:
    """Calore disperso attraverso l'isolamento della cabina [W] (informativo).

        Q = k·A·(T_int - T_est) / t

    Nel caso freddo serve a controllare l'ipotesi sui riscaldatori inclusa nei
    carichi di servizio notturni. Il valore è un limite superiore: si trascura
    la resistenza del guscio e dello strato limite esterno.
    """
    if thickness <= 0.0:
        return float("inf")
    return conductivity * area * (t_inside - t_outside) / thickness
