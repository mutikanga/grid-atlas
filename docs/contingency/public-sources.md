# Public sources: published figures for the Grid Atlas fallback

**What this is.** These are figures we found in public documents, for use at provenance level PUBLIC (`provenance = "open"`) under `docs/contingency-plan.md`. Each one carries its source. Nothing in this file is estimated. Two rows say **derived**, which means simple arithmetic on two published figures from the same document, and the row shows the working. If we did not find a figure, it says **not found**. In that case we leave it blank rather than guess.

**Researched:** 1 November 2026. The machine-readable copy is `docs/contingency/public-figures.csv`, with one row per numeric figure.

**Confidence**
- **high**: read directly in an official ERA or UETCL document.
- **medium**: reputable press quoting ERA, UETCL, UEDCL or the Ministry, or a secondary source that agrees with an official one.
- **low**: a single secondary source, undated, or not checked against an official document.

**Two warnings for anyone using these numbers**
1. **Calendar year and financial year are different periods.** ERA's ESI performance reports use the calendar year (Jan to Dec). UETCL's annual reports use the financial year (Jul to Jun). Never mix them in one series.
2. **The quarterly tariff-review figures for energy and sales are ERA forecasts, annualised.** They are not metered actuals. Their peak-demand figures, by contrast, are actuals that ERA took from UETCL's system summaries.

**Spot-check (1 Nov 2026, independent checker).** We fetched the sources again and compared values:
- **ERA-TRR-Q3-26 (PDF):** these all match: peaks and exports for Apr and May 2026, shoulder, off-peak and minimum demand, load shedding and its causes, Table 3 plant capacities and purchases (Karuma, Bujagali, Nalubaale + Kiira, Isimba, Kabulasoke, Nkonge, Tororo), Table 5 loss factors, Table 12 BST 342.3 / 269.8 / 189.9 and total costs. The check also found five monthly peaks printed as chart labels (section 2), which had been marked not found.
- **ERA-ESI-24 (PDF):** these all match: installed capacity 2,052.7 / 1,847.5 MW and the 2024 split, peaks 1,117.9 / 972.9 MW, purchases 6,622.6 GWh, sales 6,301.1 GWh, losses 4.85%, purchases by source, and energy generated.
- **MON-0511:** these match: about 2,098 MW installed, about 1,550 MW firm, and the 1,337.15 MW peak.
- **MON-0504:** these match: substation loading, 36 of 94 transformers, 6.93 GWh and 12.75 GWh, monthly purchases, UEDCL demand, and 7,827.5 GWh generation. The interruption and busbar figures were not re-checked.
- **PL-0513:** 137 km, 220 kV double circuit, and Kawanda upgraded from 132/33 kV to 220 kV.
- **UETCL-KMP:** the progress percentages match. The Bujagali 250 MVA figure is not on that page, so it is marked unverified (section 8).
- **WIKI-NK:** the capacity and district match. The connecting line is not stated there (section 7).

The UETCL annual report and strategic plan were not re-fetched in this check.

## Source list

