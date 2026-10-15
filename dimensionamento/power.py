"""Potenza ed energia: carichi, generazione, accumulo, PMAD.

Parametri: Scheda dati, sezioni *Potenza ed energia* (carichi di servizio,
batterie, RPS, fotovoltaico, celle a combustibile) e *Vita a cicli delle
batterie*.
Requisiti: MR-07 (cicli), MR-08 (percorrenza con le risorse a bordo),
MR-12 (notte), MR-14 (emergenza), MR-15 (tempesta), MR-21 (+30% sui carichi
di servizio).

Struttura del modello
---------------------
1. Il gruppo descrive l'escursione con alcuni "sol tipo" (per esempio un sol
   di guida e un sol di EVA): per ciascuno, le ore passate in ogni modo
   operativo (guida, giorno, EVA, notte) e quante volte si ripete.
2. Ogni modo ha una potenza dei carichi di servizio, aumentata del margine di
   MR-21. La trazione si aggiunge durante la guida.
3. La generazione (RPS, fotovoltaico) è dimensionata in automatico oppure
   dichiarata dal gruppo; le celle a combustibile forniscono l'energia
   dell'intera escursione. L'ala fotovoltaica è ripiegata durante la guida e
   non produce (Scheda, Potenza ed energia: ipotesi dello studio GRC); il
   gruppo può dichiararla attiva in marcia, motivando la scelta e mettendo
   a budget la struttura di supporto necessaria.
4. La batteria è dimensionata simulando, fase per fase, il bilancio di
   energia dell'escursione: la capacità utile necessaria è il massimo
   "debito" di energia accumulato rispetto alla carica completa.

Architetture (``[architecture] power``):
    batterie            solo batteria, caricata alla base
    rps                 RPS + batteria
    fotovoltaico        ala fotovoltaica + batteria
    celle_combustibile  celle a combustibile + batteria per i picchi
    ibrido              RPS e fotovoltaico di potenza dichiarata + batteria
Altre combinazioni si ottengono modificando ``generation`` e documentando la
modifica in MODIFICHE.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .constants import HOUR

MODES = ("drive", "eva", "day", "night")      # ordine delle fasi all'interno di un sol
MODE_LABELS = {"drive": "guida", "eva": "EVA", "day": "sosta di giorno", "night": "notte"}


# ---------------------------------------------------------------------------
# Carichi di servizio e profilo dell'escursione
# ---------------------------------------------------------------------------
def service_loads(loads, margin: float) -> dict[str, float]:
    """Potenza dei carichi di servizio per modo, con il margine di MR-21 [W].

        P_modo = (1 + 0,30) · P_modo,stimata
    """
    return {mode: (1.0 + margin) * getattr(loads, mode) for mode in MODES}


def drive_time(sol_types) -> float:
    """Tempo totale di guida nell'escursione [s]: Σ n_s · t_guida,s."""
    return sum(s.count * s.drive for s in sol_types)


def sol_sequence(sol_types, order: list[str] | None = None) -> list:
    """Successione dei sol nell'escursione.

    Se il gruppo dichiara ``sequence`` in [operations], si usa quella. In caso
    contrario i sol tipo si alternano nell'ordine in cui sono scritti nel file
    (guida, EVA, guida, EVA, ...) finché ciascuno ha esaurito il proprio
    numero. La sequenza fa parte della ConOps: per esempio, raggruppare i sol
    di guida all'inizio cambia la capacità richiesta alla batteria.
    """
    if order:
        by_name = {s.name: s for s in sol_types}
        return [by_name[name] for name in order]
    remaining = [s.count for s in sol_types]
    sequence = []
    while any(remaining):
        for i, s in enumerate(sol_types):
            if remaining[i] > 0:
                sequence.append(s)
                remaining[i] -= 1
    return sequence


