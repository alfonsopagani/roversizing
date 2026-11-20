"""Uscite: tabelle a terminale, file CSV e Markdown, grafici facoltativi.

Tutte le tabelle sono costruite una volta sola da ``build_tables`` come
(titolo, intestazioni, righe) e poi stampate o salvate nei diversi formati.
"""
from __future__ import annotations

import csv
import datetime
import math
import re
from pathlib import Path

from . import __version__, mobility
from .constants import DAY, HOUR, KWH
from .power import DRIVE_MODES, MODE_LABELS, drive_time, modes_used
from .requirements import check_all, n

Table = tuple[str, list[str], list[list[str]]]
NUMBER = re.compile(r"-?[\d.]+(,\d+)?")


# ---------------------------------------------------------------------------
# Costruzione delle tabelle
# ---------------------------------------------------------------------------
# Testi del report per i valori interni (le chiavi del file di input non cambiano)
SUBSYSTEM_LABELS = {"mobilita": "mobilità", "abitabilita": "abitabilità", "eclss": "ECLSS", "eva": "EVA"}
ARCHITECTURE_LABELS = {"rps": "RPS", "celle_combustibile": "celle a combustibile",
                       "ibrido": "ibrido (RPS e fotovoltaico)"}


def subsystem_label(key: str) -> str:
    return SUBSYSTEM_LABELS.get(key, key)


def architecture_label(key: str) -> str:
    return ARCHITECTURE_LABELS.get(key, key)


def header_lines(d, c, input_name: str) -> list[str]:
    """Intestazione comune a report, scansioni e verifica fuori progetto (d: progetto, c: dati comuni)."""
    g = d.group
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    return [f"Missione: {g.name} - versione {g.version}",
            f"File di input: {input_name}",
            "Studenti: " + "; ".join(f"{s.name} ({s.id})" + (f", {s.role}" if s.role else "")
                                     for s in g.students),
            f"Architettura di potenza: {architecture_label(d.architecture.power)}",
            "Dati comuni (common.toml): " + ("versione del corso" if c.unchanged
                                             else f"MODIFICATI rispetto alla versione del corso "
                                                  f"(impronta {c.fingerprint})"),
            f"Strumento: roversizing {__version__}, eseguito il {now}"]


def markdown_header(title: str, lines: list[str]) -> str:
    """Titolo e intestazione in elenco, per i file .md."""
    return "\n".join([f"# {title}", ""] + [f"- {line}" for line in lines] + [""])


def mass_tables(res) -> list[Table]:
    b, limit = res.budget, res.common.mission.mass_limit
    rows = []
    for it in b.items:
        rows.append([it.name, subsystem_label(it.subsystem), (it.maturity or "fissa").replace("_", " "), n(it.base),
                     n(it.mga * 100) if not it.fixed else "-", n(it.predicted), it.source])
    summary = [
        ["Massa di base delle voci con margine", n(b.base_dry)],
        ["MGA (somma per voce)", n(b.mga)],
        ["Massa prevista delle voci con margine", n(b.predicted_dry)],
        [f"Margine di sistema ({n(b.system_margin_fraction * 100)}% della base)", n(b.system_margin)],
        ["Masse fisse (carico utile, equipaggio, tute, consumabili)", n(b.fixed)],
        ["Massa totale a pieno carico", n(b.total)],
        ["Limite MR-20", n(limit)],
        ["Riserva rispetto a MR-20", n(limit - b.total)],
    ]
    total = b.total
    subs = [[subsystem_label(k), n(v), n(v / total * 100, 1)]
            for k, v in sorted(b.by_subsystem.items(), key=lambda kv: -kv[1])]
    subs.append(["margine di sistema", n(b.system_margin), n(b.system_margin / total * 100, 1)])
    return [("Budget di massa per voce",
             ["Voce", "Sottosistema", "Maturità", "Base [kg]", "MGA [%]", "Prevista [kg]", "Origine"], rows),
            ("Budget di massa: totali", ["Grandezza", "Massa [kg]"], summary),
            ("Massa prevista per sottosistema", ["Sottosistema", "Massa [kg]", "Quota [%]"], subs)]