| Key | Publisher | Title | Date | URL |
|---|---|---|---|---|
| ERA-TRR-Q3-26 | ERA | Tariff Review Report for the Third Quarter (July to September) of 2026, ref REP/25/026/058 | 2026-06-24 | https://www.era.go.ug/download/tariff-review-report-for-the-third-quarter-july-to-september-of-2026/ |
| ERA-TRR-Q2-26 | ERA | Main Grid Tariff Review Report for the Second Quarter (April to June) of 2026 | 2026-03-25 | https://www.era.go.ug/download/main-grid-tariff-review-report-for-the-second-quarter-april-to-june-of-2026/ |
| ERA-TRR-Q1-26 | ERA | Main Grid Tariff Review Report for the First Quarter (January to March) of 2026 | 2026-03-23 (as printed) | https://www.era.go.ug/download/main-grid-tariff-review-report-for-the-first-quarter-january-to-march-of-2026/ |
| ERA-TRR-Q4-25 | ERA | Main Grid Tariff Review Report for the Fourth Quarter (October to December) of 2025 | 2025-09-26 | https://www.era.go.ug/download/main-grid-tariff-review-report-for-the-fourth-quarter-october-to-december-of-2025/ |
| ERA-ESI-24 | ERA | Electricity Supply Industry Performance Report for the Year 2024, ref REP/83/114/57/025/037 | 2025-05-14 | https://www.era.go.ug/download/electricity-supply-industry-performance-report-for-the-year-2024-2/ |
| ERA-AR-25 | ERA | Annual Integrated Report for the financial year ended 30 June 2025 | FY2024/25 (publication date not printed) | https://www.era.go.ug/download/annual-integrated-report-for-the-financial-year-ended-30th-june-2025/ |
| UETCL-AR-25 | UETCL | Annual Report FY 2024/2025 (period ended 30 June 2025) | posted 2026-03-30 | https://uetcl.go.ug/2026/03/30/uetcl-annual-report-for-the-period-ended-30th-june-2025/ |
| UETCL-SP | UETCL | Corporate Strategic Plan 2025/26–2029/30, Abridged Version | uploaded 2026-02 | https://uetcl.go.ug/wp-content/uploads/2026/02/UETCL-Strategic-Plan-2025-30-Abridged-Version_.pdf |
| UETCL-KMP | UETCL | Kampala Metropolitan Transmission System Improvement Project (project page) | progress to Jan–Feb 2026 | https://uetcl.go.ug/project/kampalametroproject/ |
| UETCL-AGM | UETCL | UETCL convenes 17th Annual General Meeting | 2026-03-27 | https://uetcl.go.ug/2026/03/27/uetcl-convenes-17th-annual-general-meeting/ |
| MON-0511 | Daily Monitor (P. Wafula) | Kenya targets more Ugandan electricity in 2027 | 2026-05-11 | https://www.monitor.co.ug/uganda/news/national/kenya-targets-more-ugandan-electricity-in-2027-5454454 |
| MON-0504 | Daily Monitor | The troubles at UEDCL that got bosses sacked | 2026-05-04 | https://www.monitor.co.ug/uganda/news/national/the-troubles-at-uedcl-that-got-bosses-sacked-5445982 |
| MON-1002 | Daily Monitor (R. Nabisubi) | UEDCL rolls out massive infrastructure upgrades to fix Greater Kampala power outages | 2026-10-02 | https://www.monitor.co.ug/uganda/news/national/uedcl-rolls-out-massive-infrastructure-upgrades-to-fix-greater-kampala-power-outages-5617548 |
| MON-0606 | Daily Monitor (J. Bwire, S. Otage) | National grid failure triggers widespread blackout across Uganda | 2026-06-06 | https://www.monitor.co.ug/uganda/news/national/total-darkness-in-uganda-national-grid-collapse-revives-fears-of-poor-power-service-5486752 |
| MON-REG | Daily Monitor | Power cuts to ease in six months, says regulator | undated in search result | https://www.monitor.co.ug/uganda/business/markets/power-cuts-to-ease-in-six-months-says-regulator--5644452 |
| PLUS-1231 | Plus News | Electricity Tariffs Remain Unchanged for Next Quarter as Gov't Promises Better Service | 2025-12-31 | https://plusnews.ug/?p=36426 |
| BT-1213 | Business Times Uganda | Inside the Shs1.7Tn power companies' applications to ERA to set end-user tariffs | 2023-12-13 | https://businesstimesug.com/inside-the-shs1-7tn-power-companies-applications-to-era-to-set-end-user-tariffs/ |
| BT-0330 | Business Times Uganda | UETCL sustains growth, expanded capacity | 2024-03-30 | https://businesstimesug.com/uetcl-sustains-growth-expanded-capacity/ |
| PL-0513 | Powerline (India) | Uganda's UETCL commissions 220 kV Kawanda–Masaka line | 2019-05-13 | https://powerline.net.in/2019/05/13/ugandas-uetcl-commissions-220-kv-kawanda-masaka-line/ |
| WIKI-PS | Wikipedia | List of power stations in Uganda | accessed 2026-11-01 | https://en.wikipedia.org/wiki/List_of_power_stations_in_Uganda |
| WIKI-NK | Wikipedia | Nkonge Solar Power Station | accessed 2026-11-01 | https://en.wikipedia.org/wiki/Nkonge_Solar_Power_Station |
| WIKI-KB | Wikipedia | Kawanda–Birembo High Voltage Power Line | accessed 2026-11-01 | https://en.wikipedia.org/wiki/Kawanda%E2%80%93Birembo_High_Voltage_Power_Line |
| WIKI-NMV | Wikipedia | Namanve | accessed 2026-11-01 | https://en.wikipedia.org/wiki/Namanve |
| UIA-KAP | Uganda Investment Authority | Kapeeka Industrial Park: From rural farmland to 34 factories in 10 years | c. Dec 2025 (10th anniversary) | https://ugandainvest.go.ug/kapeeka-industrial-park-from-rural-farmland-to-34-factories-in-10-years/ |
| UEGCL-NMV | UEGCL | Natural Resources Committee conducts an oversight visit to Namanve TPP (50 MW) | 2025-02 (visit 14 Feb 2025) | https://uegcl.com/natural-resources-committee-conducts-an-oversight-visit-to-namanve-tpp-50-mw/ |

## 1. Installed capacity