def service_energy(sol_types, p_service: dict[str, float]) -> dict[str, float]:
    """Energia dei carichi di servizio per modo, sull'intera escursione [J].

        E_modo = Σ_s n_s · t_modo,s · P_modo
    """
    return {mode: sum(s.count * getattr(s, mode) for s in sol_types) * p_service[mode]
            for mode in MODES}


def sol_energy(sol, p_service: dict[str, float], traction_rate: float) -> float:
    """Energia richiesta in un sol tipo [J]: Σ_modi P_modo·t_modo + P_trazione·t_guida."""
    return sum(p_service[m] * getattr(sol, m) for m in MODES) + traction_rate * sol.drive


# ---------------------------------------------------------------------------
# Generazione
# ---------------------------------------------------------------------------
def pv_share(t0: float, t1: float, light: float) -> float:
    """Quota dell'energia giornaliera dell'ala prodotta fra t0 e t1 dall'alba.

    Con produzione sinusoidale fra alba e tramonto (durata t_luce):
        q(t0, t1) = [cos(π·t0/t_luce) - cos(π·t1/t_luce)] / 2
    q(0, t_luce) = 1. Gli istanti oltre il tramonto sono riportati al tramonto.
    """
    if light <= 0:
        return 0.0
    t0, t1 = min(max(t0, 0.0), light), min(max(t1, 0.0), light)
    return (math.cos(math.pi * t0 / light) - math.cos(math.pi * t1 / light)) / 2.0


def pv_collectable(sol_type, sol: float, deployed_while_driving: bool) -> float:
    """Quota dell'energia giornaliera dell'ala raccolta in un sol tipo.

    La guida avviene all'inizio del giorno (fasi in ordine guida, EVA, sosta).
    Con l'ala ripiegata in marcia si perde la quota prodotta durante la guida:
        f_s = 1 - q(0, t_guida,s)
    """
    if deployed_while_driving:
        return 1.0
    return 1.0 - pv_share(0.0, sol_type.drive, sol - sol_type.night)


@dataclass
class Generation:
    rps: float = 0.0          # potenza elettrica dell'RPS [W]
    pv: float = 0.0           # potenza nominale dell'ala fotovoltaica [W]
    fc_energy: float = 0.0    # energia fornita dalle celle a combustibile [J]


def generation(arch: str, d, sol_types, p_service, traction_rate: float,
               e_total: float, duration: float, sol: float) -> Generation:
    """Potenza dei generatori secondo l'architettura scelta.

    RPS dimensionato in automatico (power_kw = 0): potenza media dell'escursione
        P_RPS = E_totale / t_escursione
    Fotovoltaico dimensionato in automatico (power_kw = 0): in ogni sol tipo
    l'ala produce l'energia del sol nelle ore in cui è aperta,
        P_FV = max_s E_s / (h_sole · f_s)
    con h_sole ore equivalenti di sole sull'intero periodo di luce e f_s la
    quota dell'energia giornaliera raccolta nel sol (``pv_collectable``).
    Celle a combustibile: forniscono l'energia dell'intera escursione.
    Ibrido: potenze di RPS e fotovoltaico dichiarate dal gruppo.
    """
    gen = Generation()
    if arch == "rps":
        gen.rps = d.rps.power if d.rps.power > 0 else e_total / duration
    elif arch == "fotovoltaico":
        if d.pv.power > 0:
            gen.pv = d.pv.power
        else:
            deployed = d.pv.deployed_while_driving
            sizes = []
            for s in sol_types:
                f = pv_collectable(s, sol, deployed)
                if f <= 1e-6:
                    raise ValueError(f"fotovoltaico: nel sol tipo '{s.name}' si guida per tutto il giorno "
                                     "e l'ala, ripiegata in marcia, non produce. Dichiarare la potenza "
                                     "dell'ala (power_kw) oppure rivedere la ConOps.")
                sizes.append(sol_energy(s, p_service, traction_rate) / (d.pv.sun_hours * f))
            gen.pv = max(sizes)
    elif arch == "celle_combustibile":
        gen.fc_energy = e_total
    elif arch == "ibrido":
        gen.rps, gen.pv = d.rps.power, d.pv.power
        if gen.rps == 0 and gen.pv == 0:
            raise ValueError("architettura ibrida: dichiarare la potenza di RPS e/o fotovoltaico "
                             "(power_kw > 0); la batteria copre il resto.")
    return gen


