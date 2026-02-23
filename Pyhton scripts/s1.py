import argparse
from pathlib import Path
import pandas as pd
import sys

def pick_engine(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return "openpyxl"
    elif suffix == ".xls":
        return "xlrd"  # requires: pip install xlrd
    else:
        return None  # let pandas decide (or raise)

def normalize_key(series: pd.Series) -> pd.Series:
    # Normalize for case-insensitive, whitespace-trimmed comparison
    return series.astype(str).str.strip().str.casefold()

def main():
    parser = argparse.ArgumentParser(
        description="Compare a key column between two Excel sheets and copy a source column "
                    "from File A → target column in File B where keys match (VLOOKUP-like)."
    )
    parser.add_argument("--file-a", required=True, help="Path to the first Excel file (source).")
    parser.add_argument("--sheet-a", default=0, help="Sheet name or index in File A (default: 0).")
    parser.add_argument("--key-a", required=True, help="Key column name in File A (to match).")
    parser.add_argument("--source-a", required=True, help="Column name in File A to copy when matched.")

    parser.add_argument("--file-b", required=True, help="Path to the second Excel file (destination).")
    parser.add_argument("--sheet-b", default=0, help="Sheet name or index in File B (default: 0).")
    parser.add_argument("--key-b", required=True, help="Key column name in File B (to look up).")
    parser.add_argument("--target-b", required=True, help="Target column name to populate in File B.")

    parser.add_argument("--output", required=True, help="Output .xlsx file path to write results.")
    parser.add_argument("--only-fill-empty", action="store_true",
                        help="If set, only fill NaN/blank cells in target; do not overwrite existing values.")
    parser.add_argument("--copy-all-sheets", action="store_true",
                        help="If set, copy ALL sheets from File B into the output and replace only --sheet-b.")

    args = parser.parse_args()

    file_a = Path(args.file_a)
    file_b = Path(args.file_b)
    out_path = Path(args.output)

    if not file_a.exists():
        sys.exit(f"ERROR: File A not found: {file_a}")
    if not file_b.exists():
        sys.exit(f"ERROR: File B not found: {file_b}")

    eng_a = pick_engine(file_a)
    eng_b = pick_engine(file_b)

    # --- Read the specific sheets
    df_a = pd.read_excel(file_a, sheet_name=args.sheet_a, engine=eng_a)
    df_b = pd.read_excel(file_b, sheet_name=args.sheet_b, engine=eng_b)

    # Validate required columns
    for col, label, df in [(args.key_a, "key-a", df_a),
                           (args.source_a, "source-a", df_a),
                           (args.key_b, "key-b", df_b)]:
        if col not in df.columns:
            sys.exit(f"ERROR: Column '{col}' (from {label}) not found in its sheet.")

    # --- Build mapping from A[key_a] → A[source_a] using normalized key (first match wins on duplicates)
    df_a["_key_norm_"] = normalize_key(df_a[args.key_a])
    # In case of duplicates, 'first' will keep the first non-null source
    mapping = df_a.groupby("_key_norm_")[args.source_a].first()

    # --- Map B's key to A's source column (normalized comparison)
    key_b_norm = normalize_key(df_b[args.key_b])
    matched_values = key_b_norm.map(mapping)

    # --- Apply to target column in B
    # Ensure target column exists (create if missing)
    if args.target_b not in df_b.columns:
        df_b[args.target_b] = pd.NA

    if args.only-fill-empty:
        # Fill only where target is NA/blank
        is_blank = df_b[args.target_b].isna() | (df_b[args.target_b].astype(str).str.strip() == "")
        df_b.loc[is_blank, args.target_b] = matched_values.loc[is_blank]
    else:
        # Overwrite always
        df_b[args.target_b] = matched_values

    # --- Simple match statistics
    matches = matched_values.notna().sum()
    total = len(df_b)
    print(f"Matched {matches}/{total} rows in B based on key comparison.")

    # --- Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.copy_all_sheets:
        # Copy all sheets from File B, replacing only sheet-b
        xls_b = pd.ExcelFile(file_b, engine=eng_b)
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            for sname in xls_b.sheet_names:
                if (str(args.sheet_b) == sname) or (isinstance(args.sheet_b, int) and
                                                    sname == xls_b.sheet_names[int(args.sheet_b)]):
                    # Write modified df_b into the target sheet
                    df_b.to_excel(writer, sheet_name=sname, index=False)
                else:
                    # Copy untouched sheets as-is
                    df_tmp = pd.read_excel(file_b, sheet_name=sname, engine=eng_b)
                    df_tmp.to_excel(writer, sheet_name=sname, index=False)
    else:
        # Write only the modified sheet to a new workbook
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            # Preserve sheet name where possible
            sheet_name = (df_b.attrs.get("sheet_name") if hasattr(df_b, "attrs") else None) or \
                         (args.sheet_b if isinstance(args.sheet_b, str) else "Sheet1")
            df_b.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"Done. Wrote: {out_path}")

if __name__ == "__main__":
    main()