| Figure | Value | Unit | Period | Source | Confidence |
|---|---|---|---|---|---|
| National installed generation capacity | 2,052.7 | MW | end 2024 (CY) | ERA-ESI-24, Table 1 | high |
| …of which on-grid | 2,049.0 | MW | end 2024 | ERA-ESI-24, Table 1 | high |
| …hydro / thermal / solar PV / bagasse | 1,715.1 / 100.0 / 88.3 / 148.9 | MW | end 2024 | ERA-ESI-24, Table 2 | high |
| National installed generation capacity | 1,847.5 | MW | end 2023 | ERA-ESI-24, Table 1 | high |
| National installed generation capacity | 2,094.6 | MW | 2025 (ERA report year; prior-year comparator 2,048.5 MW) | ERA-AR-25, Performance highlights | high |
| Installed capacity (UETCL basis) | 2,037.5 | MW | FY2024/25 (from 2,026.7 MW in FY2023/24) | UETCL-AR-25, p.12 | high |
| Installed capacity, as quoted in press | about 2,098 | MW | 2026-05 | MON-0511; also PLUS-1231 (ERA CEO) | medium |
| Available firm capacity | about 1,550 | MW | 2026-02 | MON-0511 (citing UETCL) | medium |
| System reserve margin | 12.83 | % | FY2024/25 baseline | UETCL-SP, Table 3 | high |
| Installed capacity 2026 | not found | | 2026 | No official 2026 figure seen beyond the press figure above | |

## 2. Peak demand

ERA takes system peak from UETCL system summaries. "System" includes exports; "domestic" excludes them.

| Figure | Value | Unit | Period | Source | Confidence |
|---|---|---|---|---|---|
| System peak demand (domestic + exports) | 987.8 | MW | 2023 (Dec 2023) | ERA-ESI-24, summary table | high |
| Domestic peak demand | 867.9 | MW | 2023 | ERA-ESI-24 | high |
| System peak demand | 1,117.9 | MW | 2024 (Dec 2024) | ERA-ESI-24, summary table and Fig. 3 | high |
| Domestic peak demand | 972.9 | MW | 2024 (Dec 2024) | ERA-ESI-24 | high |
| System peak demand | 1,000.12 | MW | 2024-07 | ERA-TRR-Q4-25, s.3.1 | high |
| System peak demand | 1,095.98 | MW | 2024-11 | ERA-TRR-Q1-26, s.2.1 | high |
| Domestic peak demand | 944.57 | MW | 2024-11 | ERA-TRR-Q1-26, s.2.1 | high |
| Maximum system demand | 1,029.9 | MW | FY2023/24 | UETCL-AR-25, p.12 | high |
| Maximum system demand | 1,202.9 | MW | FY2024/25 | UETCL-AR-25, p.10 and p.12; UETCL-AGM | high |
| Maximum domestic demand | 1,044.2 | MW | FY2024/25 | UETCL-AR-25, p.12 | high |
| System peak demand | 1,202.85 | MW | 2025-06 | ERA-TRR-Q4-25, s.3.1 | high |
| Domestic peak demand | 1,023.21 | MW | 2025-06 | ERA-TRR-Q4-25 | high |
| System peak demand | 1,287.43 | MW | 2025-07 (29 Jul) | ERA-TRR-Q4-25 | high |
| Domestic peak demand | 1,069.50 | MW | 2025-07 | ERA-TRR-Q4-25 | high |
| Shoulder peak / off-peak max / minimum | 1,105.52 / 877.03 / 554.64 | MW | 2025-07 | ERA-TRR-Q4-25 | high |
| System peak demand | 1,335.80 | MW | 2025-09 | ERA-TRR-Q1-26, s.2.1 | high |
| Domestic peak demand | 1,157.24 | MW | 2025-09 | ERA-TRR-Q1-26 | high |
| Maximum demand | 1,345.3 | MW | 2025-12 | Wikipedia UEDCL article (secondary, not checked against ERA) | low |
| System peak demand | 1,310.71 | MW | 2026-01 | ERA-TRR-Q2-26, s.3.1 | high |
| Domestic peak demand | about 1,141.64 | MW | 2026-01 | ERA-TRR-Q2-26 | high |
| System peak demand | 1,337.15 | MW | 2026-02 (11 Feb) | ERA-TRR-Q2-26; also MON-0511 | high |
| Domestic peak demand | 1,187.68 | MW | 2026-02 | ERA-TRR-Q2-26 | high |
| Shoulder peak / off-peak max / minimum | 1,223.74 / 1,089.04 / 667.99 | MW | 2026-02 | ERA-TRR-Q2-26 | high |
| System peak demand | 1,375.614 | MW | 2026-04 | ERA-TRR-Q3-26, s.3.1 | high |
| Domestic peak demand | 1,197.84 | MW | 2026-04 | ERA-TRR-Q3-26 | high |
| System peak demand | 1,388.44 | MW | 2026-05 (11 May) | ERA-TRR-Q3-26, s.3.1 | high |
| …exports within that peak (TZ / KE / RW) | 26.69 / 100.02 / 83.79 | MW | 2026-05 | ERA-TRR-Q3-26 | high |
| Domestic peak demand | 1,199.53 | MW | 2026-05 | ERA-TRR-Q3-26 | high |
| Shoulder peak / off-peak max / minimum | 1,302.12 / 1,034.92 / 740.52 | MW | 2026-05 | ERA-TRR-Q3-26 | high |
| System peak demand (domestic + export), from chart data labels | 1,329.27 / 1,297.52 / 1,350.61 / 1,345.28 / 1,330.67 | MW | 2025-08 / 2025-10 / 2025-11 / 2025-12 / 2026-03 | ERA-TRR-Q3-26, Figure 1 (p.3 of s.3; source given there: UETCL System Reports). The same labels repeat the text values for Jul 2025, Sep 2025, Jan, Feb and Apr 2026, which confirms them. The Dec 2025 label also confirms the Wikipedia figure above. | high |
| Domestic peak demand for Aug 2025, Oct–Dec 2025, Mar 2026 | not found | | | Figure 1 of ERA-TRR-Q3-26 plots the domestic line without data labels. | |
| System and domestic peaks for Jun–Oct 2026 | not found | | | No Q4 2026 tariff review was online on 1 Nov 2026. | |
| Distribution-side demand (UEDCL) | 986.4 → 1,217.7 | MW | 2025-04 → 2026-03 | MON-0504 (citing a distribution sub-sector assessment) | medium |