# ---------------------------------------------------------------------------
# Simulazione del bilancio di energia e dimensionamento della batteria
# ---------------------------------------------------------------------------
@dataclass
class EnergySimulation:
    max_deficit: float                     # energia utile richiesta alla batteria [J]
    cycles: list[float] = field(default_factory=list)   # profondità di ciascun ciclo [J]
    night_need: float = 0.0                # energia della notte più impegnativa [J]
    end_deficit: float = 0.0               # debito a fine escursione [J]


def simulate(sequence, p_service, traction_rate: float, gen: Generation,
             sol: float, sun_hours: float, fc_covers_loads: bool,
             pv_while_driving: bool = False) -> EnergySimulation:
    """Bilancio di energia fase per fase e capacità utile della batteria.

    Le fasi di luce si susseguono dall'alba nell'ordine guida, EVA, sosta di
    giorno; poi viene la notte. Per ogni fase, fra gli istanti t0 e t1 contati
    dall'alba:
        E_carico = (P_modo + P_trazione) · Δt          (trazione solo in guida)
        E_gen    = P_RPS·Δt + E_FV(t0, t1)
        debito   = max(0, debito + E_carico - E_gen)
    Con l'ala sempre aperta produrrebbe in un sol l'energia E_FV,sol = P_FV·h_sole,
    con un andamento sinusoidale fra alba e tramonto (durata t_luce = t_sol - t_notte):
        E_FV(t0, t1) = E_FV,sol · [cos(π·t0/t_luce) - cos(π·t1/t_luce)] / 2
    Durante la guida l'ala è ripiegata e E_FV = 0, salvo che il gruppo la
    dichiari attiva in marcia (``pv_while_driving``).
    Il debito è l'energia mancante rispetto alla batteria carica; non può
    essere negativo perché la batteria piena non accumula altro. La capacità
    utile richiesta è il debito massimo. Il bilancio è fatto sull'energia di
    ogni fase, non istante per istante.

    Un ciclo di carica-scarica si chiude quando il debito torna a zero; se a
    fine escursione il debito è positivo, la batteria si ricarica alla base e
    anche questo conta come un ciclo.

    Con le celle a combustibile i carichi medi sono coperti dalle celle e la
    batteria serve solo per i picchi di potenza.
    """
    deficit = peak = 0.0
    sim = EnergySimulation(0.0)
    for s in sequence:
        light = sol - s.night
        e_pv_sol = gen.pv * sun_hours
        t = 0.0                                          # tempo dall'alba [s]
        for mode in MODES:
            dt = getattr(s, mode)
            if dt <= 0:
                continue
            e_load = (p_service[mode] + (traction_rate if mode == "drive" else 0.0)) * dt
            e_pv = 0.0
            if mode != "night" and light > 0:
                if mode != "drive" or pv_while_driving:
                    e_pv = e_pv_sol * pv_share(t, t + dt, light)
                t += dt
            e_gen = gen.rps * dt + e_pv
            if fc_covers_loads:
                e_gen = e_load
            deficit = max(0.0, deficit + e_load - e_gen)
            if deficit > peak:
                peak = deficit
            sim.max_deficit = max(sim.max_deficit, deficit)
            if deficit == 0.0 and peak > 0.0:
                sim.cycles.append(peak)
                peak = 0.0
        sim.night_need = max(sim.night_need, p_service["night"] * s.night)
    sim.end_deficit = deficit
    if peak > 0.0:
        sim.cycles.append(peak)
    return sim


