"""Controllo termico: radiatore della cabina e dispersioni dell'isolamento.

Parametri: Scheda dati, sezioni *Ambiente marziano* e *Controllo termico*.
Equazioni e ipotesi: MODELLI.md, §9.
"""
from __future__ import annotations

from .constants import SIGMA_SB


def sink_temperature(t_ground: float, t_sky: float, ground_view: float) -> float:
    """Temperatura equivalente di pozzo [K] (MODELLI §9).

        T_pozzo^4 = F·T_suolo^4 + (1 - F)·T_cielo^4
    """
    return (ground_view * t_ground**4 + (1.0 - ground_view) * t_sky**4) ** 0.25


def heat_load(crew: int, metabolic: float, p_service: float, dissipated: float) -> float:
    """Calore da smaltire in un caso [W] (MODELLI §9): Q = n·q_met + f_diss·P_servizio."""
    return crew * metabolic + dissipated * p_service


def radiator_area(heat: float, t_radiator: float, t_sink: float, emissivity: float) -> float:
    """Superficie radiante necessaria [m^2] (MODELLI §9).

        A = Q / [ε·σ·(T_rad^4 - T_pozzo^4)]

    Se T_rad ≤ T_pozzo si solleva ValueError.
    """
    if t_radiator <= t_sink:
        raise ValueError(f"radiatore: la temperatura del radiatore ({t_radiator:.0f} K) deve essere "
                         f"maggiore di quella di pozzo ({t_sink:.0f} K).")
    return heat / (emissivity * SIGMA_SB * (t_radiator**4 - t_sink**4))


def insulation_heat_loss(area: float, conductivity: float, thickness: float,
                         t_inside: float, t_outside: float) -> float:
    """Calore disperso attraverso l'isolamento della cabina [W], informativo (MODELLI §9).

        Q_disp = k·A·(T_int - T_est) / t_isol

    Con spessore nullo restituisce infinito.
    """
    if thickness <= 0.0:
        return float("inf")
    return conductivity * area * (t_inside - t_outside) / thickness
