# Request 15: open data for the map and site scoring (a task list for the team)

- **To:** the Grid Atlas team member who owns open data and the basemap: [name, phone]
- **From:** Grid Atlas team lead
- **Date:** Monday 2 November 2026
- **Due:** Friday 6 November 2026, the end of build week 1. Do items 4 and 5 first: the week-1 map page needs the hillshade and the OpenStreetMap layers.
- **Template:** `templates/T10_growth.xlsx`, sheet `growth_rates`, for item 7 only. The other items are files, each recorded in the `manifest.toml` of its folder under `data/open/layers/`.

This is a task list for the team, not a request to anyone outside it. It lists the open datasets we fetch ourselves and the licence terms we must keep.

## Why we need it
These datasets give the map its hillshade, lakes, roads, towns and district lines (demo item 1), served from our own server, which has no internet. They also feed the site ranking (demo item 4, acceptance criterion 5): the Limits exclusion and the terrain, people, economy and logistics factors (review findings DG-13 and DG-14). Item 7 sets the growth behind every 2030 figure.

## What to send
For every item: fetch it on the team Mac, keep the original file unchanged, check its licence before any use, and record it in the manifest (see "How to deliver"). Keep national files whole and clip only derived layers. The study area for clipping is every district that holds a Central substation or a candidate site, plus 50 km, because the site metrics look up to 50 km away. The Bujagali and Nalubaale delivery points count as Central; the Mbarara tie and the Karuma infeed do not.

### 1. District and sub-county boundaries (UBOS)
- **What:** polygons for districts and sub-counties, with their names and codes, and each sub-county's district. They must be the same units as the Census 2024 tables in item 2.
- **From, in order:**
  1. Boundaries that UBOS has released for Census 2024: look on the census page (`https://www.ubos.org/nphc-2024-census-page/`) and UBOS's map portal.
  2. The HDX copy of Uganda's administrative boundaries, which comes from UBOS (`https://data.humdata.org/dataset/cod-ab-uga`). Check its date: it may be older than the 2024 units.
- **Format:** GeoPackage, or a zipped Shapefile with its `.prj`, as received. Put the EPSG code in the manifest.
- **Licence:** not confirmed. Read the terms on the UBOS site and the licence field on the HDX page, and record both (question 1). Until they are confirmed, show the boundaries on our map with the credit "Boundaries: Uganda Bureau of Statistics (UBOS)", and do not give the files to anyone outside UETCL.
- **Used for:** the Central study polygon that clips the other layers; district and sub-county names in the site details; the units that population (item 2) and GDP (item 6) attach to.

### 2. Census 2024 population (UBOS)
- **What:** total population per sub-county and per district from the National Population and Housing Census 2024, final results. Also the population aged 15 to 64 per sub-county, if the tables give it.
- **From, in order:**
  1. The sub-county profile Excel tables on the UBOS census page.
  2. The sub-region census profile reports (PDF) that cover the Central districts.
  3. District totals from the Census 2024 final report.
- **Format:** keep the files as downloaded. Then make one CSV with one row per sub-county: `district`, `sub_county`, `census_code` (if given), `population_total`, `population_15_64` (if given) and `source_table`. Counts in persons, not thousands.
- **Licence:** as item 1: UBOS's terms are not confirmed. Credit "Source: UBOS, National Population and Housing Census 2024". Use the published totals only.
- **Used for:** the people factor and the demand-and-markets factor: the population within 20 km and within 50 km of each site.

### 3. Protected areas and wetlands (UWA, NFA, MWE and NEMA)
- **What:** polygons, each with its name and type, of national parks, wildlife reserves and other protected areas (Uganda Wildlife Authority, UWA); central forest reserves (National Forestry Authority, NFA); and mapped wetlands (Ministry of Water and Environment, MWE, and the National Environment Management Authority, NEMA). Not UNRA: it is the roads authority and does not hold these layers. The scope of work names it by mistake.
- **From, in order:**
  1. A copy UETCL already holds. Ask the Planning GIS unit (request 4), and whoever handles environmental studies for line routes, what they hold and on what terms.
  2. The holders' own published layers, or a short request from the sponsor to UWA, NFA and MWE/NEMA.
  3. For the demo, if neither arrives this week: the protected-area, nature-reserve, forest-reserve and wetland polygons in the OpenStreetMap extract (item 5), labelled "OpenStreetMap, not official boundaries".
