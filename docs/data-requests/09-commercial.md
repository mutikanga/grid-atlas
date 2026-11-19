# Request 09: tariff, bulk sales, deemed energy and plant agreements

- **To:** UETCL Commercial: the officers who hold the bulk supply tariff and bulk billing, and those who hold the power purchase agreements and generator invoices
- **From:** Grid Atlas team (UETCL graduate trainees), under the covering memo from the Head of Network Operations
- **Date:** Monday 2 November 2026
- **Due:** Friday 13 November 2026, so the results can be checked before the management preview on Friday 20 November
- **Template:** `templates/T06_commercial.xlsx`, sheets `README`, `tariffs`, `bsp_sales`, `deemed_energy`, `energy_charges`, `plants_ppa` and `questions`

Please send each item when it is ready; there is no need to wait for the full set. If you can only send part by 13 November, send items 1, 2 and 5 first. If something cannot be sent, or will be late, tell us as soon as you know.

## Why we need it

The Grid Atlas puts a UGX value on technical losses, deemed energy and suppressed demand for September 2025 to September 2026. These figures open the demo at the ERA SDP session and set the payback of each loss remedy, so they must rest on the approved tariff and your records, not on a proposed tariff or an older year. Your bulk sales also cross-check the monthly loss balance that the demo must reconcile (acceptance criterion 3), and the plant summary, which we had planned to request from UEGCL, tells the model what feeds Central.

## What to send

Fill in the workbook `templates/T06_commercial.xlsx`, one sheet per item, or send your own files. Your native format is welcome; the template lists the minimum fields. Items 1 to 4 cover each month from September 2025 to September 2026 (13 months); item 5 is the plant list as it stands now. Energy in kWh, money in UGX, months as YYYY-MM, dates as YYYY-MM-DD. Excel or CSV is best.

1. **Bulk supply tariff, month by month** (sheet `tariffs`)
   - The ERA-approved bulk supply tariff in UGX/kWh for each month: start and end dates, tariff code, rate, approval status, and the ERA decision reference and date. One row per period it applied, with no month left out.
   - If a month's tariff was first provisional or only proposed, give each version as its own row and mark its approval status. If an approved tariff was revised later, give the revised rate and say what changed in `notes`.
   - A copy of each ERA decision, if easy (PDF is fine).
   - *Used for:* the top of the value range for losses, the value of suppressed demand, and the tariff named on the opening slide.

2. **Deemed energy per plant, per month** (sheet `deemed_energy`)
   - Every plant with deemed energy in the period, across the country and including plants on 33 kV: kWh deemed and UGX payable, per month. MWh is fine in your own files if the column says so.
   - The cause as your records state it, and its category: evacuation constraint (the grid could not take the energy) or surplus (no demand for it). For a constraint, name the substation, line or 33 kV feeder.
   - Where each claim stands: accrued, invoiced, verified, paid or disputed.
   - One row per plant per month, split by cause and location if your records do. If they list several events in a month with the same cause and location, add them into one row.
   - Deemed energy only. Demand that could not be supplied (load shedding, curtailed customers) is a different figure; leave it out.
   - *Used for:* the national total and the Central share on the opening slide, and the link from each network constraint to what it cost.

3. **Energy sold per bulk supply point and direct customer, per month** (sheet `bsp_sales`)
   - kWh billed each month at each bulk supply point, split by buyer: UEDCL, any other distributor, each direct customer (by code) and exports.
   - The meter ID and metering voltage, with one row per meter where a point has more than one.
   - The amount billed in UGX, and whether the reading was estimated.
   - All bulk supply points in one export if that is easiest. At least those at the Central substations: Kawanda, Mutundwe, Lugogo, Kampala North, Queensway, Namanve, Mukono, Kapeeka, Kabulasoke, Nkonge and Masaka.
   - *Used for:* the cross-check on NCC's bulk supply point metering in the monthly loss balance.

