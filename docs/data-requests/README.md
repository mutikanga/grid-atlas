# Grid Atlas data requests: index and send checklist

This folder is the data-request pack that goes out on Monday 2 November 2026. It has one covering memo for the sponsor (the Head of Network Operations) to sign, one handling note, and one note per request. Unless a note says otherwise, every request covers September 2025 to September 2026 (13 months).

## Files
- `00-covering-memo.md`: request 1, the sponsor's memo. Its annex is a covering letter for the three holders outside UETCL (requests 11, 13 and 14).
- `handling-note.md`: one page on classification, delivery, storage and what may be shown outside UETCL. It names the two delivery locations, which the other notes point to.
- `02-...md` to `15-...md`: one note per request, listed below.
- Template workbooks: `templates/<ID>_<slug>.xlsx`, generated from `templates/spec/` (see "Before sending"). Each opens with a `README` sheet. T11 (reconciliation explanations) and T12 (hand-built network) are the team's own and are never sent.

## The 15 requests
| # | Note | To | What | Template | Due |
|---|---|---|---|---|---|
| 1 | `00-covering-memo.md` | Head of Network Operations (sponsor) | Sign the covering memo: approval reference, a contact per dataset, due dates, escalation route. Book the management preview for Fri 20 Nov. | none | Mon 2 Nov |
| 2 | `02-planning-network-model.md` | Grid Development and Planning | National solved cases in native format at all voltages: as-operated peak near Sep 2026, light load, 2030. Rating sets, generator Q limits, Planning's own solved voltages and flows, network changes since Sep 2025. | `T01_network_model.xlsx` | Fri 6 Nov |
| 3 | `03-planning-studies-and-costs.md` | Planning mentor | Latest Central contingency studies and criteria; Kawanda relief scope and date; commissioning years; standard unit costs. | `T13_planning_studies.xlsx`, plus sheet `projects` of `T08_projects_and_loads.xlsx` | Fri 13 Nov (criteria by Fri 6 Nov if possible) |
| 4 | `04-planning-gis.md` | Planning GIS unit | Substations, and one feature per circuit with the model branch ID, kV, conductor, length and commissioning year. EPSG code stated; no landowner fields. | `T02_gis.xlsx` | Fri 6 Nov |
| 5 | `05-ncc-monthly-reports.md` | NCC reporting | The 13 Power System Summaries in Excel; how losses by voltage level are derived; deemed and unserved energy kept apart; incidents due to constraints; peak and off-peak sample days. | `T03_ncc_monthly.xlsx` | Fri 6 Nov (sheet `sample_days` by Wed 4 Nov) |
| 6 | `06-ncc-scada.md` | NCC SCADA / historian | Hourly MW and MVAr per measurement point, and bus kV, for all 13 months (two days a month at minimum), with the point list and sign convention. | `T04_scada.xlsx` | Fri 6 Nov |
| 7 | `07-ncc-metering.md` | NCC metering and energy accounting | Monthly MWh at every Central boundary meter (including the 400 kV infeed at Kawanda), every Central generator and every bulk supply point, with accuracy class; whether substation loads are net or gross of embedded plant. | `T03_ncc_monthly.xlsx` (sheets `boundary_meters`, `internal_meters`, `definitions`) | Fri 6 Nov |
| 8 | `08-ncc-operations-kawanda.md` | NCC operations | The Kawanda constraint: element, limit, hours it bound, MW curtailed, deferred connections. Other Central limits and the outage log. | `T05_ncc_operations.xlsx` | Fri 6 Nov (part A by Wed 4 Nov) |
| 9 | `09-commercial.md` | Commercial | Approved bulk supply tariff by month; deemed energy per plant; energy per bulk supply point; agreement summary for the plants in or feeding Central. | `T06_commercial.xlsx` | Fri 13 Nov |
| 10 | `10-planning-connections-and-projects.md` | Grid Development and Planning (connections, projects); Commercial | Committed and pending large loads in Central; ILDS anchor sites; SGR traction points; planned projects to 2030. | `T08_projects_and_loads.xlsx` | Fri 13 Nov |
| 11 | `11-era-sdp.md` | ERA SDP secretariat | Date and slot (with questions), venue, internet or LAN access, whether we may present remotely from a UETCL desk, audience, evaluation criteria, recording and distribution rules. | none | Sent Mon 2 Nov; reply asked for by Fri 6 Nov |
| 12 | `12-ict-infosec-dpo.md` | ICT and Information Security; Data Protection Officer | Data classification; approval and conditions for hosting beside Grid Monitor; ports; an internal Git host; a results-only laptop copy or a remote demo; personal-data rules for corridor GIS and event logs. | none | Fri 6 Nov (hosting answer by Thu 5 Nov if possible) |
| 13 | `13-uia-industrial-parks.md` | UIA | Park boundaries with the CRS stated, status, hectares available, allocated loads. | `T09_sites.xlsx` | Fri 13 Nov |
| 14 | `14-uedcl-feeders.md` | UEDCL (aggregate, not blocking) | 33 kV feeders per Central bulk supply point: monthly peak and MWh, and the generators on each feeder. | `T07_uedcl_feeders.xlsx` | Fri 13 Nov |
| 15 | `15-open-data-team-tasks.md` | The Grid Atlas team | UBOS boundaries and Census 2024 population; UWA/NFA protected areas and MWE/NEMA wetlands (Protected Planet only with permission); Copernicus or SRTM terrain; OSM roads, with attribution. | none sent (the team fills `T10_growth.xlsx`) | Week 1 (Fri 6 Nov) |