- **Format:** GeoPackage, or a zipped Shapefile with its `.prj`.
- **Licence:** whatever each holder states. Record it, and use the layer only as the holder allows. The OpenStreetMap fallback is under the ODbL (item 5).
- **Protected Planet (WDPA): do not download it for use.** Its terms require UNEP-WCMC's prior written permission for any use that informs or assists a commercial entity, and UETCL is a limited company. They also forbid passing the data on, in whole or in part, including through interactive web maps. Use it only if the sponsor gets that permission in writing. Even then it never goes into an export, and it goes on no map shown outside UETCL unless the permission covers that.
- **Used for:** the Limits factor. It is a hard exclusion (at present, a site overlapping protected land or wetland by more than 5 % is dropped), plus the distance to the nearest one. Wetlands may also stand in for flood-prone land (question 9).

### 4. Elevation for the hillshade and slope (Copernicus GLO-30, or SRTM 30 m)
- **What:** a 30 m elevation model covering longitude 31° to 34° E and latitude 1° S to 2° N, with heights in metres. That is nine 1° tiles.
- **From:** Copernicus DEM GLO-30, from the public bucket `copernicus-dem-30m`. No login is needed; see `https://copernicus-dem-30m.s3.amazonaws.com/readme.html`. Tiles are named by their south-west corner, for example `Copernicus_DSM_COG_10_N00_00_E032_00_DEM`. We need latitudes `S01`, `N00` and `N01`, each with longitudes `E031`, `E032` and `E033`. SRTM 1 arc-second from USGS EarthExplorer is an acceptable alternative, but it needs a login.
- **Format:** GeoTIFF, as downloaded.
- **Then:** run `scripts/make_basemap.sh` in the GDAL container. It makes the hillshade tiles (zoom 7 to 13) and the slope in percent (in EPSG:32636). Never use an online terrain or tile service.
- **Licence:** Copernicus allows any use, including giving out and changing the data, on these conditions:
  1. With the elevation data itself, show: "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved".
  2. With our hillshade and slope, show: "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved".
  3. On the About page, add: "The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30."
  4. Never suggest that ESA or the EU endorses the Atlas.

  SRTM, if used, is US government data with open distribution. Cite USGS (doi:10.5066/F7PR7TFT).
- **Used for:** the hillshade under the map (demo item 1) and the terrain factor (the mean slope at each site). Elevation does not give flood risk (question 9).

### 5. Roads, rail, water, towns and ports (OpenStreetMap)
- **What:** from one Uganda extract:
  - roads: motorway, trunk, primary, secondary and tertiary;
  - railways, including any SGR alignment (it may be tagged as under construction or proposed). Compare it with the SGR traction points Planning sends under request 10;
  - lakes and rivers;
  - cities and towns;
  - lake ports;
  - for item 3's fallback: protected areas, forest reserves and wetlands.
- **From:** Geofabrik's public extract, `https://download.geofabrik.de/africa/uganda-latest.osm.pbf`. Record the data date shown on the Geofabrik page.
- **Format:** `.osm.pbf`, as downloaded. `scripts/make_basemap.sh` turns it into GeoPackages for PostGIS and simplified GeoJSON for the map.
- **Never use `tile.openstreetmap.org`.** Its policy forbids bulk downloads, prefetching and offline use, and our server has no internet anyway. We draw the OpenStreetMap data ourselves.
- **Licence:** Open Database License (ODbL) 1.0.
  - Show "© OpenStreetMap contributors", linked to `https://www.openstreetmap.org/copyright`, in a corner of the map and on the About page. Put the same credit in the README of every export that holds data derived from OpenStreetMap.
  - Share-alike: maps and pictures need only the credit. Data derived from OpenStreetMap that we give outside UETCL must be offered under the ODbL too, for example a clipped road layer, or road distances in a site export.
  - So keep OpenStreetMap layers in their own tables. Never merge them into UETCL network tables.