4. **Energy charge per plant, per month** (sheet `energy_charges`)
   - Every plant UETCL buys energy from, not only those in Central: the energy charge actually paid each month in UGX/kWh, and whether the plant was on take-or-pay terms.
   - If easy: the kWh bought and the capacity payment in UGX.
   - If plant-level charges cannot leave Commercial, send one row per month with the plant shown as `Not named`, the energy charge of the most expensive plant running that month whose energy is paid only when taken (not take-or-pay), and a line on how you chose it.
   - *Used for:* the bottom of the value range. When supply exceeds demand, a kWh saved on the grid avoids buying a kWh from the plant at the margin, or saves nothing if that energy would have been deemed anyway.

5. **Plant summary for plants in or feeding Central** (sheet `plants_ppa`)
   - One row per plant: owner, technology, installed, contracted and dependable MW, connection substation and voltage (and the 33 kV feeder if the plant is embedded), billing metering point, commercial operation date, PPA expiry, the deemed-energy terms in outline, and operating status now, with any change since September 2025.
   - At least Namanve (thermal; please confirm its operating status and PPA expiry), Kabulasoke, Nkonge, Kapeeka and Bujagali. Add any other plant connected inside Central or feeding it directly whose agreement Commercial holds, such as Nalubaale or Karuma (the 400 kV infeed at Kawanda).
   - One or two lines on the deemed-energy terms are enough: when deemed energy is payable, how the kWh is worked out and at what price. Do not send the agreements themselves.
   - *Used for:* the supply side of the network model and the site scoring: what feeds Central, where, at what voltage and on what terms.

6. **Which items are confidential** (sheet `questions`, Q1, and the `confidential` column in `plants_ppa`)
   - For each item above, tell us who may see it: the Atlas team only, UETCL staff, or ERA as a total or range. We will follow your marking. Anything you mark confidential is used only in the Atlas calculations and is not shown outside UETCL unless you agree.

## Questions to answer

Answer in the `questions` sheet of the workbook (column `answer`), or in a short note with your files. "Not known" is a useful answer. Please answer Q1 and Q4 with the first files, because they decide how we may use and read the data.

- **Q1.** Which of the items you send are confidential? For each sheet or column, say who may see it: the Atlas team only, UETCL staff, or ERA as a total or range.
- **Q2.** Which bulk supply tariff applied in each month from September 2025 to September 2026? Was any month provisional or revised later? Does the tariff have parts other than a single energy rate, such as a demand charge or time-of-day rates?
- **Q3.** How is deemed energy worked out under the agreements, in outline? Which unit records the cause, and from which record (for example NCC dispatch instructions or plant availability declarations)?
- **Q4.** Do your monthly figures follow calendar months? If deemed energy is recorded by invoice month, or sales by meter-reading date, say which and give the reading dates.
- **Q5.** Are the bulk supply point billing meters on the high-voltage or low-voltage side of the 132/33 kV transformers? Is the energy billed at a point just its meter reading, or does it add the output of plants embedded on the 33 kV feeders behind it?
- **Q6.** Are energy charges set in UGX, or in USD (or another currency) and converted? At which exchange rate?
- **Q7.** Which plants were on take-or-pay terms, and in which months?
- **Q8.** Do you reconcile monthly bulk sales with NCC's delivered energy? If so, what differences are usual, and why?
- **Q9.** For any plant in or feeding Central whose agreement Commercial does not hold, which unit or organisation holds it?

## What not to send

- No personal data: no names, phone numbers, email addresses or ID numbers of any person.
- No customer names or account numbers. Give each direct customer a code (DC-1, DC-2 and so on) that stays the same every month, and keep the key to the codes yourself.
- No full agreements, invoices, bank details or signatures. The figures and a short outline of the terms are enough.

## How to deliver

- Follow the handling note sent with this request.
- Put the files in the Grid Atlas folder on the UETCL share, or in the landing folder on the Grid Atlas server. The handling note gives both locations.
- Never send them by personal email, WhatsApp, a USB stick of unknown origin or personal cloud storage.
- Name each file with what it holds and the period, for example `T06_commercial_2025-09_to_2026-09.xlsx`. If you correct a file, send it again under the same name and tell us it replaces the earlier one.
- Then tell the contact below which files you have put there. Do not attach the data to that message.

## Contact

[name, phone], Grid Atlas team, for any question about this request and to say when files are delivered. If the due date cannot be met, the escalation route is in the covering memo.

Thank you for your help.