def power_tables(res) -> list[Table]:
    d, fx, dep, c = res.design, res.fixed, res.dep, res.common
    margin = c.margins.power
    rows = []
    for mode in modes_used(d.operations.sol_types):
        est = getattr(d.loads, mode)
        trac = dep.traction_rate if mode in DRIVE_MODES else 0.0
        rows.append([MODE_LABELS[mode], n(est / 1e3, 2), n(fx.p_service[mode] / 1e3, 2),
                     n(trac / 1e3, 2), n((fx.p_service[mode] + trac) / 1e3, 2)])
    rows.append(["picco di trazione (" + dep.peak_case + ")", "-", "-", n(dep.p_peak / 1e3, 2),
                 n(dep.p_peak_electric / 1e3, 2)])
    p_table = ("Budget di potenza per modo operativo",
               ["Modo", "Servizio stimato [kW]", f"Servizio +{n(margin * 100)}% [kW]",
                "Trazione [kW]", "Totale [kW]"], rows)

    e_serv = sum(fx.e_service.values())
    e_tot = e_serv + dep.e_traction
    e_rows = [[f"servizio - {MODE_LABELS[m]}", n(fx.e_service[m] / KWH, 1), n(fx.e_service[m] / e_tot * 100, 1)]
              for m in modes_used(d.operations.sol_types)]
    e_rows += [["servizio - totale", n(e_serv / KWH, 1), n(e_serv / e_tot * 100, 1)],
               ["trazione", n(dep.e_traction / KWH, 1), n(dep.e_traction / e_tot * 100, 1)],
               ["totale escursione", n(e_tot / KWH, 1), "100,0"]]
    e_table = ("Budget di energia per escursione", ["Voce", "Energia [kWh]", "Quota [%]"], e_rows)

    gen, sim = dep.gen, dep.sim
    cap = dep.battery_capacity
    s_rows = [["Architettura", architecture_label(d.architecture.power), ""]]
    if gen.rps > 0:
        s_rows.append(["RPS: potenza elettrica", n(gen.rps / 1e3, 2), "kW"])
        s_rows.append(["RPS: massa", n(dep.rps_mass), "kg"])
    if gen.pv > 0:
        s_rows.append(["Fotovoltaico: potenza nominale", n(gen.pv / 1e3, 2), "kW"])
        s_rows.append(["Fotovoltaico: superficie dell'ala", n(dep.pv_area, 1), "m²"])
        s_rows.append(["Fotovoltaico: massa", n(dep.pv_mass), "kg"])
        s_rows.append(["Fotovoltaico: ala durante la guida",
                       "aperta (scelta del gruppo)" if d.pv.deployed_while_driving else "ripiegata", ""])
    if gen.fc_energy > 0:
        s_rows.append(["Celle a combustibile: energia fornita", n(gen.fc_energy / KWH), "kWh"])
        s_rows.append(["Celle a combustibile: massa", n(dep.fc_mass), "kg"])
    s_rows += [["Batteria: energia utile richiesta", n(sim.max_deficit / KWH, 1), "kWh"],
               ["Batteria: capacità nominale", n(cap / KWH, 1), "kWh"],
               ["Batteria: criterio di dimensionamento", dep.battery_criterion, ""],
               ["Batteria: massa", n(dep.battery_mass), "kg"],
               ["Batteria: cicli per escursione", str(len(sim.cycles)), ""],
               ["Batteria: DOD del ciclo più profondo",
                n(max(sim.cycles) / cap * 100 if sim.cycles else 0.0), "%"],
               ["Potenza elettrica di picco (trazione + servizio in guida)", n(dep.p_peak_electric / 1e3, 2), "kW"]]
    return [p_table, e_table, ("Sistema di potenza", ["Grandezza", "Valore", "Unità"], s_rows)]