## 3. Energy purchased, sent out, sold

| Figure | Value | Unit | Period | Source | Confidence |
|---|---|---|---|---|---|
| Energy generated to the grid | 6,788.5 | GWh | 2024 | ERA-ESI-24 | high |
| Energy generated to the grid | 6,032.3 | GWh | 2023 | ERA-ESI-24 | high |
| UETCL energy purchases | 6,622.6 | GWh | 2024 | ERA-ESI-24, s.2.2 and Table 4 | high |
| UETCL energy purchases | 6,027.8 | GWh | 2023 | ERA-ESI-24 | high |
| UETCL purchases: large hydro / small hydro / bagasse / thermal / solar / imports | 5,003.6 / 944.9 / 433.8 / 74.9 / 115.4 / 49.9 | GWh | 2024 | ERA-ESI-24, Table 4 | high |
| UETCL energy sales | 6,301.1 | GWh | 2024 | ERA-ESI-24, Table 5 | high |
| …to Umeme / exports / UEDCL / mini-grids | 5,572.0 / 478.1 / 223.4 / 27.6 | GWh | 2024 | ERA-ESI-24, Table 5 | high |
| UETCL energy purchases | 6,333.7 | GWh | FY2023/24 | UETCL-AR-25, p.12 | high |
| UETCL energy purchases | 7,055.2 | GWh | FY2024/25 | UETCL-AR-25, p.12 | high |
| UETCL energy sales | 6,031.1 | GWh | FY2023/24 | UETCL-AR-25 | high |
| UETCL energy sales | 6,745.08 | GWh | FY2024/25 | UETCL-AR-25; UETCL-AGM | high |
| UETCL exports | 535.9 | GWh | FY2024/25 (494.0 in FY2023/24) | UETCL-AR-25, p.14 | high |
| Domestic generation | 7,827.5 | GWh | 2025 | MON-0504 (citing a UEDCL report) | medium |
| Monthly energy purchases (UEDCL data) | 534.6 | GWh | 2025-01 | MON-0504 | medium |
| Monthly energy purchases (UEDCL data) | 622.7 | GWh | 2026-03 | MON-0504 | medium |
| Annualised purchases forecast (ERA) | 9,092.49 | GWh | Q3 2026 forecast | ERA-TRR-Q3-26, Table 3 | high (as a forecast) |
| Annualised sales to distributors forecast | 7,242.8 / 8,061.8 / 7,827.6 / 8,217.1 | GWh | Q4 2025 / Q1 / Q2 / Q3 2026 forecast | ERA-TRR-Q4-25, Q1-26, Q2-26, Q3-26 BST tables | high (as forecasts) |
| Annualised UETCL sales by destination: UEDCL / export / data centres / total | 7,324.9 / 477.4 / 856.5 / 8,694.5 | GWh | Q3 2026 forecast | ERA-TRR-Q3-26, Table 4 | high (as a forecast) |
| Same, 2026 base | 7,633.8 / 731.1 / 400.3 / 8,792.9 | GWh | 2026 base forecast | ERA-TRR-Q3-26, Table 4 | high (as a forecast) |
| Energy sent out (station busbar) | not found | | any | No public source gives sent-out separately from purchases | |
| Monthly purchases / sent out / delivered as a series | not found | | 2024–2026 | Only the two press data points above were found | |
| Energy delivered to Central region | not found | | any | | |

## 4. Transmission losses

