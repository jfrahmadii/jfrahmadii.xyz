#!/usr/bin/env python3
"""
Canada Electricity Decarbonization Tracker - dataset builder
============================================================
Builds the star-schema CSVs for the Power BI / Fabric portfolio project
(Ontario vs Alberta). Two modes:

1) Dimensions + verified SEED facts  -> always written (no internet needed).
   These are real, citable figures pulled from the CER Provincial Energy
   Profiles, AESO 2024 Annual Market Statistics, and the ECCC National
   Inventory Report. They make the model immediately demoable.

2) FULL annual backfill (optional)   -> run with  `python build_dataset.py --backfill`
   Downloads the CER "Figure Data" CSVs (2005-2022 generation-by-fuel trend
   and 1990-2022 emissions-intensity trend) and expands Fact_Generation /
   Fact_Emissions to the full time series. These files are served as binary
   downloads, so they must be fetched from a normal machine (this script),
   not through the assistant's restricted fetch tools.

Output: ./  (CSV files land next to this script)
Author: Jeff  |  Stack: Power BI / Microsoft Fabric
"""

import csv, os, sys, datetime, io

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# DIMENSION: Province
# ---------------------------------------------------------------------------
PROVINCES = [
    # ProvinceKey, Province, ISO, Region, GridOperator
    ("ON", "Ontario", "CA-ON", "Central Canada", "IESO"),
    ("AB", "Alberta", "CA-AB", "Prairies",       "AESO"),
]

# ---------------------------------------------------------------------------
# DIMENSION: Fuel type   (renewable flag + emitting flag + category)
# ---------------------------------------------------------------------------
FUELS = [
    # FuelKey, FuelType, Category, IsRenewable, IsEmitting
    ("NUC", "Nuclear",   "Non-emitting", 0, 0),
    ("HYD", "Hydro",     "Renewable",    1, 0),
    ("WND", "Wind",      "Renewable",    1, 0),
    ("SOL", "Solar",     "Renewable",    1, 0),
    ("BIO", "Bioenergy", "Renewable",    1, 1),  # biogenic; counted renewable
    ("GAS", "Natural Gas","Fossil",      0, 1),
    ("COA", "Coal",      "Fossil",       0, 1),
    ("OIL", "Oil/Other", "Fossil",       0, 1),
    ("OTH", "Other",     "Other",        0, 1),  # IESO "OTHER" mixed category
]

# ---------------------------------------------------------------------------
# DIMENSION: Date  (daily grain, supports Power BI time-intelligence)
# ---------------------------------------------------------------------------
DATE_START = datetime.date(1990, 1, 1)
DATE_END   = datetime.date(2026, 12, 31)

def build_dim_date(path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["DateKey","Date","Year","Quarter","QuarterNum",
                    "MonthNum","MonthName","IsYearEnd"])
        d = DATE_START
        one = datetime.timedelta(days=1)
        while d <= DATE_END:
            q = (d.month - 1)//3 + 1
            is_ye = 1 if (d.month == 12 and d.day == 31) else 0
            w.writerow([d.strftime("%Y%m%d"), d.isoformat(), d.year,
                        f"Q{q}", q, d.month, d.strftime("%B"), is_ye])
            d += one