def volume_table(res) -> Table:
    d, fx = res.design, res.fixed
    h, g = d.habitability, fx.geom
    rows = [["Volume abitabile netto (NHV)", n(h.nhv, 2), "m³"],
            ["Rapporto NHV / volume pressurizzato", n(h.nhv_fraction, 2), "-"],
            ["Stivaggio interno disponibile", n(h.stowage, 2), "m³"],
            ["Altri volumi pressurizzati", n(h.other_pressurized, 2), "m³"],
            ["Volume pressurizzato richiesto", n(fx.v_required, 2), "m³"],
            ["Volume della cabina" + (" (CAD)" if d.cabin.cad_volume > 0 else ""), n(g.volume, 2), "m³"],
            ["Diametro della cabina" + (" (cilindro dichiarato)" if g.source != "cilindro" else ""),
             n(g.diameter, 2), "m"],
            ["Lunghezza della cabina, fondi compresi" + (" (cilindro dichiarato)" if g.source != "cilindro" else ""),
             n(g.length, 2), "m"],
            ["Superficie del guscio" + (" (CAD)" if d.cabin.cad_area > 0 else ""), n(g.area, 1), "m²"],
            ["Volume da stivare (cibo, acqua interna, altre voci)", n(fx.v_stowage_need, 2), "m³"]]
    return ("Budget di volume", ["Grandezza", "Valore", "Unità"], rows)


def performance_table(res) -> Table:
    c, d, dep, fx = res.common, res.design, res.dep, res.fixed
    m, env, mob = c.mission, c.environment, d.mobility
    mass = res.loop.mass
    v_flat = mobility.max_speed(dep.p_peak, mass, env.g, mob.crr, 0.0, mob.eta)
    v_slope = mobility.max_speed(dep.p_peak, mass, env.g, mob.crr, m.slope, mob.eta)
    torque = mobility.wheel_torque(mass, env.g, mob.crr, m.slope, mob.wheel_diameter, mob.driven_wheels)
    usable = dep.battery_capacity * d.battery.dod_max
    e_per_km = dep.e_traction / (dep.distance / 1e3)
    extra_km = max(0.0, usable - dep.sim.max_deficit) / e_per_km
    person_days = fx.cons.person_time / DAY
    rows = [["Velocità massima in piano (potenza di picco)", n(v_flat * 3.6, 1), "km/h"],
            [f"Velocità massima sulla pendenza di {n(math.degrees(m.slope))}°", n(v_slope * 3.6, 1), "km/h"],
            ["Coppia per ruota motrice in pendenza, M_r", n(torque), "N·m"],
            ["Percorrenza pianificata (ore di guida × velocità media)",
             n(drive_time(d.operations.sol_types) * d.operations.v_mean / 1e3), "km"],
            ["Energia di trazione per km", n(e_per_km / KWH, 2), "kWh/km"],
            ["Percorrenza aggiuntiva con l'energia utile residua", n(extra_km), "km"],
            ["Consumabili a bordo (escursione, emergenza e riserva)", n(person_days, 1), "persone-giorno"],
            ["Rientro in emergenza (MR-14): durata", n(res.emergency.duration / HOUR, 1), "h"],
            ["Rientro in tempesta (MR-15): durata", n(res.storm.duration / HOUR, 1), "h"]]
    if res.cg:
        rows.append(["Baricentro x, y, z", ", ".join(n(v, 2) for v in res.cg), "m"])
    # Se mancano alcune posizioni si elencano le voci senza posizione; se non ne è
    # stata data nessuna (layout non ancora definito) la riga si omette.
    elif res.cg_missing and len(res.cg_missing) < sum(1 for it in res.budget.items if it.predicted > 0):
        rows.append(["Baricentro x, y, z: non calcolato, mancano le posizioni di",
                     "; ".join(res.cg_missing), ""])
    return ("Prestazioni", ["Grandezza", "Valore", "Unità"], rows)


