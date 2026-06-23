"""
IESO Generator Output Capability — extract + transform to partitioned Parquet.

- Downloads the un-versioned monthly CSVs from the IESO public reports site.
- Skips the 3 comment lines, unpivots Hour 1..24 into long format.
- Pivots Measurement (Output/Capability/Available Capacity/Forecast) into columns.
- Treats Delivery Date + Hour Ending as LOCAL Ontario wall-clock (DST-safe: 24h grid).
- Writes Hive-partitioned Parquet (year=/month=).
- Incremental: only re-downloads months whose source timestamp changed
  (always the current, still-open month; closed months are immutable).

Usage:
  python Extract_Transform_data.py                    # incremental extract
  python Extract_Transform_data.py --full             # re-extract every month
  python Extract_Transform_data.py --aggregate        # build model facts + Dim_Generator
  python Extract_Transform_data.py --dim-generator    # build Dim_Generator only
  python Extract_Transform_data.py --aggregate-after  # extract, then aggregate

Hardening notes (validated against real April-2025 data):
  * Data rows carry a trailing comma (29 fields) vs a 28-field header, which
    makes pandas promote the first column to the index and shift every column
    left by one. Fixed with index_col=False.
  * Offline units leave blank/whitespace hour cells; values are coerced to
    numeric so measures aggregate instead of concatenating strings.
"""

import io
import re
import json
import sys
from pathlib import Path
from datetime import datetime, date

import requests
import pandas as pd

BASE = "https://reports-public.ieso.ca/public/GenOutputCapabilityMonth/"
ROOT = Path(__file__).resolve().parent
PARQUET_DIR = ROOT / "parquet"
STATE_FILE = ROOT / "state.json"
START_MONTH = (2019, 5)        # earliest available file
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "ieso-etl/1.0"})

MEASUREMENT_MAP = {
    "Output": "output_mw",
    "Capability": "capability_mw",
    "Available Capacity": "available_capacity_mw",
    "Forecast": "forecast_mw",
}

# IESO fuel labels -> star-schema FuelKey (matches Dim_FuelType.csv).
# Ontario has no coal/oil in this dataset; BIOFUEL maps to Bioenergy (BIO).
# OTHER is a small, mixed IESO category — kept as its own member (OTH) so total
# generation reconciles instead of being silently dropped. It is NOT classified
# as renewable, and is not assumed to be oil.
FUEL_KEY_MAP = {
    "NUCLEAR": "NUC",
    "HYDRO":   "HYD",
    "WIND":    "WND",
    "SOLAR":   "SOL",
    "GAS":     "GAS",
    "BIOFUEL": "BIO",
    "OTHER":   "OTH",
}


def list_available_months():
    """Parse the directory index, return {(year,month): last_modified_str} for
    un-versioned files only (e.g. PUB_GenOutputCapabilityMonth_202505.csv)."""
    html = SESSION.get(BASE, timeout=60).text
    pattern = re.compile(
        r'PUB_GenOutputCapabilityMonth_(\d{4})(\d{2})\.csv'   # un-versioned only
        r'</a>\s*(\d{2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2})'
    )
    months = {}
    for y, m, modified in pattern.findall(html):
        months[(int(y), int(m))] = modified.strip()
    return months


def fetch_month_csv(year, month):
    url = f"{BASE}PUB_GenOutputCapabilityMonth_{year}{month:02d}.csv"
    resp = SESSION.get(url, timeout=120)
    resp.raise_for_status()
    return resp.text


