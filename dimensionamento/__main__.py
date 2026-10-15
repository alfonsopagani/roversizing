"""Interfaccia a riga di comando.

Esempi:
    python -m dimensionamento progetti/esempio.toml
    python -m dimensionamento progetti/esempio.toml --set mobility.crr=0.6
    python -m dimensionamento progetti/esempio.toml --sweep mobility.crr 0.1 0.6 11 --plot
    python -m dimensionamento progetti/esempio.toml --fuori-progetto mobility.crr=0.6
    python -m dimensionamento progetti/esempio.toml --sweep mobility.crr 0.1 0.6 11 --congelato
    python -m dimensionamento progetti/esempio.toml --out risultati --plot
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

from . import __version__
from .inputs import InputError, apply_override, load_common, load_design, validate
from .report import (format_markdown, format_text, n, plot_energy, plot_mass, print_report,
                     requirements_table, write_outputs)
from .sensitivity import failed_requirements, linspace, plot_frozen, plot_sweep, sweep, sweep_table
from .sizing import SizingError, off_design, run


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="python -m dimensionamento",
        description="Dimensionamento di ordine ridotto di un rover pressurizzato per Marte (esercitazione E2).")
    p.add_argument("input", help="file TOML del gruppo")
    p.add_argument("--set", action="append", default=[], metavar="SEZIONE.CHIAVE=VALORE",
                   help="modifica un valore del file di input solo per questa esecuzione (ripetibile)")
    p.add_argument("--sweep", nargs=4, metavar=("SEZIONE.CHIAVE", "DA", "A", "N"),
                   help="studio di sensitività: N valori equispaziati fra DA e A")
    p.add_argument("--fuori-progetto", action="append", default=[], dest="off_design",
                   metavar="SEZIONE.CHIAVE=VALORE",
                   help="verifica fuori progetto: il rover dimensionato con il file di input opera "
                        "con il valore indicato (ripetibile), per esempio mobility.crr=0.6")
    p.add_argument("--congelato", action="store_true",
                   help="con --sweep: verifica fuori progetto del rover dimensionato con il file di "
                        "input, invece di riprogettarlo a ogni valore")
    p.add_argument("--out", metavar="CARTELLA", help="salva report.md e i CSV nella cartella")
    p.add_argument("--plot", action="store_true", help="salva anche i grafici PNG (richiede matplotlib)")
    p.add_argument("--version", action="version", version=f"roversizing {__version__} (pacchetto dimensionamento)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        common = load_common()
        design, raw = load_design(args.input, args.set)
        name = Path(args.input).name
        folder = Path(args.out) if args.out else Path(".")

        if args.sweep:
            key, start, stop, count = args.sweep
            try:
                values = linspace(float(start), float(stop), int(float(count)))
            except ValueError:
                raise InputError(f"--sweep: DA, A e N devono essere numeri ({start}, {stop}, {count}).") from None
            rows = sweep(common, raw, name, key, values, frozen=args.congelato)
            table = sweep_table(key, rows, frozen=args.congelato)
            print(format_text(table))
            prefix = "fuori_progetto" if args.congelato else "sensitivita"
            if args.out:
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"{prefix}_{key.replace('.', '_')}.md"
                path.write_text(format_markdown(table) + "\n", encoding="utf-8")
                print(f"\nTabella salvata in {path}")
            if args.plot:
                folder.mkdir(parents=True, exist_ok=True)
                plots = (plot_frozen(key, rows, common.mission, folder) if args.congelato
                         else plot_sweep(key, rows, common.mission.mass_limit, folder))
                for path in plots:
                    print(f"Grafico salvato in {path}")
            return 0

        if args.off_design:
            changed = copy.deepcopy(raw)
            for assignment in args.off_design:
                apply_override(changed, assignment)
            nominal, off = off_design(common, design, validate(changed, name))
            lines = [f"Verifica fuori progetto: {', '.join(args.off_design)}",
                     f"File di input: {name}",
                     "Rover congelato come dimensionato dal file di input: massa "
                     f"{n(nominal.budget.total)} kg, picco di trazione {n(nominal.dep.p_peak / 1e3, 1)} kW, "
                     f"batteria {n(nominal.dep.battery_capacity / 3.6e6, 1)} kWh.",
                     f"Requisiti non soddisfatti nel progetto nominale: {failed_requirements(nominal)}",
                     f"Requisiti non soddisfatti fuori progetto: {failed_requirements(off)}", ""]
            table = requirements_table(off)
            print("\n".join(lines))
            print(format_text(table))
            if args.out:
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / "fuori_progetto.md"
                path.write_text("\n".join(lines) + "\n" + format_markdown(table) + "\n", encoding="utf-8")
                print(f"\nSalvato {path}")
            return 0

        res = run(common, design)
        print_report(res, name)
        if args.out:
            for path in write_outputs(res, name, folder):
                print(f"Salvato {path}")
        if args.plot and res.loop.converged:
            folder.mkdir(parents=True, exist_ok=True)
            for path in (plot_mass(res, folder), plot_energy(res, folder)):
                print(f"Grafico salvato in {path}")
        return 0 if res.loop.converged else 2
    except (InputError, SizingError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