- **Used for:** the basemap (demo item 1); the logistics factor (distance to a trunk road, to the railway or SGR, and to a lake port); the demand-and-markets factor (road distance to Kampala); and the fallback for item 3.

### 6. District GDP (the Pardee Center study for USAID)
- **What:** *Estimating District GDP in Uganda*, by the Frederick S. Pardee Center for International Futures (now the Pardee Institute), University of Denver, prepared for USAID, November 2017.
  - Annex A, Table 2 (pages 15 to 18) gives GDP (million US$) and GDP per capita (US$) for 116 units: 115 districts plus Kampala, as of 30 June 2017.
  - The figures are for 2014, in 2011 US$ at market exchange rates.
- **From:** the PDF on the University of Denver's Pardee pages (`https://korbel.du.edu/pardee/resources/estimating-district-gdp-uganda`), also on SSRN (abstract 3941446). Do not count on a USAID-hosted copy still being online.
- **Format:** keep the PDF. Type Table 2 into a CSV with the columns `district`, `gdp_musd`, `gdp_per_capita_usd` and `page`. A second team member checks every row against the PDF.
- **Licence:** the document states none. Treat it as the authors' copyright: cite it in full wherever one of its figures is used, use the figures in scoring, and do not publish the typed table as a dataset.
- **Caveats for the sites method note:**
  - The figures are modelled from night-time lights and farm data. They are not official statistics.
  - They are for 2014.
  - Districts and cities created since June 2017 need a rule to take a share of their parent's figure (question 11).