def subsystem_tables(res) -> list[Table]:
    fx, d = res.fixed, res.design
    cons = fx.cons
    e_rows = [["O₂ metabolico", n(cons.o2_metabolic, 1)], ["O₂ delle EVA", n(cons.o2_eva, 1)],
              ["Miscela persa dalla cabina", n(cons.gas_leak, 1)],
              ["Miscela persa nei cicli di uscita", n(cons.gas_access, 1)],
              ["O₂ totale", n(cons.o2, 1)], ["N₂ totale", n(cons.n2, 1)],
              ["Acqua", n(cons.water, 1)], ["Cibo", n(cons.food, 1)],
              ["Assorbitore di CO₂", n(cons.sorbent, 1)], ["Serbatoi", n(fx.tanks, 1)]]
    sh = fx.shelter
    r_rows = [["Schermo richiesto", n(sh.required), "kg"], ["Coperto dall'acqua", n(sh.from_water), "kg"],
              ["Coperto da altri materiali", n(sh.from_other), "kg"], ["Massa aggiuntiva", n(sh.added), "kg"],
              ["Dose efficace dall'evento solare, nel riparo", n(fx.spe_dose_shelter), "mSv"],
              ["Dose efficace dall'evento solare, senza riparo", n(fx.spe_dose_unshielded), "mSv"],
              ["Dose efficace da raggi cosmici in un'escursione", n(fx.gcr_dose, 1), "mSv"]]
    t_rows = [["Calore da smaltire (caso caldo, " + fx.heat_case + ")", n(fx.heat), "W"],
              ["Temperatura di pozzo", n(fx.t_sink, 1), "K"],
              ["Temperatura del radiatore", n(d.thermal.radiator_temperature, 1), "K"],
              ["Superficie del radiatore", n(fx.radiator_area, 1), "m²"],
              ["Dispersione dell'isolamento (caso freddo, limite superiore)", n(fx.heat_loss), "W"]]
    return [("ECLSS: consumabili e serbatoi per escursione", ["Voce", "Massa [kg]"], e_rows),
            ("Riparo e dosi di radiazione (MR-16)", ["Grandezza", "Valore", "Unità"], r_rows),
            ("Controllo termico", ["Grandezza", "Valore", "Unità"], t_rows)]


def loop_table(res) -> Table:
    L = res.loop
    rows = [["Iterazioni", str(L.iterations)],
            ["Somma delle frazioni k = dF/dm", n(L.gain, 3)],
            ["Fattore di crescita 1/(1 - k)", n(1 / (1 - L.gain), 2) if L.gain < 1 else "-"]]
    rows += [[f"  dF/dm: {name}", n(v, 3)] for name, v in sorted(L.contributions.items(), key=lambda kv: -kv[1])]
    return ("Ciclo di massa", ["Grandezza", "Valore"], rows)


def requirements_table(res) -> Table:
    rows = [[ch.mr, ch.description, ch.required, ch.obtained, ch.status] for ch in check_all(res)]
    return ("Verifica dei requisiti", ["Req.", "Verifica", "Richiesto", "Ottenuto", "Esito"], rows)


def fem_table(res) -> Table:
    rows = [[it.name, n(it.predicted, 1)] + ([n(v, 3) for v in it.position] if it.position else ["", "", ""])
            for it in res.budget.items]
    rows.append(["Margine di sistema (non localizzato)", n(res.budget.system_margin, 1), "", "", ""])
    return ("Masse per il modello FEM (masse previste, a pieno carico)",
            ["Voce", "Massa [kg]", "x [m]", "y [m]", "z [m]"], rows)


def build_tables(res) -> list[Table]:
    """Tutte le tabelle del report, nell'ordine di stampa."""
    return (mass_tables(res) + power_tables(res) + [volume_table(res), performance_table(res)]
            + subsystem_tables(res) + [loop_table(res), requirements_table(res), fem_table(res)])


# ---------------------------------------------------------------------------
# Formati di uscita
# ---------------------------------------------------------------------------
def format_text(table: Table) -> str:
    """Tabella a larghezza fissa per il terminale."""
    title, headers, rows = table
    widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    widths = [min(w, 60) for w in widths]

    def line(cells):
        out = []
        for i, cell in enumerate(cells):
            text = str(cell)[: widths[i]]
            numeric = NUMBER.fullmatch(text) is not None
            out.append(text.rjust(widths[i]) if numeric and i > 0 else text.ljust(widths[i]))
        return "  ".join(out).rstrip()

    sep = "  ".join("-" * w for w in widths)
    return "\n".join([title, "=" * len(title), line(headers), sep] + [line(r) for r in rows])