def battery_capacity(usable: float, dod: float, p_peak: float, p_continuous: float,
                     c_rate: float) -> tuple[float, str]:
    """Capacità nominale della batteria [J] e criterio che la determina.

        C_energia = E_utile / DOD
        C_potenza = (P_picco - P_continua) / c_max      (c_max in 1/h)

    P_continua è la potenza erogata con continuità dai generatori (RPS, celle a
    combustibile).
        C = max(C_energia, C_potenza)

    Attenzione alle unità: con C in Wh e c_max in 1/h la potenza massima è
    c_max·C in W. Qui C è in J, quindi C_potenza = ΔP·3600 / c_max.
    """
    c_energy = usable / dod
    c_power = max(0.0, p_peak - p_continuous) * HOUR / c_rate
    return (c_energy, "energia") if c_energy >= c_power else (c_power, "potenza di picco")


def allowed_cycles(dod: float, table_dod: list[float], table_cycles: list[int]) -> tuple[int, float]:
    """Cicli ammessi alla profondità di scarica ``dod`` (tabella della Scheda, MR-07).

    Si usa la riga con DOD immediatamente superiore o uguale (valore
    conservativo, senza interpolazione). Restituisce i cicli e la DOD della
    riga usata.
    """
    rows = sorted(zip(table_dod, table_cycles))
    for row_dod, cycles in rows:
        if dod <= row_dod + 1e-9:
            return cycles, row_dod
    return 0, rows[-1][0]


# ---------------------------------------------------------------------------
# Rientro in condizioni particolari (MR-14, MR-15)
# ---------------------------------------------------------------------------
@dataclass
class Return:
    duration: float          # durata del rientro, soste comprese [s]
    energy_need: float       # energia richiesta [J]
    energy_available: float  # energia disponibile: accumulo + generazione [J]
    traction: float          # quota di trazione [J]


def return_trip(distance: float, speed: float, drive_per_sol: float, sol: float,
                p_load: float, e_traction: float, gen: Generation, pv_factor: float,
                sun_hours: float, stored: float, light: float = 0.0,
                pv_while_driving: bool = False) -> Return:
    """Bilancio di energia di un rientro alla base [J].

        t_guida   = d / v
        n         = ceil(t_guida / t_guida,sol) - 1        (sol completi prima dell'ultimo)
        t_rientro = n·t_sol + (t_guida - n·t_guida,sol)   (si guida all'inizio di ogni sol)
        E_rich  = P_servizio·t_rientro + E_trazione(d)
        E_disp  = E_accumulata + P_RPS·t_rientro + E_FV
        E_FV    = f·P_FV·h_sole · n·[1 - q(0, t_guida,sol)]       (ala ripiegata in marcia)
        E_FV    = f·P_FV·h_sole · [n + q(0, t_guida - n·t_guida,sol)]   (ala attiva in marcia)

    Si guida dall'alba; nei sol completi l'ala produce nella parte di giorno
    che segue la guida, nell'ultimo sol il rientro termina all'arrivo. q è la
    quota sinusoidale dell'energia giornaliera (``pv_share``), t_luce la durata
    del periodo di luce.
    f è la frazione dell'irraggiamento disponibile (0,15 in tempesta, MR-15;
    1 negli altri casi); E_accumulata è l'energia utile a bordo all'inizio del
    rientro (batteria e reagenti), dichiarata dal gruppo come stato di carica.
    """
    t_drive = distance / speed
    n_full = max(0, math.ceil(t_drive / drive_per_sol - 1e-9) - 1)
    t = n_full * sol + (t_drive - n_full * drive_per_sol)
    need = p_load * t + e_traction
    e_pv_sol = pv_factor * gen.pv * sun_hours
    if pv_while_driving:
        e_pv = e_pv_sol * (n_full + pv_share(0.0, t_drive - n_full * drive_per_sol, light))
    else:
        e_pv = e_pv_sol * n_full * (1.0 - pv_share(0.0, drive_per_sol, light))
    available = stored + gen.rps * t + e_pv
    return Return(t, need, available, e_traction)