- **Used for:** the economy factor (each district's share of GDP).

### 7. Demand growth rates for 2030 (template T10)
- **What:** the compound growth rate of peak demand, in percent per year, that grows today's substation loads to 2030: low, base and high, each with its source.
- **Template:** `templates/T10_growth.xlsx`, sheet `growth_rates`. Your native format is welcome; the template lists the minimum fields. Its README sheet sets the rules: one rate per scope and scenario, no double counting of the large loads in T08, and a source on every row.
- **From, in order:**
  1. Planning's own load forecast per bulk supply point (requests 2 and 3).
  2. The demand path in Uganda's National Energy Compact under Mission 300.
  3. The NDP IV growth targets, or UBOS GDP statistics, turned into a demand growth rate by a method you state.

  Keep a PDF of every source page used.
- **Minimum:** one Central base rate from 2026 to 2030, with its source.
- **Licence:** the published documents are public; cite them. Planning's forecast is internal UETCL data: it stays with the other UETCL data and never goes into `data/open/`.
- **Used for:** the 2030 stop on the map, the MW each site can take in 2030 (criterion 5), and the years of growth left at Kawanda. If Planning's 2030 case arrives, its loads replace the rate in the 2030 case, but the Kawanda page still uses the rate.

### Licences and credits at a glance
| Item | Licence | Credit to show | Outside UETCL |
|---|---|---|---|
| 1, 2 UBOS boundaries and population | Not confirmed | "Source: Uganda Bureau of Statistics (UBOS)" | On our maps with the credit; no files until the terms are confirmed |
| 3 UWA, NFA, MWE and NEMA layers | As each holder states | As each holder asks | Only as the holder allows |
| 3 Protected Planet (WDPA) | Prior written permission needed; no passing on | The UNEP-WCMC and IUCN citation | Never in exports; on no outside map unless the permission covers it |
| 4 Copernicus GLO-30 | Any use, with the notices | The two Copernicus notices and the liability sentence | Yes, with the notices |
| 4 SRTM, if used | US government, open | USGS citation | Yes |
| 5 OpenStreetMap | ODbL 1.0 | "© OpenStreetMap contributors", linked | Maps with the credit; derived data only under the ODbL |
| 6 Pardee district GDP | None stated: the authors' copyright | Full citation | The figures with a citation; not the typed table |
| 7 Growth sources | Public documents; Planning's forecast is internal | Citation | Planning's figures only once cleared |

Anything shown outside UETCL also needs clearance at the management preview on Friday 20 November.

## Questions to answer
Record the answers in each dataset's `manifest.toml`, or in the sites method note where marked, by Friday 6 November.
1. For each dataset: what are the exact licence or terms, where did you read them, on what date, and what credit text must we show?
2. Do the boundary files use the same sub-counties, by name and code, as the Census 2024 tables? List each mismatch and how you resolved it.
3. Which districts make up the study area? Check that every Central substation and every candidate site falls inside. In particular, confirm the districts of Kapeeka and Kabulasoke: we expect Nakaseke and Gomba.
4. Is the population aged 15 to 64 published per sub-county? If not, the people factor uses total population: tell the sites owner.
5. Does UETCL already hold UWA, NFA or MWE/NEMA layers, and on what terms? If not, does the sponsor want to ask the holders, or do we use the OpenStreetMap fallback for the demo?
6. Once question 5 is settled, is WDPA needed at all? If it is, what exactly does UNEP-WCMC's written permission allow?
7. Which elevation product and tiles did you use, and what CRS and vertical datum does `gdalinfo` report?
8. What is the data date of the OpenStreetMap extract, and which tags did you keep for each layer?
9. Flood risk: no flood dataset is on this list. With the sites owner, decide whether mapped wetlands stand in for flood-prone land, or flood is dropped from the terrain factor. Record the decision in the sites method note.
10. Poverty: UNHS poverty figures are published by sub-region, so they barely separate sites in Central. Do we drop poverty from MVP scoring, or apply it per sub-region with a note? Record the decision in the sites method note.
11. Which current districts and cities did not exist in June 2017, and what rule gives them a GDP figure (for example, a share of the parent's figure by Census 2024 population)? Record the rule in the sites method note.
12. Which source gives the base growth rate, and has the Planning mentor agreed it?

## What not to send
For this task, "send" means bringing a file into the project or the Atlas.
- **No personal data.** Use Geofabrik's public extract, which carries no contributor names or IDs. Never use the internal extract with full metadata, or the history file. Use population only as published totals: never census microdata, or any record about a household or a person.
- **No customer names.** If a layer names landowners, occupants or customers, delete those fields before you file it.
- **No Protected Planet data** without UNEP-WCMC's written permission, and none in exports even then.
- **No online map tiles or imagery.** Nothing from `tile.openstreetmap.org`, Google, Bing or any other online map, and no tracing from their imagery.
- **No dataset whose licence you could not find.** Set it aside and tell the team lead.
- **No UETCL data in `data/open/`**, and no open data merged into UETCL network tables.

## How to deliver
Open data is public, but it travels by the same rules as everything else in the project, as the handling note (`handling-note.md`) sets out.
- Fetch everything on the team Mac, into the project folder. The NCC server has no internet. Open data reaches it only inside the release bundle that `./atlas bundle` writes to `dist/`. The bundle carries `data/open/` and `data/basemap/` with checksums, on the UETCL-issued release drive.
- Give each dataset its own folder: `data/open/layers/ubos_boundaries/`, `data/open/layers/ubos_census2024/`, `data/open/layers/protected_wetlands/`, `data/open/layers/dem/`, `data/open/layers/osm/` and `data/open/layers/pardee_gdp/` (contracts section 8 puts open context layers in `data/open/layers/`). The public source pages for item 7 go in `data/open/layers/growth_sources/`.
  - Keep each download unchanged, under its original name.
  - Clean CSVs and clipped layers go in a `derived/` folder inside the dataset's folder.
  - `scripts/make_basemap.sh` writes the hillshade tiles and the map layers to `data/basemap/`.
- Downloaded files are data. Never run a script that comes with them.
- Record every file in the `manifest.toml` in its dataset folder (the format is in `docs/dev/contracts.md` section 8):
  - the dataset and file name;
  - its sha256 (`shasum -a 256 <file>` on the Mac);
  - provenance `open`;
  - who fetched it (initials) and the date;
  - the source URL, and the version or data date;
  - the licence, the credit text and the CRS.

  The loader refuses any file that is missing from the manifest or has changed since.
- The T10 workbook, and any internal source behind it, goes to the Grid Atlas folder on the UETCL share or the landing folder on the Grid Atlas server. The handling note gives both locations.
- Never move any of these files by personal email, WhatsApp, personal cloud storage or a USB stick of unknown origin. Nothing goes into git: `data/` is git-ignored.

## Contact
[name, phone], Grid Atlas team: owner of this task list. Raise any doubt about a licence with them before the data is used.