def transform(csv_text, year, month):
    """CSV text -> tidy DataFrame (one row per date/generator/hour)."""
    # Skip the 3 leading comment lines (\\ prefixed). Header is line index 3.
    # IMPORTANT: every data row carries a trailing comma (29 fields) while the
    # header has 28. Without index_col=False, pandas promotes the first column
    # to the index and silently shifts every column left by one.
    df = pd.read_csv(io.StringIO(csv_text), skiprows=3, index_col=False)

    # Drop fully-empty trailing column created by the trailing comma, if present.
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]

    hour_cols = [c for c in df.columns if c.startswith("Hour ")]
    id_cols = ["Delivery Date", "Generator", "Fuel Type", "Measurement"]

    long = df.melt(
        id_vars=id_cols, value_vars=hour_cols,
        var_name="hour_ending", value_name="value",
    )
    long["hour_ending"] = long["hour_ending"].str.replace("Hour ", "", regex=False).astype("int16")

    # Hour cells can be blank/whitespace (e.g. " ") for offline units. Coerce to
    # numeric so downstream measures aggregate instead of concatenating strings.
    long["value"] = pd.to_numeric(long["value"], errors="coerce")

    # Pivot measurements into columns -> one row per date/generator/hour.
    wide = long.pivot_table(
        index=["Delivery Date", "Generator", "Fuel Type", "hour_ending"],
        columns="Measurement", values="value", aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    wide = wide.rename(columns=MEASUREMENT_MAP)

    # Local Ontario wall-clock timestamp. hour_ending 1 => 00:00, ... 24 => 23:00.
    _dd = pd.to_datetime(wide["Delivery Date"], format="%Y-%m-%d")
    wide["delivery_date"] = _dd.dt.date
    wide["local_datetime"] = _dd + pd.to_timedelta(wide["hour_ending"] - 1, unit="h")
    wide = wide.rename(columns={"Generator": "generator", "Fuel Type": "fuel_type"})
    wide = wide.drop(columns=["Delivery Date"])

    # Ensure all measurement columns exist even if a month lacks one.
    for col in MEASUREMENT_MAP.values():
        if col not in wide.columns:
            wide[col] = pd.NA

    wide["year"] = year
    wide["month"] = month

    ordered = [
        "delivery_date", "local_datetime", "hour_ending",
        "generator", "fuel_type",
        "output_mw", "capability_mw", "available_capacity_mw", "forecast_mw",
        "year", "month",
    ]
    return wide[ordered]


def write_parquet(df, year, month):
    out_dir = PARQUET_DIR / f"year={year}" / f"month={month:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / "data.parquet", index=False)  # needs pyarrow


def aggregate_to_model(parquet_dir=None, out_dir=None):
    """Roll hourly generator Output up to province x fuel x period GWh, ready to
    feed Fact_Generation in the Power BI star schema.

    Each hourly row is 1 MW sustained for 1 hour = 1 MWh, so summing output_mw
    over hours/days/generators gives MWh; /1000 -> GWh. Writes monthly + annual."""
    parquet_dir = Path(parquet_dir or PARQUET_DIR)
    out_dir = Path(out_dir or ROOT)
    files = sorted(parquet_dir.rglob("data.parquet"))
    if not files:
        print("No parquet partitions found. Run the extract first.", file=sys.stderr)
        return
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    df["fuel_key"] = df["fuel_type"].str.upper().map(FUEL_KEY_MAP)
    unknown = sorted(df.loc[df["fuel_key"].isna(), "fuel_type"].dropna().unique())
    if unknown:
        print(f"  WARNING unmapped fuel types ignored: {unknown}", file=sys.stderr)
    df = df.dropna(subset=["fuel_key"])

    dt = pd.to_datetime(df["delivery_date"])
    df["yr"] = dt.dt.year
    df["mo"] = dt.dt.month

    # Monthly grain (period key = first of month)
    monthly = df.groupby(["yr", "mo", "fuel_key"], as_index=False)["output_mw"].sum()
    monthly["Generation_GWh"] = (monthly["output_mw"] / 1000.0).round(1)
    monthly["ProvinceKey"] = "ON"
    monthly["DateKey"] = (monthly["yr"].astype(str)
                          + monthly["mo"].astype(str).str.zfill(2) + "01").astype(int)
    monthly = monthly.rename(columns={"fuel_key": "FuelKey", "yr": "Year", "mo": "Month"})
    monthly = monthly[["ProvinceKey", "FuelKey", "DateKey", "Year", "Month", "Generation_GWh"]]

    # Annual grain (period key = year-end, matches the seed facts)
    annual = df.groupby(["yr", "fuel_key"], as_index=False)["output_mw"].sum()
    annual["Generation_GWh"] = (annual["output_mw"] / 1000.0).round(1)
    annual["ProvinceKey"] = "ON"
    annual["DateKey"] = (annual["yr"].astype(str) + "1231").astype(int)
    annual["SourceFlag"] = "IESO"
    annual = annual.rename(columns={"fuel_key": "FuelKey", "yr": "Year"})
    annual = annual[["ProvinceKey", "FuelKey", "DateKey", "Year", "Generation_GWh", "SourceFlag"]]

    monthly.to_parquet(out_dir / "Fact_Generation_ON_monthly.parquet", index=False)
    monthly.to_csv(out_dir / "Fact_Generation_ON_monthly.csv", index=False)
    annual.to_parquet(out_dir / "Fact_Generation_ON_annual.parquet", index=False)
    annual.to_csv(out_dir / "Fact_Generation_ON_annual.csv", index=False)
    print(f"  aggregated {len(files)} partitions -> "
          f"{len(monthly):,} monthly / {len(annual):,} annual rows")
    return annual


def build_dim_generator(parquet_dir=None, out_dir=None):
    """Distinct generator -> fuel mapping from the parquet, written as
    Dim_Generator.csv (GeneratorKey, Generator, FuelType, FuelKey).
    Regenerate when new generators come online."""
    parquet_dir = Path(parquet_dir or PARQUET_DIR)
    out_dir = Path(out_dir or ROOT)
    files = sorted(parquet_dir.rglob("data.parquet"))
    if not files:
        print("No parquet partitions found. Run the extract first.", file=sys.stderr)
        return
    seen = {}
    for f in files:
        d = pd.read_parquet(f, columns=["generator", "fuel_type"]).drop_duplicates()
        for g, ft in d.itertuples(index=False):
            if pd.isna(g):
                continue
            seen.setdefault(g, ft)  # data has exactly 1 fuel per generator

    rows = [{
        "GeneratorKey": g,
        "Generator": g,
        "FuelType": str(ft).title() if ft is not None else None,
        "FuelKey": FUEL_KEY_MAP.get(str(ft).upper(), ""),
    } for g, ft in seen.items()]
    out = pd.DataFrame(rows).sort_values(["FuelType", "Generator"]).reset_index(drop=True)

    missing = out.loc[out["FuelKey"] == "", "FuelType"].dropna().unique().tolist()
    if missing:
        print(f"  WARNING generators with unmapped fuel: {missing}", file=sys.stderr)
    out.to_csv(out_dir / "Dim_Generator.csv", index=False)
    print(f"  wrote Dim_Generator.csv: {len(out)} generators")
    return out


def load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def month_iter(start, end):
    y, m = start
    while (y, m) <= end:
        yield (y, m)
        m += 1
        if m > 12:
            y, m = y + 1, 1


def main(full_refresh=False):
    available = list_available_months()
    state = {} if full_refresh else load_state()
    today = date.today()
    end = (today.year, today.month)

    processed = skipped = 0
    for (y, m) in month_iter(START_MONTH, end):
        if (y, m) not in available:
            continue
        key = f"{y}{m:02d}"
        src_modified = available[(y, m)]
        if not full_refresh and state.get(key) == src_modified:
            skipped += 1
            continue
        try:
            csv_text = fetch_month_csv(y, m)
            df = transform(csv_text, y, m)
            write_parquet(df, y, m)
            state[key] = src_modified
            processed += 1
            print(f"  processed {key}: {len(df):,} rows")
        except Exception as e:                       # noqa
            print(f"  ERROR {key}: {e}", file=sys.stderr)

    save_state(state)
    print(f"Done. processed={processed} skipped(unchanged)={skipped} "
          f"at {datetime.now():%Y-%m-%d %H:%M}")


if __name__ == "__main__":
    if "--aggregate" in sys.argv:
        aggregate_to_model()
        build_dim_generator()
    elif "--dim-generator" in sys.argv:
        build_dim_generator()
    else:
        main(full_refresh="--full" in sys.argv)
        if "--aggregate-after" in sys.argv:
            aggregate_to_model()
            build_dim_generator()
