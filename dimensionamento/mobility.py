"""Mobilità: potenza ed energia di trazione, massa dell'azionamento.

Parametri: Scheda dati, sezione *Mobilità*. Requisiti: MR-08, MR-10, MR-11.
Equazioni e ipotesi: MODELLI.md, §7.
"""
from __future__ import annotations

import math


def traction_power(mass: float, g: float, crr: float, slope: float,
                   speed: float, eta: float) -> float:
    """Potenza elettrica assorbita dalla trazione [W] (MODELLI §7).

        P = (C_rr·cosθ + sinθ)·m·g·v / η

    θ in rad, v in m/s.
    """
    return (crr * math.cos(slope) + math.sin(slope)) * mass * g * speed / eta


def peak_power(mass: float, g: float, crr: float, eta: float,
               v_flat: float, slope: float, v_slope: float) -> tuple[float, str]:
    """Potenza di picco della trazione [W] e caso che la determina (MODELLI §7).

        P_picco = max[P(0, v_piano), P(θ_max, v_pendenza)]
    """
    p_flat = traction_power(mass, g, crr, 0.0, v_flat, eta)
    p_slope = traction_power(mass, g, crr, slope, v_slope, eta)
    return (p_flat, "piano") if p_flat >= p_slope else (p_slope, "pendenza")


def traction_energy(mass: float, g: float, crr: float, eta: float,
                    distance: float, climb: float, margin: float) -> float:
    """Energia elettrica di trazione per un tragitto [J] (MODELLI §7).

        E = (1 + k_man)·(C_rr·m·g·d + m·g·Δh) / η
    """
    return (1.0 + margin) * (crr * mass * g * distance + mass * g * climb) / eta


def drive_mass(p_peak: float, specific_mass: float) -> float:
    """Massa di motori, riduttori e controllori [kg] (MODELLI §7): m_az = k_az·P_picco, con k_az in kg/W."""
    return specific_mass * p_peak


def wheel_torque(mass: float, g: float, crr: float, slope: float,
                 wheel_diameter: float, driven_wheels: int) -> float:
    """Coppia per ruota motrice in pendenza [N·m], informativa (MODELLI §7).

        M_r = (C_rr·cosθ + sinθ)·m·g·R / n,   R = D_ruota / 2
    """
    return (crr * math.cos(slope) + math.sin(slope)) * mass * g * wheel_diameter / 2.0 / driven_wheels


def max_speed(p_available: float, mass: float, g: float, crr: float,
              slope: float, eta: float) -> float:
    """Velocità raggiungibile con la potenza di trazione disponibile [m/s] (MODELLI §7).

        v = P·η / [(C_rr·cosθ + sinθ)·m·g]
    """
    return p_available * eta / ((crr * math.cos(slope) + math.sin(slope)) * mass * g)


def tipping_angle(track: float, cg_height: float) -> float:
    """Angolo di ribaltamento laterale statico [rad] (MODELLI §7): tanφ = (b/2) / h_G."""
    return math.atan2(track / 2.0, cg_height)