def format_markdown(table: Table) -> str:
    title, headers, rows = table
    esc = lambda s: str(s).replace("|", "\\|")                     # noqa: E731
    lines = [f"### {title}", "", "| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def print_report(res, input_name: str) -> None:
    print("\n".join(header_lines(res.design, res.common, input_name)))
    print()
    if not res.loop.converged:
        print(res.loop.message)
        return
    for table in build_tables(res):
        print(format_text(table))
        print()


def slug(title: str) -> str:
    keep = "".join(ch.lower() if ch.isalnum() else "_" for ch in title)
    return "_".join(p for p in keep.split("_") if p)[:60]


def write_outputs(res, input_name: str, folder: Path) -> list[Path]:
    """Scrive report.md (tutte le tabelle) e un CSV per tabella nella cartella indicata."""
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    md = [markdown_header("Report di dimensionamento", header_lines(res.design, res.common, input_name))]
    if not res.loop.converged:
        md += ["```", res.loop.message, "```"]
    else:
        for table in build_tables(res):
            md += [format_markdown(table), ""]
            path = folder / f"{slug(table[0])}.csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(table[1])
                writer.writerows(table[2])
            written.append(path)
    path = folder / "report.md"
    path.write_text("\n".join(md), encoding="utf-8")
    written.insert(0, path)
    return written


# ---------------------------------------------------------------------------
# Grafici (facoltativi, richiedono matplotlib)
# ---------------------------------------------------------------------------
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")
MARGIN = "#a3a19b"                     # barre dei margini


def _pyplot():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        raise SystemExit("I grafici richiedono matplotlib:  python -m pip install matplotlib") from None
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                         "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": SURFACE,
                         "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE})
    return plt


def plot_mass(res, folder: Path) -> Path:
    """Massa prevista per sottosistema (barre orizzontali) con il margine di sistema."""
    plt = _pyplot()
    b = res.budget
    data = [(subsystem_label(k), v) for k, v in sorted(b.by_subsystem.items(), key=lambda kv: kv[1])]
    data.insert(0, ("margine di sistema", b.system_margin))
    labels, values = zip(*data)
    colors = [MARGIN] + [SERIES[0]] * (len(labels) - 1)          # il margine non è un sottosistema
    fig, ax = plt.subplots(figsize=(7, 0.4 * len(labels) + 1.2))
    ax.barh(labels, values, color=colors, height=0.6)
    for y, v in enumerate(values):
        ax.text(v, y, f" {n(v)}", va="center", color=INK2, fontsize=9)
    ax.set_xlabel("Massa [kg]")
    ax.set_title(f"Massa a pieno carico: {n(b.total)} kg (limite MR-20: "
                 f"{n(res.common.mission.mass_limit)} kg)", color=INK, fontsize=11, loc="left")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    path = folder / "massa_per_sottosistema.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_energy(res, folder: Path) -> Path:
    """Energia per escursione: carichi di servizio per modo (blu) e trazione (arancio)."""
    plt = _pyplot()
    fx, dep = res.fixed, res.dep
    modes = modes_used(res.design.operations.sol_types)
    labels = [MODE_LABELS[m].replace(" ", "\n", 1) for m in modes] + ["trazione"]
    values = [fx.e_service[m] / KWH for m in modes] + [dep.e_traction / KWH]
    colors = [SERIES[0]] * len(modes) + [SERIES[1]]
    fig, ax = plt.subplots(figsize=(1.2 * len(labels) + 1.0, 3.8))   # 7 in con cinque barre
    bars = ax.bar(labels, values, color=colors, width=0.6)
    for x, v in enumerate(values):
        ax.text(x, v, f"{n(v)}", ha="center", va="bottom", color=INK2, fontsize=9)
    ax.legend([bars[0], bars[-1]], ["carichi di servizio, per modo", "trazione"], frameon=False, loc="upper left")
    ax.set_ylabel("Energia [kWh]")
    ax.set_title(f"Energia per escursione: {n(sum(values))} kWh", color=INK, fontsize=11, loc="left")
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    path = folder / "energia_per_escursione.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
