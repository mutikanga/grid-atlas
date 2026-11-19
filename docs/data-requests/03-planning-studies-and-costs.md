# Request 03: Planning studies, criteria and unit costs

- **To:** Planning mentor, UETCL Grid Development and Planning
- **From:** Grid Atlas team (UETCL graduate trainees), under the covering memo from the Head of Network Operations
- **Date:** Monday 2 November 2026
- **Due:** Friday 13 November 2026. If the criteria (item 1) can come by Friday 6 November, that helps: we fix the N-1 method before we run it.
- **Template:** `templates/T13_planning_studies.xlsx` (attached), sheets `README`, `questions`, `criteria`, `studies`, `contingency_results`, `unit_costs` and `commissioning_years`; plus the `projects` sheet of `templates/T08_projects_and_loads.xlsx` for the Kawanda relief

## Why we need it

- **N-1 benchmark (acceptance criterion 4 in the scope of work).** The Atlas runs N-1 on every Central line and transformer. It supports Planning's work; it does not replace it. So we will run our N-1 on the same case and with your criteria, compare our table with your own results line by line, explain every difference, and ask you to sign the comparison. No N-1 result is shown outside UETCL, including at the ERA SDP session, before you have signed it.
- **Kawanda page.** It shows how much more load Kawanda can take before and after the planned relief.
- **Losses segment and asset age.** Unit costs give the reconductoring payback in the demo. Commissioning years give the asset-age view that the board paper's notes ask for.

## What to send

Items 1, 2, 4 and 5 go in T13. Item 3, the Kawanda relief, goes in the `projects` sheet of T08. Your native format is welcome; the template lists the minimum fields. Where a report or table already exists, send it as it is and skip that sheet.

1. **Planning criteria.** Sheet `criteria`: one row per criterion, and one per voltage level where they differ. Or send the criteria document itself.
   - The rating set checked in normal operation, and after a contingency: continuous, emergency (short-time) or NCC operating limit.
   - The ambient and conductor temperatures behind the line ratings.
   - The transformer loading allowed after a contingency: how much, and for how long.
   - The voltage limits in pu, in normal operation and after a contingency, at 132 kV and 220 kV (and 400 kV if you have them).
   - The source of each: Grid Code clause or planning-manual section.
2. **Latest Central contingency or system-study results.** Sheets `studies` and `contingency_results`.
   - The most recent study you have, whatever its year. If you also hold a 2030 study, send it too: the Atlas runs N-1 on 2030 as well.
   - For each study: title, date, the year and loading it represents (peak or light load), the tool, and what was tripped.
   - The study case in native format, if it is not one of the cases you send under request 2. If it is, give its `case_id`.
   - For each violation: the contingency, the element affected, the kind (overload, undervoltage, overvoltage, non-convergence or loss of supply), the value before and after the outage, the limit, and the rating used.
   - The full contingency list, including outages that caused no violation. For PSS/E, the .con file is fine.
3. **The planned Kawanda relief.** T08 sheet `projects`, with `relief_for` = Kawanda, one row per part.
   - What it is: transformer, line, substation, or a mix.
   - kV; MVA per transformer unit, or conductor and rating per circuit; length for a line.
   - The existing elements it replaces or uprates.
   - Status (planned, committed or under construction) and expected in-service month.
   - If it is in your 2030 case, its element IDs in `model_ref` with these basics are enough. If it is already listed under request 10, do not repeat it.
4. **Commissioning year of each Central line and transformer.** Sheet `commissioning_years`: one row per line circuit and per transformer unit, with the year first energised, and the year and kind of any later reconductoring, uprating or major refurbishment. Skip this if your reply to request 2 (T01) or the GIS layers from request 4 (T02) already carry it. Load-flow case files usually do not.
5. **Standard unit costs.** Sheet `unit_costs`. For each: cost, currency (UGX or USD), price year, what it includes, and where it comes from (contract rate, tender or estimate). A low and high range is welcome.
   - Reconductoring per km, by conductor, including ACCC. Give the conductor size, and say whether the cost is per circuit-km or per route-km.
   - A 132 kV bay and a 220 kV bay (say whether a line or a transformer bay).
   - A transformer per MVA, by voltage ratio (for example 220/132 kV and 132/33 kV).
   - A capacitor bank per MVAr, by voltage.

Format: Excel preferred; PDF reports are fine.

## Questions to answer

Answer in the `questions` sheet of T13, or in your reply.

1. Which loading case does your latest Central study use: year, peak or light load, and dispatch? Is it one of the cases you are sending under request 2?
2. Which outages do you treat as credible: each line circuit and transformer, both circuits on shared towers, generating units, busbar faults?
3. Is loss of supply acceptable after a single outage anywhere in Central, for example at a substation fed by one line? Up to how many MW?
4. What is the planned Kawanda relief, which existing elements does it change, is it funded, and when is it due in service?
5. What match between the Atlas N-1 table and your results would you accept: the same violations, and loadings within how many percentage points?
6. Can you set aside an hour in the week of 16 November to review and sign the comparison, before the management preview planned for Friday 20 November? If someone else should sign, who?
7. Are the unit costs from recent contracts or from estimates? What do they include: supply, installation, civil works, engineering, taxes?
8. Where are commissioning years kept, and who keeps them?

## What not to send

- No personal data: no staff names or phone numbers, and no landowner, wayleave or compensation records.
- No customer names.
- No supplier contracts, bids or tender documents. The unit rate, its price year and what it includes are enough.

## How to deliver

Follow the handling note (`handling-note.md`) sent with this request.

- Put the files in the UETCL share folder or the Atlas server landing folder named in the handling note.
- Then send the contact below a short UETCL email, without attachments, listing the file names, so we can log what arrived.
- If a file cannot leave your workstation, tell us and we will work through it with you there.
- Never use personal email, WhatsApp, personal cloud storage, or USB sticks of unknown origin.

## Contact

[name, phone], Grid Atlas team (power systems).

If part of this is ready before the rest, please send it as it is ready. If the due date is a problem, or anything here is unclear, tell us early; the covering memo gives the escalation route.