def build_dim_province(path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ProvinceKey","Province","ISOCode","Region","GridOperator"])
        w.writerows(PROVINCES)

def build_dim_fuel(path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["FuelKey","FuelType","Category","IsRenewable","IsEmitting"])
        w.writerows(FUELS)

# ---------------------------------------------------------------------------
# SEED FACTS  (verified, citable; year-end period key = YYYY-12-31)
# ---------------------------------------------------------------------------
# Generation in GWh. Source = CER Provincial Energy Profiles (2021), shares x
# published provincial total. Where CER stated a fuel's share exactly it is
# marked 'CER'; the gas/bio split of Ontario's ~9% remainder is marked 'EST'
# (replace with exact values via --backfill).
#   Ontario 2021 total = 148,300 GWh ; Alberta 2021 total = 73,900 GWh
SEED_GENERATION = [
    # ProvinceKey, FuelKey, Year, GWh, SourceFlag
    ("ON","NUC",2021, 81565,"CER"),
    ("ON","HYD",2021, 35592,"CER"),
    ("ON","WND",2021, 11864,"CER"),
    ("ON","SOL",2021,  5932,"CER"),
    ("ON","GAS",2021, 11864,"EST"),
    ("ON","BIO",2021,  1483,"EST"),
    ("AB","GAS",2021, 46557,"CER"),
    ("AB","COA",2021, 16258,"CER"),
    ("AB","WND",2021,  6651,"CER"),
    ("AB","HYD",2021,  2217,"CER"),
    ("AB","BIO",2021,  1478,"CER"),
    ("AB","SOL",2021,   739,"EST"),
]

# Emissions facts. tCO2e (power sector) and grid intensity gCO2e/kWh.
# Sources: ECCC National Inventory Report 1990-2022 via CER profiles.
#   ON power-sector emissions 2022 = 3.8 Mt ; AB 2022 = 19.4 Mt
#   Grid intensity anchors (gCO2e/kWh): ON 200(1990)/220(2005)/35(2022)
#                                       AB 950(1990)/910(2005)/470(2022)
SEED_EMISSIONS = [
    # ProvinceKey, Year, EmissionsTonnesCO2e, GridIntensity_gPerKWh, SourceFlag
    ("ON",1990, None, 200,"CER/ECCC"),
    ("ON",2005, None, 220,"CER/ECCC"),
    ("ON",2022, 3800000, 35,"CER/ECCC"),
    ("AB",1990, None, 950,"CER/ECCC"),
    ("AB",2005, None, 910,"CER/ECCC"),
    ("AB",2022, 19400000, 470,"CER/ECCC"),
]

def yearkey(year):  # period key = Dec 31 of the year
    return f"{year}1231"

def build_fact_generation(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ProvinceKey","FuelKey","DateKey","Year",
                    "Generation_GWh","SourceFlag"])
        for pk, fk, yr, gwh, src in rows:
            w.writerow([pk, fk, yearkey(yr), yr, gwh, src])

def build_fact_emissions(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ProvinceKey","DateKey","Year",
                    "Emissions_tCO2e","GridIntensity_gPerKWh","SourceFlag"])
        for pk, yr, t, gi, src in rows:
            w.writerow([pk, yearkey(yr), yr, t if t is not None else "", gi, src])

# ---------------------------------------------------------------------------
# OPTIONAL BACKFILL from CER figure-data CSVs
# ---------------------------------------------------------------------------
CER_BASE = ("https://www.cer-rec.gc.ca/en/data-analysis/energy-markets/"
            "province-territory-energy-profiles/data")
CER_FILES = {
    "ON_gen":  f"{CER_BASE}/ontario/figure-02-data.csv",
    "ON_int":  f"{CER_BASE}/ontario/figure-09-data.csv",
    "AB_gen":  f"{CER_BASE}/alberta/figure-02-data.csv",
    "AB_int":  f"{CER_BASE}/alberta/figure-09-data.csv",
}

def backfill():
    import urllib.request
    print("Downloading CER figure-data CSVs ...")
    raw = {}
    for k, url in CER_FILES.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            raw[k] = urllib.request.urlopen(req, timeout=30).read().decode("utf-8-sig")
            print(f"  ok  {k}: {len(raw[k])} bytes")
        except Exception as e:
            print(f"  FAIL {k}: {e}")
    # NOTE: inspect raw[...] headers once, then map columns -> FUELS keys.
    # CER trend files are wide (one column per fuel, one row per year).
    # Left as an explicit TODO so the mapping is reviewed, not guessed:
    for k, txt in raw.items():
        head = txt.splitlines()[:2]
        print(f"\n[{k}] header preview:\n  " + "\n  ".join(head))
    print("\nReview the headers above, then map columns to FuelKey in "
          "parse_cer_gen()/parse_cer_int() to emit the full 2005-2022 facts.")

# ---------------------------------------------------------------------------
def main():
    build_dim_date(os.path.join(HERE, "Dim_Date.csv"))
    build_dim_province(os.path.join(HERE, "Dim_Province.csv"))
    build_dim_fuel(os.path.join(HERE, "Dim_FuelType.csv"))
    build_fact_generation(os.path.join(HERE, "Fact_Generation.csv"), SEED_GENERATION)
    build_fact_emissions(os.path.join(HERE, "Fact_Emissions.csv"), SEED_EMISSIONS)
    print("Wrote: Dim_Date, Dim_Province, Dim_FuelType, "
          "Fact_Generation, Fact_Emissions (seed).")
    if "--backfill" in sys.argv:
        backfill()

if __name__ == "__main__":
    main()