| Figure | Value | Unit | Period | Source | Confidence |
|---|---|---|---|---|---|
| Transmission losses | 4.85 | % | 2024 | ERA-ESI-24, s.2.3 (summary table rounds to 4.9%) | high |
| ERA transmission loss target | 4.6 | % | 2024 | ERA-ESI-24, s.2.3 | high |
| Transmission losses | 4.8 | % | 2023 | ERA-ESI-24 | high |
| Transmission losses, **derived** | 321.5 | GWh | 2024 | purchases 6,622.6 minus sales 6,301.1 (ERA-ESI-24), which gives 4.85% | high (derived) |
| Transmission losses | 4.79 | % | FY2022/23 (from 4.28%) | BT-0330 | medium |
| Transmission losses | 4.78 | % | FY2023/24 | UETCL-AR-25, p.12 (the text mislabels this year as "FY 25/26") | high |
| Transmission losses | 4.40 | % | FY2024/25 | UETCL-AR-25, p.12 | high |
| Transmission losses, **derived** | 310.1 | GWh | FY2024/25 | purchases 7,055.2 minus sales 6,745.08 (UETCL-AR-25), which gives 4.40% | high (derived) |
| Technical loss (KPI baseline) | 4.46 | % | FY2024/25 (target 4% by 2029/30) | UETCL-SP, Table 3 | high |
| ERA transmission loss factor used in tariffs | 4.65 / 4.60 / 3.56 | % | 2023 / 2024 / 2025 | ERA-TRR-Q4-25, loss trajectory table | high |
| ERA transmission loss factor (MYT 2026–2028) | 4.62 / 4.69 / 4.62 | % | 2026 / 2027 / 2028 | ERA-TRR-Q3-26, Table 5; ERA-TRR-Q2-26 | high |
| Transmission losses, actual | not found | | CY2025, 2026 | | |
| Transmission losses by voltage level | not found | | any | | |

## 5. Bulk supply tariff (ERA-approved, UETCL BST)

There are three Time-of-Use (ToU) periods: peak 18:00–23:00, shoulder 05:00–18:00 and off-peak 23:00–05:00 (ERA-ESI-24, s.2.5.2).

| Figure | Peak | Shoulder | Off-peak | Unit | Period | Source | Confidence |
|---|---|---|---|---|---|---|---|
| Approved BST | 329.1 | 263.1 | 186.4 | UGX/kWh | Q3 2025 | ERA-TRR-Q4-25, Table 12 | high |
| Approved BST | 318.2 | 250.2 | 171.1 | UGX/kWh | Q4 2025 | ERA-TRR-Q4-25, Table 12; ERA-AR-25 | high |
| Approved base BST 2026 / Q1 2026 | 328.2 | 259.8 | 184.4 | UGX/kWh | Q1 2026 | ERA-TRR-Q1-26, Table 23; ERA-TRR-Q2-26, Table 13 | high |
| Approved BST | 341.3 | 272.8 | 197.4 | UGX/kWh | Q2 2026 | ERA-TRR-Q2-26, Table 13 | high |
| Approved BST | 342.3 | 269.8 | 189.9 | UGX/kWh | Q3 2026 | ERA-TRR-Q3-26, Table 12 | high |
| Approved BST | not found | | | | Q4 2026 | The report was not on era.go.ug on 1 Nov 2026 | |
| UETCL proposed BST (application, not an approval) | 248.66 (single figure) | | | UGX/kWh | 2024 application | BT-1213 | medium |

**Note.** ERA-TRR-Q1-26 gives a prior-quarter comparator of 326.7 / 258.7 / 179.6. Its table labels that row "Q1 2025", but its text calls it Q4 2025. Neither matches the Q4 2025 figure of 318.2 / 250.2 / 171.1 published in ERA-TRR-Q4-25. Use the Q4 2025 report's own figure.

Related annualised bulk supply totals (ERA forecasts):

| Figure | Value | Unit | Period | Source | Confidence |
|---|---|---|---|---|---|
| Total bulk supply costs | 1,759,068 / 1,952,738 / 2,276,597 / 2,234,548 / 2,303,781 | UGX million | Q3 2025 / Q4 2025 / Q1 / Q2 / Q3 2026 | BST tables in the four tariff reviews | high |
| Power purchase costs | 2,096,086 | UGX million | Q3 2026 | ERA-TRR-Q3-26, Table 12 | high |
| Effective transmission O&M cost | 206,685 | UGX million | Q3 2026 | ERA-TRR-Q3-26, s.6.1 | high |

## 6. Deemed energy payments

