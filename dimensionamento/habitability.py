"""Abitabilità: volume pressurizzato e geometria della cabina.

Parametri: Scheda dati, sezione *Abitabilità e volumi*; volumi del cibo nella
sezione *Equipaggio ed ECLSS*.

La cabina è un cilindro di diametro D con due fondi. Sono previsti fondi
semisferici e fondi ellittici (semiellissoidi di rivoluzione con profondità
h = k·R). Altre forme, per esempio una cabina a pareti piane, si aggiungono
scrivendo una funzione con la stessa interfaccia di ``cabin_geometry`` e
documentando la modifica in MODIFICHE.md, oppure dichiarando volume e
superficie ricavati dal proprio modello CAD/FEM (``apply_cad``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def pressurized_volume(nhv: float, nhv_fraction: float, stowage: float,
                       other: float = 0.0) -> float:
    """Volume pressurizzato richiesto [m^3].

        V_p = NHV / f_NHV + V_stivaggio + V_altro

    NHV è il volume abitabile netto, f_NHV il rapporto fra volume abitabile
    netto e volume pressurizzato dei prototipi (Scheda, Abitabilità e volumi: 79-82%),
    V_stivaggio la capacità di stivaggio interna, V_altro eventuali volumi
    pressurizzati aggiuntivi (per esempio un airlock interno alla cabina).
    """
    return nhv / nhv_fraction + stowage + other


def head_volume_area(radius: float, ratio: float, heads: str) -> tuple[float, float]:
    """Volume [m^3] e superficie [m^2] dei DUE fondi della cabina.

    Fondi semisferici: V = 4/3·π·R^3, A = 4·π·R^2.
    Fondi ellittici con profondità h = k·R (k < 1): due semiellissoidi oblati,
        V = 4/3·π·R^2·h
        A = 2·π·R^2 · [1 + (1 - e^2)/e · artanh(e)],  e^2 = 1 - (h/R)^2
    Con k = 1 si ritrova la sfera.
    """
    if heads == "semisferici" or ratio >= 0.999:
        return 4.0 / 3.0 * math.pi * radius**3, 4.0 * math.pi * radius**2
    h = ratio * radius
    e = math.sqrt(1.0 - ratio**2)
    volume = 4.0 / 3.0 * math.pi * radius**2 * h
    area = 2.0 * math.pi * radius**2 * (1.0 + (1.0 - e**2) / e * math.atanh(e))
    return volume, area


@dataclass
class CabinGeometry:
    diameter: float          # m
    length: float            # lunghezza totale, fondi compresi [m]
    cylinder_length: float   # lunghezza del tratto cilindrico [m]
    volume: float            # volume interno [m^3]
    area: float              # superficie del guscio [m^2]
    source: str = "cilindro" # origine di volume e superficie: "cilindro" oppure "CAD"


def cabin_geometry(volume_required: float, diameter: float, heads: str,
                   head_ratio: float = 1.0, length: float = 0.0) -> CabinGeometry:
    """Geometria della cabina cilindrica con due fondi.

    Se ``length`` = 0 la lunghezza del tratto cilindrico si ricava dal volume
    richiesto:
        L_c = (V_p - V_fondi) / (π·R^2)
    altrimenti si usa la lunghezza totale dichiarata dal gruppo e il volume
    risultante va confrontato con quello richiesto (budget di volume).

    Superficie del guscio: A = π·D·L_c + A_fondi.
    """
    radius = diameter / 2.0
    v_heads, a_heads = head_volume_area(radius, head_ratio, heads)
    depth = radius if heads == "semisferici" else head_ratio * radius
    if length > 0.0:
        l_cyl = length - 2.0 * depth
        if l_cyl < 0.0:
            raise ValueError(f"cabina: la lunghezza dichiarata ({length:.2f} m) è minore "
                             f"della profondità dei due fondi ({2 * depth:.2f} m).")
    else:
        l_cyl = (volume_required - v_heads) / (math.pi * radius**2)
        if l_cyl < 0.0:
            raise ValueError(f"cabina: con D = {diameter:.2f} m i soli fondi hanno un volume "
                             f"({v_heads:.1f} m^3) maggiore di quello richiesto "
                             f"({volume_required:.1f} m^3). Ridurre il diametro.")
    volume = math.pi * radius**2 * l_cyl + v_heads
    area = math.pi * diameter * l_cyl + a_heads
    return CabinGeometry(diameter, l_cyl + 2.0 * depth, l_cyl, volume, area)


def apply_cad(geom: CabinGeometry, cad_volume: float, cad_area: float) -> CabinGeometry:
    """Volume e superficie della cabina dal modello CAD/FEM del gruppo.

    Quando la cabina reale non è un cilindro con fondi (pareti piane, sezione
    non circolare, più moduli), il gruppo può dichiarare volume interno e
    superficie del guscio ricavati dal proprio modello. Ciascun valore, se
    maggiore di zero, sostituisce quello del cilindro:
        V = V_CAD,   A = A_CAD
    Il volume entra nella verifica del volume pressurizzato; la superficie
    nelle masse di interni e isolamento (e del guscio, finché manca la massa
    del FEM) e nella dispersione termica.
    Diametro e lunghezza restano quelli del cilindro dichiarato.
    """
    if cad_volume <= 0.0 and cad_area <= 0.0:
        return geom
    parts = []
    if cad_volume > 0.0:
        parts.append("volume")
    if cad_area > 0.0:
        parts.append("superficie")
    return CabinGeometry(geom.diameter, geom.length, geom.cylinder_length,
                         cad_volume if cad_volume > 0.0 else geom.volume,
                         cad_area if cad_area > 0.0 else geom.area,
                         "CAD (" + " e ".join(parts) + ")")


def stowage_required(food: float, water: float, water_inside: bool,
                     items: float) -> float:
    """Volume da stivare in cabina [m^3].

        V = V_cibo + V_acqua (se i serbatoi sono interni) + V_altre voci

    V_cibo dal volume per persona-giorno del cibo confezionato (Scheda, Equipaggio ed ECLSS);
    V_acqua = massa / 1000 kg/m^3; le altre voci (kit medici, ricambi...) sono
    dichiarate dal gruppo.
    """
    return food + (water if water_inside else 0.0) + items
