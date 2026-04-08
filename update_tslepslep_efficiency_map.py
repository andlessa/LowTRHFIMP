#!/usr/bin/env python3
"""Populate efficiencyMap entries in all TSlepSlep.txt files from orig signal files.

The script reads Acc values from files like:
  orig/TSlepSlep_<m_slep>_<m_lsp>_signal.dat
and updates each:
  SR*_cuts/TSlepSlep.txt
by rebuilding its efficiencyMap with one entry per mass point.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Tuple

MassPoint = Tuple[int, int]
AccByMass = Dict[MassPoint, Dict[str, str]]

SIGNAL_FILE_RE = re.compile(r"^TSlepSlep_(\d+)_(\d+)_signal\.dat$")
CUTS_DIR_RE = re.compile(r"^SR(DF|SF)_([01])([a-i])_cuts$")
SR_LINE_RE = re.compile(r"^(SR-[A-Z]{2}-[01]J[a-i])\s+\S+\s+\S+\s+(\S+)")


def parse_signal_file(path: Path) -> Dict[str, str]:
    """Return SR -> Acc values as strings from one signal .dat file."""
    sr_to_acc: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = SR_LINE_RE.match(line.strip())
        if m:
            sr_to_acc[m.group(1)] = m.group(2)
    return sr_to_acc


def collect_acc_values(orig_dir: Path) -> AccByMass:
    """Collect all mass-point Acc maps from SlepSlep_*_signal.dat files."""
    acc_by_mass: AccByMass = {}
    for path in sorted(orig_dir.glob("SlepSlep*/analysis/SlepSlep_*_signal.dat")):
        m = SIGNAL_FILE_RE.match(path.name)
        if not m:
            continue
        mass_point = (int(m.group(1)), int(m.group(2)))
        acc_by_mass[mass_point] = parse_signal_file(path)
    if not acc_by_mass:
        raise RuntimeError(f"No TSlepSlep signal files found in {orig_dir}")
    return acc_by_mass


def folder_to_sr(folder_name: str) -> str | None:
    """Convert folder name like SRDF_0a_cuts into SR name SR-DF-0Ja."""
    m = CUTS_DIR_RE.match(folder_name)
    if not m:
        return None
    flavor, njet, letter = m.groups()
    return f"SR-{flavor}-{njet}J{letter}"


def format_mass(mass: int) -> str:
    return f"{mass:.4E}"


def build_efficiency_map(sr_name: str, acc_by_mass: AccByMass) -> str:
    """Build the full efficiencyMap block for one SR."""
    entries: List[str] = []
    for (m_slep, m_lsp), sr_map in sorted(acc_by_mass.items()):
        if sr_name not in sr_map:
            continue
        m1 = format_mass(m_slep)
        m2 = format_mass(m_lsp)
        acc = sr_map[sr_name]
        entries.append(f"[[[{m1}*GeV,{m2}*GeV],[{m1}*GeV,{m2}*GeV]],{acc}]")

    if not entries:
        return "efficiencyMap: []\n"

    if len(entries) == 1:
        return f"efficiencyMap: [{entries[0]}]\n"

    body = ",\n".join(entries)
    return f"efficiencyMap: [{body}]\n"


def update_file(path: Path, new_eff_map_block: str, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    updated = re.sub(r"(?ms)^efficiencyMap:\s*.*\Z", new_eff_map_block, text)
    if updated == text:
        return False
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update all TSlepSlep.txt efficiencyMap fields from orig signal Acc values."
    )
    parser.add_argument(
        "--root",
        default="/home/lessa/smodels-database/13TeV/ATLAS/ATLAS-SUSY-2018-32-eff",
        help="Analysis root directory containing orig/ and SR*_cuts/ (default: current directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which files would be updated without writing changes.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    orig_dir = Path("./run_01_SlepSlep").resolve()
    acc_by_mass = collect_acc_values(orig_dir)

    ts_files = sorted(root.glob("SR*_cuts/TSlepSlep.txt"))
    if not ts_files:
        raise RuntimeError(f"No TSlepSlep.txt files found under {root}")

    changed = 0
    skipped = 0

    for ts_file in ts_files:
        sr_name = folder_to_sr(ts_file.parent.name)
        if sr_name is None:
            skipped += 1
            continue

        block = build_efficiency_map(sr_name, acc_by_mass)
        if update_file(ts_file, block, args.dry_run):
            changed += 1
            print(f"updated: {ts_file.relative_to(root)}")
        else:
            print(f"unchanged: {ts_file.relative_to(root)}")

    print(f"done: changed={changed}, skipped={skipped}, total={len(ts_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