| Figure | Value | Unit | Period | Source | Confidence |
|---|---|---|---|---|---|
| Deemed energy payments | not found | UGX | 2024, 2025, 2026 | The ERA tariff reviews, ERA-ESI-24 and UETCL-AR-25 give no total. ERA-AR-25 lists "increased deemed energy" only as a risk, with no number. | |
| Deemed energy cost | 104.4 | UGX billion | about FY2019/20 (9% of a UGX 1.1 trillion purchase bill) | Daily Monitor, "Taxpayers lose Shs104.4b to UETCL's non-evacuated power" (2020 audit), https://monitor.co.ug/uganda/business/technology/taxpayers-lose-shs104-4b-to-uetcl-s-non-evacuated-power--3253858 (figure seen in search summary only) | low |
| Achwa deemed energy | 24 | USD million per year | 2019 to Nov 2023 | BT-1213 | medium |

## 7. Power plants in or feeding Central

ERA-TRR-Q3-26 Table 3 gives the capacity as contracted for tariff purposes. It also gives ERA's annualised purchase forecast for Q3 2026, which is a forecast, not an actual.

| Plant | Capacity | Unit | Location / connection | Q3 2026 annualised purchase forecast (MWh) | Source | Confidence |
|---|---|---|---|---|---|---|
| Namanve HFO (UEGCL) | 50 | MW | Kiwanga, Mukono (north of the Namanve park). Peaking plant. | 65,676 (UGX 72.79 bn) | ERA-TRR-Q3-26; WIKI-NMV; UEGCL-NMV | high |
| Kabulasoke Solar PV (MSS Xsabo) | 20 | MWp | Gomba district | 29,325 | ERA-TRR-Q3-26 (some press say 24 MW) | high |
| Nkonge Solar PV (Xsabo Nkonge Solarline II) | 20 | MWp | Kasanda district (WIKI-NK). WIKI-NK says only that it evacuates "via a substation near the station". That this is Nkonge substation on the Kabulasoke–Nkonge 132 kV line (named in UETCL-AR-25 p.26) is our inference, not a published statement. | 39,862 | ERA-TRR-Q3-26; WIKI-NK | high (capacity); inference (connection) |
| Kapeeka solar | not found | | We found no solar plant at Kapeeka | | | |
| Tororo Solar PV (Tororo PV Power Co.) | 10 | MWp | Tororo (Eastern, not Central) | 21,904 | ERA-TRR-Q3-26 | high |
| Tororo Solar North PV | 10 | MWp | Tororo (Eastern) | 15,692 | ERA-TRR-Q3-26 | high |
| Electro-Maxx HFO Tororo | 50 | MW | Tororo (Eastern). Wikipedia says 80 MW. | 61,320 | ERA-TRR-Q3-26; WIKI-PS | high (ERA) |
| Bujagali HPP | 250 | MW | Buikwe, on the Nile | 1,697,228 | ERA-TRR-Q3-26 | high |
| Nalubaale + Kiira (UEGCL) | 380 (180 + 200) | MW | Jinja / Njeru | 1,781,193 | ERA-TRR-Q3-26 (split: WIKI-PS) | high |
| Isimba HPP (UEGCL) | 183 | MW | Kamuli, on the Nile | 1,182,716 | ERA-TRR-Q3-26 (Wikipedia: 183.2) | high |
| Karuma HPP (UEGCL) | 600 | MW | Kiryandongo. 400 kV infeed. | 1,919,926 | ERA-TRR-Q3-26 | high |
| Namanve refurbishment / financial risk | text only | | Parliament warned in Feb 2025 that operations could halt by Dec 2025 without funding. ERA tariffs make provision for the refurbishment. | | UEGCL-NMV; ERA-TRR-Q4-25 s.7.5 | medium |
| Plant output by month (actual) | not found | | | | | |

## 8. Transmission lines and substations around Kampala / Kawanda

