# jfrahmadii.xyz — Data Analytics Portfolio

Personal site — a publication of data-driven analysis (static HTML/CSS/JS,
deployed on **GitHub Pages** at **[jfrahmadii.xyz](https://jfrahmadii.xyz)**).
Each published piece is a page under `projects/`; the data work behind a piece
lives under `analysis/` (or in its own dedicated repo when the project predates
this site).

## Layout

| Path | What it is |
|---|---|
| `index.html` | Home — intro, writing feed, about |
| `projects/ontario-grid-decarbonization.html` | Published analysis — Ontario's grid |
| `projects/firefighters-montreal.html` | Published analysis — Montreal road emergencies (embeds two Tableau Public dashboards; code lives in the separate `firefighters-interventions` repo) |
| `assets/css/site.css` | Site styles (light shell + dark dashboard panel) |
| `assets/js/ontario-data.js` | **Generated** chart data — do not hand-edit |
| `assets/js/ontario-charts.js` | Chart.js rendering |
| `tools/build-site-data.mjs` | Regenerates `ontario-data.js` from the fact tables |
| `analysis/ontario-grid/` | Data project behind the Ontario piece (ETL, star schema, Power BI guide) — see its [README](analysis/ontario-grid/README.md) |
| `CNAME` / `.nojekyll` | GitHub Pages custom-domain + raw-serve config |

The site reads no data at runtime — every chart is inlined into
`assets/js/ontario-data.js`, so nothing in `analysis/` is on the critical path
for the live site. It is kept in the repo for reproducibility.

### Develop locally
Any static server works:
```bash
npx serve .            # then open http://localhost:3000
# or:  python -m http.server 8000
```

### Regenerate the chart data (after re-running the ETL)
```bash
node tools/build-site-data.mjs   # reads analysis/ontario-grid/Fact_Generation_ON_*.csv -> assets/js/ontario-data.js
```

### Deploy to GitHub Pages + jfrahmadii.xyz
1. Push to `main` on the GitHub repo backing the site.
2. **Settings → Pages →** Source: `Deploy from a branch`, Branch: `main` / `/ (root)`.
3. **Settings → Pages → Custom domain:** `jfrahmadii.xyz` (the `CNAME` file is already committed).
4. At the domain registrar, point DNS at GitHub Pages:
   - Apex `@` → four `A` records: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
     (and/or four `AAAA` records: `2606:50c0:8000::153` … `8003::153`).
   - `www` → `CNAME` → `jfrahmadii.github.io`.
5. Back in **Settings → Pages**, tick **Enforce HTTPS** once the cert is issued (~15–30 min).