Critical items (2, 4, 5, 6, 7, 8 and 12) are due on Friday 6 November; the rest (3, 9, 10, 13 and 14) on Friday 13 November.

## What to attach
| # | Covering document | Handling note | Template workbook |
|---|---|---|---|
| 1 | The memo itself, for signature, with the annex letter and the rest of this pack | yes | none |
| 2 | Signed memo | yes | `templates/T01_network_model.xlsx` |
| 3 | Signed memo | yes | `templates/T13_planning_studies.xlsx` and `templates/T08_projects_and_loads.xlsx` |
| 4 | Signed memo | yes | `templates/T02_gis.xlsx` |
| 5 | Signed memo | yes | `templates/T03_ncc_monthly.xlsx` |
| 6 | Signed memo | yes | `templates/T04_scada.xlsx` |
| 7 | Signed memo | yes | `templates/T03_ncc_monthly.xlsx` (the same workbook as request 5) |
| 8 | Signed memo | yes | `templates/T05_ncc_operations.xlsx` |
| 9 | Signed memo | yes | `templates/T06_commercial.xlsx` |
| 10 | Signed memo | yes | `templates/T08_projects_and_loads.xlsx` |
| 11 | Annex letter, signed, on letterhead | no: ERA sends no data | none |
| 12 | Signed memo | yes: ICT and the DPO are asked to confirm or correct it | none |
| 13 | Annex letter, signed, on letterhead | yes | `templates/T09_sites.xlsx` |
| 14 | Annex letter, signed, on letterhead, citing management's introduction | yes | `templates/T07_uedcl_feeders.xlsx` |
| 15 | Not sent: a team task list | the team follows it | none |

Send each note as a PDF, or paste it into the body of the email, from an official UETCL address. The notes and workbooks hold no data, so email is fine for sending them. The data itself comes back only by the routes in the handling note.

## Before sending (Monday, first thing)
- [ ] Fill the placeholders: the approval and memo references in `00-covering-memo.md`; `[name, phone]` in every note and the team contacts in the memo's table; the share path and the server landing folder in `handling-note.md`.
- [ ] Leave the classification placeholder in the handling note until ICT answers request 12. Add holder contacts to the memo's table as units name them.
- [ ] Check that the Grid Atlas folder on the UETCL share exists and that only the team can open it.
- [ ] Generate the workbooks: `./atlas templates`, or `docker run --rm -v "$PWD":/app -w /app gridatlas-py:dev python templates/build_templates.py`. Open each one in Excel.
- [ ] Make PDFs of the memo, the annex letter, the handling note and each note.

## Send order on Monday 2 November
1. **Request 1.** Give the pack to the sponsor to sign first thing. Do not hold the other requests for the signature: if it is not signed by 11:00, send them with the memo marked "signed copy to follow".
2. **Request 2** (Planning network model). It has the longest lead time.
3. **Request 8** (NCC operations). Part A, due Wed 4 Nov, decides which Kawanda element we model.
4. **Request 5** (NCC reporting). Its `sample_days` sheet, due Wed 4 Nov, feeds request 6.
5. **Requests 6 and 7** (NCC SCADA, NCC metering).
6. **Request 4** (Planning GIS).
7. **Request 12** (ICT and Information Security, DPO). The hosting answer is needed before the server dry run on Fri 6 Nov.
8. **Request 11** (ERA SDP secretariat). The session date decides the week-4 plan.
9. **Requests 3, 9 and 10** (Planning mentor, Commercial, Planning connections).
10. **Requests 13 and 14** (UIA, UEDCL), with the signed annex letter, through the management introductions. If an introduction is not in place yet, ask the sponsor's office to send the request.
11. **Request 15.** The team starts the open-data tasks.

Record each send in the tracking table. Ask every holder to acknowledge and to name a contact by Tue 3 Nov.

## Follow-up calendar
| Date | Action |
|---|---|
| Tue 3 Nov | Chase acknowledgements and contact names. Put the holder contacts in the memo's table. |
| Wed 4 Nov | Expect request 5 sheet `sample_days` and request 8 part A. |
| Thu 5 Nov | Remind holders of Friday's items. Expect ICT's hosting answer (request 12, part B). |
| Fri 6 Nov | Critical items due: 2, 4, 5, 6, 7, 8, 12. ERA's reply hoped for (11). |
| Mon 9 Nov | A critical item missing, with no agreed new date: the team lead raises it with the head of the holding unit. |
| Wed 11 Nov | Still missing: the team lead takes it to the sponsor. |
| Fri 13 Nov | The rest due: 3, 9, 10, 13, 14. |
| Mon 16 Nov | Missing, with no agreed new date: head of the holding unit. |
| Wed 18 Nov | Still missing: the sponsor. |
| Fri 20 Nov | Management preview: clear what may be shown outside UETCL. |

## Tracking
- **Received:** the files are on the UETCL share or in the landing folder, and logged on arrival.
- **Loaded:** loaded through the import log, with every row either loaded or listed with a reason.

| # | Holder contact | Sent (date, by) | Acknowledged | Received (what, date) | Loaded (batch, date) | Next action |
|---|---|---|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |
| 4 | | | | | | |
| 5 | | | | | | |
| 6 | | | | | | |
| 7 | | | | | | |
| 8 | | | | | | |
| 9 | | | | | | |
| 10 | | | | | | |
| 11 | | | | | | |
| 12 | | | | | | |
| 13 | | | | | | |
| 14 | | | | | | |
| 15 | | | | | | |