| Figure | Value | Unit | Period | Source | Confidence |
|---|---|---|---|---|---|
| National circuit length: 66 / 132 / 132 cable / 220 / 400 kV | 35.2 / 3,319.5 / 0.9 / 1,002 / 606 | km | July 2024 | UETCL-SP, Table 1 | high |
| National circuit length, total | 4,962.2 | km | July 2024 | UETCL-SP, Table 1 | high |
| HV transmission grid length | 5,287.2 | km | FY2024/25 baseline | UETCL-SP, Table 3 | high |
| Transmission network length | 5,139.7 | km | 2024 | ERA-ESI-24 | high |
| Transformer capacity: 400/220 / 400/132 / 220/132 / 132/33 / 132/11 / 66/11 / mobile 132/33/11 | 1,302 / 630 / 2,120 / 2,555.5 / 220 / 28 / 50 | MVA | July 2024 | UETCL-SP, Table 1 | high |
| Total transformation capacity | 6,905.5 | MVA | July 2024 | UETCL-SP, Table 1 | high |
| Total transformation capacity | 7,170.5 | MVA | FY2024/25 | UETCL-AR-25, p.22; UETCL-SP | high |
| Number of substations | 43 | count | 2024–2025 | UETCL-SP, Table 1; UETCL-AR-25 Fig. 2 (the KPI table says 42) | high |
| Kawanda–Masaka line | 137 | km | 220 kV double circuit, commissioned 2018/19 | PL-0513; WIKI-KB | medium |
| Kawanda substation upgrade | 132/33 kV → 220 kV | | with the Kawanda–Masaka project | PL-0513 | medium |
| Kawanda–Masaka line cost | 153.2 | USD million | budget | WIKI-KB | low |
| Bujagali–Kawanda line | 75 | km | 220 kV double circuit (project plan) | AfDB Bujagali interconnection notice, https://www.afdb.org/en/news-and-events/uganda-us-29-million-for-bujagali-power-interconnection-project-3471 (seen in search summary only) | low |
| Bujagali 220/132 kV transformer | 250 | MVA | 1 unit listed under the Kampala Metro upgrade | UETCL-KMP and the JICA report (search summary). **Unverified:** the UETCL-KMP page, fetched on 1 Nov 2026, gives progress percentages but no MVA rating. | low (unverified) |
| Kampala Metro project: Buloba and New Mukono 220/132/33 kV new substations; upgrades of Kawaala, Bujagali, Mutundwe; mobile substation at Namungoona | 61% complete, planned June 2026 | % | FY2024/25 | UETCL-AR-25, p.24 | high |
| Kampala Metro lot progress: Buloba 100, Mutundwe 94, Bujagali 99, New Mukono 97, Namungoona 76, 132 kV reconductoring 71 | as listed | % | Jan–Feb 2026 | UETCL-KMP | high |
| Matugga–Kasana 132 kV line | 42.5 | km | 85% complete, planned June 2026 | UETCL-AR-25, p.24 | high |
| Kasana 132/33 kV substation | 20 (1 x 20) | MVA | under construction | UETCL-AR-25, p.24 | high |
| Western 132 kV upgrade (Mutundwe–Buloba–Kabulasoke–Masaka and Kabulasoke–Nkonge–Rugonjo–Nkenda) | 359 | km | contract signed 2025-12-19, completion FY2028/29 | UETCL-AR-25, p.26 | high |
| Substation loading: Mutundwe / Busunju / Kajjansi | 130.2 / 124.2 / 104.6 | % of capacity | 2025–26 | MON-0504 (citing a UEDCL report) | medium |
| Transformers critically loaded | 36 of 94 assessed | count | 2025–26 | MON-0504 (UEDCL report) | medium |
| Kampala substations at ≥80% loading | ≥80 | % | 2025–26 | MON-REG | medium |
| Major substations over 80% loading | 13 | count | 2025-09 (11 in Jul 2025) | AllAfrica, "UEDCL defends unending power outages", https://allafrica.com/stories/202509160603.html (seen in search summary; page blocked) | low |
| Greater Kampala transmission capacity, planned increase | 80 → 200 | MW | no date given | MON-1002 (UEDCL) | low |
| Kampala South substation | 10/14 | MVA | new transformer, 2025 | PLUS-1231 | medium |
| MVA ratings of Lugogo, Queensway, Kampala North, Mukono, Namanve substations | not found | | | | |

## 9. Curtailment and constraint reports, 2026

| Figure | Value | Unit | Period | Source | Confidence |
|---|---|---|---|---|---|
| Load shedding (national) | 534.73 | MWh | 2026-01 | ERA-TRR-Q2-26, s.3.1 | high |
| Load shedding (national) | 493.03 | MWh | 2026-02 | ERA-TRR-Q2-26. Causes: under-frequency shedding (Kenyan grid disturbance), Masaka constraints, a fault on Masaka West T2, **and constraints at Kawanda Substation to mitigate transformer overload**. | high |
| Load shedding (national) | 206.26 | MWh | 2026-04 | ERA-TRR-Q3-26 | high |
| Load shedding (national) | 249.46 | MWh | 2026-05 | ERA-TRR-Q3-26. Causes: **grid capacity constraints after faults on the 132 kV Owen Falls–Mukono North line, and transformer constraints at Mutundwe Substation**. | high |
| Unplanned load shedding, energy not supplied | 6.93 | GWh | 2025 | MON-0504 (citing the Ministry of Energy) | medium |
| Energy lost to transmission faults | 12.75 | GWh | 2025 | MON-0504 (Ministry of Energy) | medium |
| Transmission-related interruptions on UEDCL | 46 events, 299.06 h, 1.44 GWh | mixed | 2026-03 | MON-0504 (UEDCL data) | medium |
| Bujagali busbar protection failure | >340 | MW of generation lost (Bujagali + Isimba) | 2025–26 (date not given) | MON-0504 (UEDCL report) | medium |
| Lines with the most interruptions (Mutundwe–Masaka Central 420; Mukono North–Mpata 396) | as listed | count | 2025 | MON-0504, citing UETCL "System Operations Data 2025" | medium |
| National blackout | 21:07 on 5 Jun 2026, restored about 00:00 on 6 Jun | time | 2026-06-05 | MON-0606 (cause unconfirmed; reported as a fault at Nalubaale) | medium |
| Data-centre load (ERA sales forecast) | 400.3 (base 2026) → 856.5 (Q3 2026) | GWh annualised | 2026 | ERA-TRR-Q3-26, Table 4. ERA-TRR-Q1-26 attributes demand growth to "new large customers, specifically data centres". | high (as a forecast) |
| Curtailment of data-centre or industrial customers | not found | | 2026 | We found no public report of a data centre or industrial customer being curtailed in 2026. The only related item: a DatacenterDynamics headline (8 Jul 2026), "MTN Uganda blames power disruption at data center for major outage". It is an outage, not a curtailment, and was not verified. | |

