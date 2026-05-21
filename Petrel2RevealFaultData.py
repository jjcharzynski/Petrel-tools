# -*- coding: utf-8 -*-
"""
Created on Tue May 19 11:10:59 2026

@author: jon.charzynski
with the help of Copilot
"""

import os
from datetime import datetime
import getpass


def convert_petrel_tm_to_nnc5(tm_file, grid_file):
    """
    Convert a Petrel Eclipse Fault Transmissibility Multiplier Data file
    and a GRDECL grid file into an NNC5 fault connection file.

    This function:
    - Reads a Petrel-exported Eclipse Fault Transmissibility Multiplier file
    - Extracts fault-specific EDITNNC connection data and assigns each NNC to the correct fault
    - Reads a GRDECL file (*.*) to extract grid dimensions from the SPECGRID keyword
    - Converts the data into NNC5 format including:
        - Direction (X/Y/Z)
        - Cell indices (IX1, IY1, IZ1, IX2, IY2, IZ2)
        - TRANS (set to -1)
        - TRANS_MULT (from Petrel)
        - THERMAL_MULT (set to 1)
        - FAULT_INDEX (mapped from fault names)
        - FAULT_WIDTH, FAULT_PERM, (both set to -1)
        - FAULT_THROW (set to 0)

    Additional processing:
    - Removes identical cell-to-cell entries
    - Removes duplicate reverse connections (A ↔ B)
    - Extracts project name from TM file header
    - Writes metadata header including user and timestamp
    
    This was written 

    Parameters
    ----------
    tm_file : str
        Path to Eclipse Fault Transmissibility Multiplier Data (ASCII) file (*.*)
    grid_file : str
        Path to GRDECL grid file (*.*) containing SPECGRID

    Output
    ------
    Writes an NNC5 file in the same directory as tm_file with suffix "_NNC5"
    """

    user_name = getpass.getuser()
    formatted_date = datetime.now().strftime("%A, %B %d %Y %H:%M:%S")

    # --------------------------------------
    # Output file name
    # --------------------------------------
    base, ext = os.path.splitext(tm_file)
    output_file = base + "_NNC5" + ext

    # --------------------------------------
    # Extract project name
    # --------------------------------------
    def get_project_name(file):
        with open(file, 'r') as f:
            for _ in range(50):
                line = f.readline()
                if "-- Project" in line:
                    return line.split(":")[1].strip()
        return "UNKNOWN_PROJECT"

    project_name = get_project_name(tm_file)

    # --------------------------------------
    # Extract DIMENS from SPECGRID
    # --------------------------------------
    def get_dimens(filepath):
        with open(filepath, 'r') as f:
            for _ in range(60):
                line = f.readline()
                if "SPECGRID" in line:
                    next_line = f.readline().strip()
                    parts = next_line.replace("/", "").split()
                    return tuple(map(int, parts[:3]))
        raise RuntimeError("SPECGRID not found in GRDECL")

    NX, NY, NZ = get_dimens(grid_file)

    # --------------------------------------
    # Parse EDITNNC blocks
    # --------------------------------------
    fault_names = {}
    nnc_list = []

    with open(tm_file, 'r') as f:
        lines = f.readlines()

    in_editnnc = False
    current_fault = None

    for line_raw in lines:
        line = line_raw.strip()

        if line.startswith("EDITNNC"):
            in_editnnc = True
            current_fault = None
            continue

        if in_editnnc:

            if line.startswith("/"):
                in_editnnc = False
                current_fault = None
                continue

            if line.startswith("--"):
                name_candidate = line.replace("--", "").strip()

                if name_candidate.upper().startswith("MATRIX"):
                    continue
                if name_candidate.upper().startswith("IX"):
                    continue

                current_fault = name_candidate.replace(" ", "_")

                if current_fault not in fault_names:
                    fault_names[current_fault] = len(fault_names) + 1

                continue

            if not line:
                continue

            parts = line.replace("/", "").split()

            if len(parts) >= 7 and current_fault is not None:
                ix1, iy1, iz1 = map(int, parts[0:3])
                ix2, iy2, iz2 = map(int, parts[3:6])
                trans = float(parts[6])
                
                # Convert near-1 multipliers back to 1.0
                if abs(trans - 0.999) < 1e-6:
                    trans = 1.0

                nnc_list.append({
                    "fault": current_fault,
                    "data": (ix1, iy1, iz1, ix2, iy2, iz2, trans)
                })

    # --------------------------------------
    # Direction function
    # --------------------------------------
    def get_direction(ix1, iy1, ix2, iy2):
        if ix1 != ix2:
            return "X"
        elif iy1 != iy2:
            return "Y"
        else:
            return "Z"

    # --------------------------------------
    # Build NNC5 output
    # --------------------------------------
    output_lines = []
    seen = set()

    skipped_same = 0
    skipped_duplicates = 0

    for entry in nnc_list:
        fault = entry["fault"]
        ix1, iy1, iz1, ix2, iy2, iz2, trans = entry["data"]

        # Skip identical
        if ix1 == ix2 and iy1 == iy2 and iz1 == iz2:
            skipped_same += 1
            continue

        # Deduplicate reverse
        key = tuple(sorted([
            (ix1, iy1, iz1),
            (ix2, iy2, iz2)
        ]))

        if key in seen:
            skipped_duplicates += 1
            continue

        seen.add(key)

        row = [
            get_direction(ix1, iy1, ix2, iy2),
            ix1, iy1, iz1,
            ix2, iy2, iz2,
            -1,
            trans,
            1,
            fault_names[fault],
            -1,
            -1,
            0
        ]

        output_lines.append(row)

    # --------------------------------------
    # Write output
    # --------------------------------------
    with open(output_file, "w") as f:

        f.write("-- Format      : NNC5 fault data (ASCII)\n")
        f.write("-- Exported by : Petrel2RevealFaultData.py\n")
        f.write(f"-- User name   : {user_name}\n")
        f.write(f"-- Date        : {formatted_date}\n")
        f.write(f"-- Project     : {project_name}\n\n")

        f.write("DIMENS\n")
        f.write(f"{NX} {NY} {NZ} /\n\n")

        f.write("FAULTNAMES\n")
        f.write(f"{len(fault_names)}\n")
        for name, idx in fault_names.items():
            f.write(f"{idx} {name}\n")
        f.write("/\n\n")

        f.write("NNC5\n")
        f.write(f"{len(output_lines)}\n")

        for row in output_lines:
            f.write(" ".join(map(str, row)) + "\n")

        f.write("/\nEND\n")

    # --------------------------------------
    # Summary
    # --------------------------------------
    print("=======================================")
    print(f"DIMENS: {NX} {NY} {NZ}")
    print(f"Total faults: {len(fault_names)}")
    print(f"Total NNCs: {len(output_lines)}")
    print(f"Skipped identical cell-to-cell NNCs: {skipped_same}")
    print(f"Skipped duplicate reverse NNCs: {skipped_duplicates}")

    print("\nFault index mapping:")
    for name, idx in fault_names.items():
        print(f"{idx}: {name}")

    print("\nOutput written to:")
    print(output_file)
    print("=======================================")
    
    
    
    
base_path = r""
tm_file     = base_path + r""
grid_file   = base_path + r""  

convert_petrel_tm_to_nnc5(tm_file, grid_file)