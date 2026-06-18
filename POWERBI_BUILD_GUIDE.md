# Power BI Build Guide — Ontario Electricity Decarbonization Tracker (Wk 3 MVP)

Rebuild the prototype (`dashboard_prototype.html`) as a published Power BI report.
Scope: **Ontario MVP** on the real IESO data. ~60–90 min for a first pass.

---

## 0. Files you need (all in this folder)

| File | Loads as | Use |
|---|---|---|
| `Fact_Generation_ON_annual.csv` | Fact | Annual GWh by fuel (year-end DateKey) |
| `Fact_Generation_ON_monthly.csv` | Fact | Monthly GWh by fuel (drill-down) |
| `parquet/` (year=/month=) | Fact (optional) | Hourly, generator-level detail |
| `Dim_Date.csv` | Dimension | Date table |
| `Dim_FuelType.csv` | Dimension | Fuel + renewable/emitting flags |
| `Dim_Generator.csv` | Dimension | Plant → fuel (drill-down) |
| `Fact_Emissions.csv` | Fact | Grid intensity anchors |

---

## 1. Load data

Home → Get data → Text/CSV → load the five CSVs above. (For the hourly layer:
Get data → Folder → point at `parquet/`, or Parquet connector.)

In Power Query, set types: `DateKey` = Whole number, `Year`/`Month` = Whole number,
`Generation_GWh` = Decimal, keys = Text. Close & Apply.

---

## 2. Model (relationships)

Model view → create these (all single-direction, 1→*, dimension to fact):

- `Dim_Date[DateKey]` → `Fact_Generation_ON_annual[DateKey]`
- `Dim_Date[DateKey]` → `Fact_Emissions[DateKey]`
- `Dim_FuelType[FuelKey]` → `Fact_Generation_ON_annual[FuelKey]`
- `Dim_FuelType[FuelKey]` → `Dim_Generator[FuelKey]`

Mark `Dim_Date` as the date table (Table tools → Mark as date table → `Date`).
Hide every key column on the fact tables (right-click → Hide) so the field list stays clean.

---

## 3. DAX measures

Create a measures table (Enter data → empty table `_Measures`) and add:

```DAX
Total Generation (GWh) = SUM ( 'Fact_Generation_ON_annual'[Generation_GWh] )

Renewable Generation (GWh) =
    CALCULATE ( [Total Generation (GWh)], 'Dim_FuelType'[IsRenewable] = 1 )

Renewable Share % =
    DIVIDE ( [Renewable Generation (GWh)], [Total Generation (GWh)] )

Emissions-Free Generation (GWh) =
    CALCULATE ( [Total Generation (GWh)], 'Dim_FuelType'[IsEmitting] = 0 )

Emissions-Free Share % =
    DIVIDE ( [Emissions-Free Generation (GWh)], [Total Generation (GWh)] )

Gas Generation (TWh) =
    CALCULATE ( [Total Generation (GWh)], 'Dim_FuelType'[FuelKey] = "GAS" ) / 1000

YoY Δ Emissions-Free Share =
    [Emissions-Free Share %]
  - CALCULATE ( [Emissions-Free Share %], DATEADD ( 'Dim_Date'[Date], -1, YEAR ) )

Grid Intensity (gCO2e/kWh) = AVERAGE ( 'Fact_Emissions'[GridIntensity_gPerKWh] )
```

> Note: `IsEmitting=0` covers nuclear + hydro + wind + solar (Bioenergy is flagged
> emitting=1, biogenic). "Emissions-free share" therefore ≈ the prototype's 80–93%.
> Use `Renewable Share %` for the renewables-only KPI (~32%).

---

## 4. Visuals (canvas 1280×720, 12-col grid)

**Headline insight (text box, top, full width).** One sentence, ~18pt:
> "Ontario runs one of North America's cleanest grids — but its emissions-free share
> slipped from 93% (2020) to 80% (2025) as gas tripled and nuclear dipped."

**KPI row — 4 Card visuals** (below headline):
1. `Total Generation (GWh)` — title "Total generation"
2. `Emissions-Free Share %` (format %) — title "Emissions-free share"
3. `Renewable Share %` — title "Renewable share"
4. `Gas Generation (TWh)` — title "Natural-gas output"

**Visual 1 — Generation mix over time** (stacked area chart, large, left):
- X = `Dim_Date[Year]`, Y = `Total Generation (GWh)`, Legend = `Dim_FuelType[FuelType]`
- Filter the page/visual to Year ≥ 2020 and ≤ 2025 (2019 and 2026 are partial).

**Visual 2 — Emissions-free share** (line chart, right top):
- X = `Year`, Y = `Emissions-Free Share %`. Y-axis min 0.7, max 1.0.

**Visual 3 — Gas vs nuclear** (line chart, right bottom):
- X = `Year`, Y = `Total Generation (GWh)`, Legend = `FuelType`,
  visual-level filter `FuelType in {Natural Gas, Nuclear}`.

Optional drill: enable drill-down on Visual 1 using `Dim_Date` hierarchy
(Year → Month) backed by `Fact_Generation_ON_monthly`, and add a `Dim_Generator`
table visual for plant-level detail.

---

## 5. Theme (reserve green for renewables)

View → Themes → Customize. Data colors by fuel:

| Fuel | Hex |
|---|---|
| Nuclear | `#7F77DD` |
| Hydro | `#378ADD` |
| Wind | `#639922` |
| Solar | `#EF9F27` |
| Bioenergy | `#1D9E75` |
| Natural Gas | `#888780` (neutral) |
| Other | `#B4B2A9` |

Accessibility: don't rely on color alone — keep the legend visible and label the
gas series directly. Cite sources in a footer text box (IESO + CER + ECCC).

---

## 6. Publish (Definition of Done)

1. Save `.pbix`.
2. Publish to a Power BI workspace → Publish to web (or shareable link).
3. Confirm: live link works, ≥1 headline insight on canvas, all sources cited.
4. Drop the link in the README and your resume; write the LinkedIn post (Wk 4).

---

## 7. Reconciliation check before you publish

Card test: `Total Generation (GWh)` for 2024 should read **156,594** (156.6 TWh),
matching the README reconciliation table. If it doesn't, a relationship or filter
is off. 2020–2025 emissions-free share should read 93.2% → 80.1%.