## 10. Kawanda substation

| Figure | Value | Unit | Period | Source | Confidence |
|---|---|---|---|---|---|
| Kawanda transformer capacity (MVA) | not found | MVA | | No public source gives it | |
| Kawanda voltage levels | 220 / 132 / 33 kV (220 kV added with Kawanda–Masaka) | kV | 2019 | PL-0513 | medium |
| Kawanda service area | loads in "a radius of over 150 km in some directions" | km | FY2024/25 | UETCL-AR-25, p.24 | high |
| Reported constraint | load shedding at Kawanda "to mitigate transformer overload" | text | 2026-02 | ERA-TRR-Q2-26, s.3.1 | high |
| Upgrade project (UETCL) | "upgrade of Mutundwe & Kawanda substations to increase transformation capacity", in progress | text | FY2024/25 | UETCL-AR-25, p.24 | high |
| Relief project (UETCL) | Matugga–Kasana 132 kV, 42.5 km, Kasana 20 MVA, planned June 2026, built partly to improve supply from Kawanda | text | FY2025/26 | UETCL-AR-25, p.24 | high |
| UEDCL transformer upgrade at Kawanda | due "by the end of 2026", relieving Naalya and Kyaliwajala | text | 2026 | MON-1002 | medium |
| Location | about 15.5 km by road north of Kampala, Wakiso district | km | | WIKI-KB | low |

## 11. Namanve and Kapeeka industrial parks

| Figure | Value | Unit | Period | Source | Confidence |
|---|---|---|---|---|---|
| Kampala Industrial and Business Park (Namanve), area | 2,209 (894 ha) | acres | | WIKI-NMV (no citation given on the page) | low |
| Namanve operational factories | not found. A search summary quoted 258 factories (target 500 by end 2025) but did not name its source, so we do not use it. | count | 2025–2026 | | |
| Namanve substation | "189 MW" substation commissioned | MW | undated | Sanyu FM item, seen in a search summary only (the page returned 404) | low |
| Kapeeka (Liao Shen) industrial park, factories | 34 (capacity for 80) | count | Dec 2025 | UIA-KAP (title; body seen in search summary) | medium |
| Kapeeka park area | 2,500 | acres | undated | Daily Monitor, "Museveni wants Kapeeka upgraded to municipality", https://www.monitor.co.ug/uganda/news/national/museveni-wants-kapeeka-upgraded-to-municipality-1863318 (search summary) | low |
| Kapeeka on-site substation | 100 | MW | undated | UIA and Daily Monitor (search summaries) | low |
| Kapeeka distribution extension | 15 km line, UGX 1.3 bn | km / UGX | undated (Umeme era) | Daily Monitor, "Shs1.3b to expand power network in Kapeeka Park", https://www.monitor.co.ug/uganda/business/prosper/shs1-3b-to-expand-power-network-in-kapeeka-park-1850766 (search summary) | low |
| Park electricity demand (MW or GWh) for Namanve or Kapeeka | not found | | | | |

## 12. National Energy Compact (Mission 300) and UBOS

| Figure | Value | Source | Confidence |
|---|---|---|---|
| Uganda National Energy Compact: demand and capacity targets | not found. The compact was reported as launched at the Africa Energy Forum in June 2026, with a national consultation on 21–22 Oct 2026. Only one target was seen: a threefold increase in firm exports by 2030 (AfDB notice, search summary). | low |
| UBOS figures (statistical abstract electricity tables) | not found in this pass (not retrieved) | |

## What is still missing (for the request notes)

- Monthly energy sent out and delivered, and actual monthly peak demand after May 2026. These are NCC system summaries, requests 5 and 7.
- Kawanda transformer ratings and loading, and curtailment logs. These are request 8.
- Deemed-energy payments for 2024–2026. This is request 9. No public total exists.
- Transmission losses by voltage level and for CY2025.
- The approved BST for Q4 2026. Check era.go.ug again; it was not posted on 1 Nov 2026.
