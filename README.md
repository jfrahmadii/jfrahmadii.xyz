# jfrahmadii.xyz — Data Analytics Portfolio

Personal site — a publication of data-driven energy analysis (static HTML/CSS/JS,
deployed on **GitHub Pages** at **[jfrahmadii.xyz](https://jfrahmadii.xyz)**), plus
the full data project behind its first piece. New analyses get added as more pages
under `projects/`.

| Path | What it is |
|---|---|
| `index.html` | Home — intro, writing feed, about |
| `projects/ontario-grid-decarbonization.html` | First published analysis (the project documented below) |
| `assets/css/site.css` | Site styles (light shell + dark dashboard panel) |
| `assets/js/ontario-data.js` | **Generated** chart data (do not hand-edit) |
| `assets/js/ontario-charts.js` | Chart.js rendering |
| `tools/build-site-data.mjs` | Regenerates `ontario-data.js` from the fact tables |
| `CNAME` / `.nojekyll` | GitHub Pages custom-domain + raw-serve config |
| *(everything below)* | The data pipeline & star-schema model — see next section |

### Develop locally
Any static server works (the dashboard fetches no files at runtime; data is inlined):
```bash
npx serve .            # then open http://localhost:3000
# or:  python -m http.server 8000
```

### Regenerate the chart data (after re-running the ETL)
```bash
node tools/build-site-data.mjs   # reads Fact_Generation_ON_*.csv -> assets/js/ontario-data.js
```

### Deploy to GitHub Pages + jfrahmadii.xyz
1. Create a GitHub repo and push this folder to `main`.
2. **Settings → Pages →** Source: `Deploy from a branch`, Branch: `main` / `/ (root)`.
3. **Settings → Pages → Custom domain:** enter `jfrahmadii.xyz` (the `CNAME` file is already committed).
4. At your domain registrar, point DNS at GitHub Pages:
   - Apex `@` → four `A` records: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
     (and/or four `AAAA` records: `2606:50c0:8000::153` … `8003::153`).
   - `www` → `CNAME` → `<your-github-username>.github.io`.
5. Back in **Settings → Pages**, tick **Enforce HTTPS** once the cert is issued (can take ~15–30 min).

> Before pushing, update the placeholder links (search the HTML for `EDIT:`): your
> GitHub username, LinkedIn URL, and confirm the display name/headline.

---

# Canada's Electricity Decarbonization Tracker — Data Model (v1)

**Stack:** Power BI / Microsoft Fabric · **Owner:** Jeff · **Scope:** Ontario vs Alberta

**The question:** *Which province is decarbonizing its electricity grid faster — Ontario or Alberta — and what's driving it?*

This folder holds the import-ready **star schema** for the dashboard, plus the script that built it. Connect Power BI Desktop to these CSVs and start modeling.

---

## 1. Files

| File | Role | Grain |
|---|---|---|
| `Dim_Date.csv` | Date dimension (daily, 1990–2026) | one row per day |
| `Dim_Province.csv` | Province dimension | one row per province |
| `Dim_FuelType.csv` | Fuel dimension | one row per fuel |
| `Dim_Generator.csv` | Generator dimension (name → fuel) | one row per generator (191, IESO) |
| `Fact_Generation.csv` | Electricity generation | province × fuel × year |
| `Fact_Emissions.csv` | Power-sector emissions + grid intensity | province × year |
| `build_dataset.py` | Rebuilds everything; `--backfill` pulls full history | — |

---

## 2. Star schema

```
                 ┌───────────────┐
                 │   Dim_Date    │
                 │ DateKey (PK)  │
                 └──────┬────────┘
                        │ 1
            ┌───────────┴───────────┐
            │ *                   * │
  ┌─────────▼─────────┐   ┌─────────▼─────────┐
  │  Fact_Generation  │   │   Fact_Emissions  │
  │ ProvinceKey (FK)  │   │ ProvinceKey (FK)  │
  │ FuelKey     (FK)  │   │ DateKey     (FK)  │
  │ DateKey     (FK)  │   │ Emissions_tCO2e   │
  │ Generation_GWh    │   │ GridIntensity     │
  └────┬──────────┬───┘   └─────────┬─────────┘
       │ *        │ *               │ *
   ┌───▼─────┐ ┌──▼──────────┐ ┌────▼──────────┐
   │Dim_Fuel │ │Dim_Province │ │ Dim_Province  │
   │FuelKey  │ │ProvinceKey  │ │ (shared dim)  │
   └─────────┘ └─────────────┘ └───────────────┘
```

Relationships (all single-direction, one-to-many from dimension to fact):

- `Dim_Date[DateKey]` 1—* `Fact_Generation[DateKey]`
- `Dim_Date[DateKey]` 1—* `Fact_Emissions[DateKey]`
- `Dim_Province[ProvinceKey]` 1—* both facts
- `Dim_FuelType[FuelKey]` 1—* `Fact_Generation[FuelKey]`
- `Dim_Generator[GeneratorKey]` 1—* hourly parquet `[generator]` (plant-level drill-down);
  `Dim_FuelType[FuelKey]` 1—* `Dim_Generator[FuelKey]`

Mark `Dim_Date` as the date table in Power BI. `DateKey` is an integer (`YYYYMMDD`); facts key to year-end (`YYYY1231`) since the grain is annual.

---

## 3. Core DAX measures

```DAX
Total Generation (GWh) = SUM ( Fact_Generation[Generation_GWh] )

Renewable Generation (GWh) =
    CALCULATE ( [Total Generation (GWh)], Dim_FuelType[IsRenewable] = 1 )

Renewable Share % =
    DIVIDE ( [Renewable Generation (GWh)], [Total Generation (GWh)] )

-- Grid carbon intensity, gCO2e/kWh (from Fact_Emissions)
Grid Intensity (gCO2e/kWh) =
    AVERAGE ( Fact_Emissions[GridIntensity_gPerKWh] )

-- Emissions intensity derived from facts (alt. cross-check):
-- tCO2e / GWh  ==  gCO2e / kWh   (unit identity)
Emissions Intensity (calc) =
    DIVIDE ( SUM ( Fact_Emissions[Emissions_tCO2e] ), [Total Generation (GWh)] )

YoY Δ Renewable Share =
    [Renewable Share %]
  - CALCULATE ( [Renewable Share %], DATEADD ( Dim_Date[Date], -1, YEAR ) )

Rolling 12-mo Grid Intensity =
    CALCULATE ( [Grid Intensity (gCO2e/kWh)],
        DATESINRANGE ( Dim_Date[Date], MAX(Dim_Date[Date]) - 365, MAX(Dim_Date[Date]) ) )

-- Province ranking by decarbonization rate over the visible window:
Decarbonization Rank =
    RANKX ( ALL ( Dim_Province[Province] ),
            CALCULATE ( [Grid Intensity (gCO2e/kWh)],
                        LASTDATE ( Dim_Date[Date] ) )
          - CALCULATE ( [Grid Intensity (gCO2e/kWh)],
                        FIRSTDATE ( Dim_Date[Date] ) ),
          , ASC )   -- biggest drop = rank 1
```

---

## 4. Headline insight (for the canvas)

> **Ontario built a near-zero grid; Alberta is the one now moving fastest.**
> Ontario's grid intensity fell from 220 → **35 gCO₂e/kWh** (2005→2022) after phasing out coal by 2014 — it is essentially decarbonized. Alberta started far dirtier (**910 gCO₂e/kWh** in 2005) but, after completing its **coal-to-gas phase-out in June 2024** and rapid wind/solar growth, gas now supplies ~75% of generation and intensity has roughly halved to **470 gCO₂e/kWh**. The next decade's decarbonization story is Alberta's to write.

---

## 5. Data provenance & coverage

| Metric | Coverage in seed | Source |
|---|---|---|
| Generation mix (GWh by fuel) | 2021, both provinces (exact, reconciles to published totals) | CER Provincial Energy Profiles |
| Grid intensity (gCO₂e/kWh) | 1990 / 2005 / 2022 anchors, both provinces | ECCC NIR via CER profiles |
| Power-sector emissions (tCO₂e) | 2022, both provinces (ON 3.8 Mt, AB 19.4 Mt) | ECCC NIR via CER profiles |

`SourceFlag` column on each fact row: `CER` / `CER/ECCC` = published figure; `EST` = my allocation of a stated residual (Ontario's ~9% gas+bio split, Alberta's ~1% solar/other). Replace `EST` rows with exact values via the backfill step.

**Backfill to full history (2005–2022):**
```bash
python build_dataset.py --backfill
```
This downloads the CER "Figure Data" trend CSVs (generation `figure-02`, intensity `figure-09`) for each province, prints their headers, and is wired to expand the facts to the full annual series. (Those files are served as binary downloads, so they're fetched here rather than through the chat tools.)

### Sources (cite these on the dashboard footer)
- CER — Ontario Energy Profile: https://www.cer-rec.gc.ca/en/data-analysis/energy-markets/province-territory-energy-profiles/ontario.html
- CER — Alberta Energy Profile: https://www.cer-rec.gc.ca/en/data-analysis/energy-markets/province-territory-energy-profiles/alberta.html
- ECCC — National Inventory Report 1990–2022: https://www.canada.ca/en/environment-climate-change/services/climate-change/greenhouse-gas-emissions/inventory.html
- AESO — 2024 Annual Market Statistics: https://www.aeso.ca/market/market-and-system-reporting/annual-market-statistic-reports/
- IESO — Year-End Data: https://www.ieso.ca/corporate-ieso/media/year-end-data

---

## 5b. Ontario real generation pipeline — IESO (recommended source)

`Extract_Transform_data.py` is a production ETL that replaces the 2021 seed with
**real hourly generation** for Ontario, May 2019 → present, straight from the IESO
public reports site. It is the credible, recruiter-legible backbone for the
Ontario side of the dashboard.

Source: `https://reports-public.ieso.ca/public/GenOutputCapabilityMonth/`
(Generator Output Capability — monthly CSVs, hourly, per generator, by fuel type).

Run it (on your machine — it downloads ~85 monthly files):
```bash
pip install requests pandas pyarrow
python Extract_Transform_data.py --aggregate-after
```
This (1) extracts each month to Hive-partitioned Parquet under `parquet/year=/month=`,
then (2) rolls hourly `output_mw` up to **province × fuel × period GWh**, writing:

- `Fact_Generation_ON_monthly.parquet` / `.csv` — monthly grain
- `Fact_Generation_ON_annual.parquet` / `.csv` — annual grain (year-end DateKey,
  `SourceFlag = IESO`), drop-in compatible with `Fact_Generation` in the schema.

Point Power BI / Fabric at the Parquet (native connector) instead of static CSV.

**Two real bugs were found and fixed by validating against an actual April-2025 file**
(our Goal→Mistake→Root-cause→Plan→Execute loop in action):

1. *Column shift.* Data rows carry a trailing comma (29 fields) but the header has
   28, so pandas silently promoted the first column to the index and shifted every
   column left by one — corrupting every field. Fixed with `index_col=False`.
2. *String aggregation.* Offline units leave blank/whitespace hour cells, so
   `output_mw` loaded as text and would concatenate instead of sum. Fixed by
   coercing values to numeric.

Validation on a real 2-day sample confirmed Nuclear is the largest fuel (as
expected for Ontario) and fuel keys map cleanly to `Dim_FuelType`.
`_sample_real_rows.csv` is kept as the test fixture.

> Alberta has no equivalent free hourly generator feed; keep Alberta on the CER
> annual figures (the seed + `build_dataset.py --backfill`). The model already
> supports mixed `SourceFlag`s per province.

---

## 5c. Reconciliation — IESO grid-connected vs CER total generation

A quick cross-check that the IESO pipeline produces trustworthy totals. IESO
annual generation (sum of hourly `output_mw` / 1000) vs Canada Energy Regulator
published Ontario **total** generation:

| Year | IESO grid-connected (TWh) | CER total generation (TWh) | Notes |
|---|---|---|---|
| 2019 | 98.1 | — | **partial** — feed starts May 2019 |
| 2020 | 146.8 | — | |
| 2021 | 141.9 | **148.3** | gap ≈ 6.4 TWh (4.3%) = embedded generation |
| 2022 | 146.4 | — | |
| 2023 | 148.6 | — | |
| 2024 | 156.6 | — | mix: nuclear 51% / hydro 24% / gas 16% / wind 8.5% |
| 2025 | 162.4 | — | first year `OTH` appears (178 GWh) |
| 2026 | 77.0 | — | **partial** — year in progress |

**Why IESO < CER (and why that's expected, not a bug):** the IESO Generator
Output Capability report covers **transmission-connected** generators only. It
excludes **distribution-connected / embedded** generation — most of Ontario's
rooftop and small-scale solar, plus some small hydro and behind-the-meter bio.
CER itself notes Ontario had ~2,171 MW of distribution-connected solar vs only
478 MW transmission-connected, so IESO's solar line (~0.7 TWh in 2024) is
structurally low against true provincial solar. The steady ~4% gap in the one
year with a hard CER anchor (2021) is consistent with that embedded slice.

**Implication for the dashboard:** label the IESO series precisely as
*"transmission-connected generation (IESO)"* rather than *"Ontario total."* It is
the right, defensible basis for the **grid generation mix** and the
decarbonization narrative; for absolute provincial totals, cite CER. Backfilling
the CER annual trend (`build_dataset.py --backfill`) adds the 2005–2021 CER
totals so this table can be completed for every year.

---

## 6. Next steps (per the spec timeline)

- **Wk 2:** Load these into Power BI, build relationships, implement the measures above. Run `--backfill` to get the full time series.
- **Wk 3:** MVP visuals — generation mix (100% stacked area) + intensity trend line + renewable-share KPI cards; add the headline insight; publish to web.
- **Wk 4:** LinkedIn write-up + repo README, link from resume.
