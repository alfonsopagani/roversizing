"""Studi di sensitività: variazione di un parametro alla volta.

Si ripete il dimensionamento completo, ciclo di massa compreso, per una serie
di valori di una sola chiave del file di input (per esempio ``mobility.crr``
fra 0,1 e 0,6), lasciando invariato tutto il resto: a ogni valore il rover è
riprogettato. Serve per i trade-off.

Con ``frozen=True`` (opzione ``--congelato``) il rover resta quello
dimensionato con il file di input e si verifica soltanto come si comporta al
variare della chiave (verifica fuori progetto, ``sizing.off_design``): è la
verifica a C_rr = 0,6 richiesta dal Design brief, e mostra quale requisito
viene violato per primo.

In entrambi i casi la tabella riporta i requisiti NON SODDISFATTI.

I valori si danno nelle unità del file di input (per esempio kW per
``loads.day_kw``).
"""
from __future__ import annotations

import copy
from pathlib import Path

from .constants import KWH
from .inputs import SCHEMA, InputError, apply_override, validate
from .requirements import KO, check_all, n
from .mobility import max_speed
from .report import GRID, INK, INK2, SERIES, Table, _pyplot
from .sizing import SizingError, off_design, run


def linspace(start: float, stop: float, count: int) -> list[float]:
    if count < 2:
        return [start]
    return [start + (stop - start) * i / (count - 1) for i in range(count)]


def failed_requirements(res) -> str:
    """Requisiti con almeno una verifica NON SODDISFATTA, nell'ordine del report."""
    out = []
    for ch in check_all(res):
        if ch.status == KO and ch.mr not in out:
            out.append(ch.mr)
    return ", ".join(out) if out else "nessuno"


def sweep(common, raw: dict, file: str, key: str, values: list[float],
          frozen: bool = False) -> list[dict]:
    """Esegue il dimensionamento (o, con ``frozen``, la verifica fuori progetto)
    per ogni valore della chiave ``sezione.chiave``."""
    section, name = key.split(".", 1) if "." in key else (key, "")
    spec = SCHEMA.get(section, {}).get(name)
    nominal = validate(copy.deepcopy(raw), file) if frozen else None
    rows = []
    for value in values:
        if spec is not None and spec.kind == "int":
            value = int(round(value))
        data = copy.deepcopy(raw)
        row = {"value": value, "converged": False}
        try:
            apply_override(data, f"{key}={value!r}")
            if frozen:
                res = off_design(common, nominal, validate(data, file))[1]
            else:
                res = run(common, validate(data, file))
        except (InputError, SizingError) as exc:
            row["note"] = str(exc)
            rows.append(row)
            continue
        if not res.loop.converged:
            row["gain"] = res.loop.gain
            rows.append(row)
            continue
        dep, b = res.dep, res.budget
        mass, env, mob = res.loop.mass, common.environment, res.design.mobility
        rows.append({
            "value": value, "converged": True, "total": b.total,
            "reserve": common.mission.mass_limit - b.total,
            "p_peak": dep.p_peak, "e_service": sum(res.fixed.e_service.values()),
            "e_traction": dep.e_traction,
            "power_mass": dep.battery_mass + dep.rps_mass + dep.pv_mass + dep.fc_mass,
            "battery": dep.battery_capacity, "gain": res.loop.gain,
            "v_flat": max_speed(dep.p_peak, mass, env.g, mob.crr, 0.0, mob.eta),
            "v_slope": max_speed(dep.p_peak, mass, env.g, mob.crr, common.mission.slope, mob.eta),
            "deficit": dep.sim.max_deficit, "usable": dep.battery_capacity * res.design.battery.dod_max,
            "failed": failed_requirements(res),
        })
    return rows


def sweep_table(key: str, rows: list[dict], frozen: bool = False) -> Table:
    if frozen:
        headers = [key, "Velocità in piano [km/h]", "Velocità in pendenza [km/h]", "E trazione [kWh]",
                   "Debito massimo [kWh]", "Accumulo utile [kWh]", "Requisiti non soddisfatti"]
    else:
        headers = [key, "Massa totale [kg]", "Riserva MR-20 [kg]", "Picco trazione [kW]",
                   "E servizio [kWh]", "E trazione [kWh]", "Sistema di potenza [kg]",
                   "Batteria [kWh]", "k = dF/dm", "Requisiti non soddisfatti"]
    out = []
    for r in rows:
        nd = 0 if isinstance(r["value"], int) else 3
        if r["converged"] and frozen:
            out.append([n(r["value"], nd), n(r["v_flat"] * 3.6, 1), n(r["v_slope"] * 3.6, 1),
                        n(r["e_traction"] / KWH), n(r["deficit"] / KWH), n(r["usable"] / KWH), r["failed"]])
        elif r["converged"]:
            out.append([n(r["value"], nd), n(r["total"]), n(r["reserve"]), n(r["p_peak"] / 1e3, 1),
                        n(r["e_service"] / KWH), n(r["e_traction"] / KWH), n(r["power_mass"]),
                        n(r["battery"] / KWH), n(r["gain"], 3), r["failed"]])
        else:
            why = r.get("note") or (f"non converge (k = {n(r['gain'], 3)})" if "gain" in r else "non converge")
            out.append([n(r["value"], nd), why] + [""] * (len(headers) - 2))
    title = (f"Verifica fuori progetto al variare di {key} (rover congelato)" if frozen
             else f"Sensitività a {key}")
    return (title, headers, out)


def plot_frozen(key: str, rows: list[dict], mission, folder: Path) -> list[Path]:
    """Verifica fuori progetto: velocità con i limiti di MR-10 e MR-11; debito di
    energia dell'escursione confrontato con l'accumulo utile."""
    plt = _pyplot()
    ok = [r for r in rows if r["converged"]]
    if not ok:
        return []
    x = [r["value"] for r in ok]
    name = key.replace(".", "_")
    paths = []

    fig, ax = plt.subplots(figsize=(7, 3.8))
    for label, field, req, color in (("in piano", "v_flat", mission.v_flat, SERIES[0]),
                                     ("in pendenza", "v_slope", mission.v_slope, SERIES[1])):
        y = [r[field] * 3.6 for r in ok]
        ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=5)
        ax.text(x[-1], y[-1], f"  {label}", va="center", color=INK2, fontsize=9)
        ax.axhline(req * 3.6, color=color, linewidth=1, linestyle="--")
        ax.text(x[0], req * 3.6, " MR-10" if field == "v_flat" else " MR-11", va="bottom",
                color=INK2, fontsize=9)
    ax.set_title(f"Velocità con la potenza installata al variare di {key}", color=INK, fontsize=11, loc="left")
    ax.set_xlabel(key)
    ax.set_ylabel("Velocità [km/h]")
    ax.grid(color=GRID, linewidth=0.8)
    fig.tight_layout()
    path = folder / f"fuori_progetto_{name}_velocita.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.plot(x, [r["deficit"] / KWH for r in ok], color=SERIES[0], linewidth=2, marker="o", markersize=5)
    ax.axhline(ok[0]["usable"] / KWH, color=INK2, linewidth=1, linestyle="--")
    ax.text(x[0], ok[0]["usable"] / KWH, " accumulo utile installato", va="bottom", color=INK2, fontsize=9)
    ax.set_title(f"Debito massimo di energia al variare di {key}", color=INK, fontsize=11, loc="left")
    ax.set_xlabel(key)
    ax.set_ylabel("Energia [kWh]")
    ax.grid(color=GRID, linewidth=0.8)
    fig.tight_layout()
    path = folder / f"fuori_progetto_{name}_energia.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)
    return paths


def plot_sweep(key: str, rows: list[dict], limit: float, folder: Path) -> list[Path]:
    """Due grafici: massa totale con il limite di MR-20; energia di servizio e di trazione."""
    plt = _pyplot()
    ok = [r for r in rows if r["converged"]]
    paths = []
    if not ok:
        return paths
    x = [r["value"] for r in ok]
    name = key.replace(".", "_")

    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.plot(x, [r["total"] for r in ok], color=SERIES[0], linewidth=2, marker="o", markersize=5)
    ax.axhline(limit, color=INK2, linewidth=1, linestyle="--")
    ax.text(x[0], limit, " limite MR-20", va="bottom", color=INK2, fontsize=9)
    failed = [r["value"] for r in rows if not r["converged"]]
    title = f"Massa totale al variare di {key}"
    if failed:
        title += f" (non converge per {', '.join(n(v, 3) for v in failed)})"
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.set_xlabel(key)
    ax.set_ylabel("Massa a pieno carico [kg]")
    ax.grid(color=GRID, linewidth=0.8)
    fig.tight_layout()
    path = folder / f"sensitivita_{name}_massa.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(7, 3.8))
    series = (("servizio", "e_service", SERIES[0]), ("trazione", "e_traction", SERIES[1]))
    for label, field, color in series:
        y = [r[field] / KWH for r in ok]
        ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=5, label=label)
        ax.text(x[-1], y[-1], f"  {label}", va="center", color=INK2, fontsize=9)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    ax.set_title(f"Energia per escursione al variare di {key}", color=INK, fontsize=11, loc="left")
    ax.set_xlabel(key)
    ax.set_ylabel("Energia [kWh]")
    ax.grid(color=GRID, linewidth=0.8)
    fig.tight_layout()
    path = folder / f"sensitivita_{name}_energia.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)
    return paths
