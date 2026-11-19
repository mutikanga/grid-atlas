# Request 05: NCC monthly Power System Summaries

**To:** UETCL NCC, reporting: whoever compiles the monthly Power System Summary  
**Cc:** NCC mentor to the Grid Atlas team  
**From:** Grid Atlas team, under the covering memo from the Head of Network Operations  
**Date:** Monday 2 November 2026  
**Due:** Friday 6 November 2026. If you can, send sheet `sample_days` by Wednesday 4 November: NCC SCADA uses it for request 06.  
**Template:** `templates/T03_ncc_monthly.xlsx`, sheets `README`, `definitions`, `system_summary`, `losses_by_voltage`, `substation_monthly`, `generation_monthly`, `deemed_unserved` and `sample_days`. Sheets `boundary_meters` and `internal_meters` in the same workbook are for NCC metering (request 07).

## Why we need it
Your Summaries are the reference for two acceptance checks: all 13 months loaded (criterion 2), and the model's monthly losses within 10% of NCC's (criterion 3, demo item 2). They also drive the map's time slider, the dashboard and the opening slide on losses, deemed energy and the Kawanda constraint.

The definitions matter because the 10% check must compare like with like. If NCC's figure counts different meters, voltage levels or transformer losses from the model's, the check can pass or fail for the wrong reason.

## What to send
Your native format is welcome; the template lists the minimum fields. Send your own files as they are, and use the template sheets only for what they lack.

For every item:
- **Period:** every month from September 2025 to September 2026 (13 months).
- **Units:** energy in MWh, power in MW, money in UGX.
- **Dates and times:** months as `YYYY-MM`; times as `YYYY-MM-DD HH:MM` in East Africa Time.
- **Names:** substations and plants as you normally write them. We map them to our codes.

1. **The 13 Power System Summaries, in Excel.** The workbooks exactly as you produce them, with every sheet. Not PDF: a PDF costs us about three days of retyping. Please include June to September 2026 even if the team already holds copies, so all 13 months come from the same version.
   - If a month exists only as PDF, send the PDF and tell us.
   - If a month was revised after it was issued, send the latest version and say what changed.
   - From them we read: energy generated, imported, exported, sent out and delivered; losses by voltage level; peak and minimum demand, with their times; substation loads; generation by plant; deemed and unserved energy; and events.

2. **How losses by voltage level are worked out:** your answers to Q1, Q2 and Q8 below. If a month's Summary has no losses by voltage level, fill sheet `losses_by_voltage`: one row per month and level (`400`, `220`, `132`, `transformation`, `total`), with `scope` (`national`, `central` or `other`), `losses_mwh`, `losses_pct`, `method` (`metered`, `estimated`, `state_estimator` or `other`) and `meters_used`.

3. **Deemed and unserved energy, kept apart** (sheet `deemed_unserved`), unless your Summary already gives them per plant and per substation with their cause:
   - `deemed`: energy a plant could have delivered but the grid did not take. One row per plant per month.
   - `unserved`: demand lost to faults or outages. `load_shed`: demand cut on NCC instruction, including curtailment of large customers. One row per substation per month.
   - In each row: `energy_mwh`; `cause` as NCC recorded it at the time (`network_constraint`, `generation_shortfall`, `surplus`, `other` or `unknown`); `constraint_element` when the cause is a network constraint; and `amount_ugx` only if the Summary gives it.

   Please never add deemed and unserved energy together. One is generation the grid could not take, the other is demand it could not supply. They have different causes, remedies and values.

4. **Incidents due to constraints, per month** (sheet `system_summary`, one row per month). Give `constraint_incidents`: the number of incidents that month that NCC attributes to a network constraint. Tell us what you count (Q9).
   - In the same row, copy `sent_out_mwh`, `delivered_mwh`, `losses_mwh` and `peak_mw` from the Summary. This also lets us check that we read your files correctly.
   - The event-by-event list is asked of NCC operations in request 08 (sheet `events`), so each monthly count can be traced to its events.
   - If your Summaries do not count these incidents, say so. We will count them from that list.

5. **Sample days** (sheet `sample_days`, one row per month):
   - `peak_day`: the day of the month's system peak;
   - `offpeak_day`: the day with the month's lowest demand, usually a Sunday or public holiday, but not a day with a major outage;
   - `constraint_day`: a day when the Kawanda constraint bound, if you know of one.

   NCC SCADA exports these days first for request 06, so please send this sheet early.

6. **Only if your Summaries lack them:**
   - `substation_monthly`, one row per substation (or metering point) per month: `energy_mwh`, `peak_mw` and `peak_at`. If you have them, also `peak_mvar`, `coincident_mw` (MW at the hour of the system peak), `min_mw`, `load_basis` (`net` or `gross` of generation embedded at 33 kV) and `quality` (`actual`, `estimated` or `partial`).
   - `generation_monthly`, one row per plant per month, for every plant including those on 33 kV feeders: `sent_out_mwh`. If you have them, also `connection_substation`, `connection_kv`, `peak_mw`, `availability_pct` and `metered` (`Y` or `N`).

7. **Your answers to the questions below**, in sheet `definitions` or in your reply. We need them whatever else you send.

**If it cannot all come by Friday 6 November:** send `sample_days`, the Summaries and the answers to Q1 to Q3 and Q5 to Q7 first, and tell us when the rest will follow.

## Questions to answer
Answer in sheet `definitions` (column `answer`) or in your reply. "Not known" is a useful answer. Q3, Q5 and Q6 also go to NCC metering (request 07); one joint answer is fine.

- **Q1.** How are the losses by voltage level in the Power System Summary worked out: from meters, estimated, or from the state estimator? Which meters are used for each voltage level?
- **Q2.** Does the 132 kV loss figure include the losses in the 220/132 kV and 132/33 kV transformers? Does it include substation station supply? Are 400 kV losses inside it, reported separately, or not reported?
- **Q3.** Can NCC produce a monthly energy balance for the Central region from boundary meters? If your energy accounting already uses a Central or Kampala-metro zone, which substations does it cover? Which boundary circuits have no meter?
- **Q5.** Are the substation loads in the Summary net of generation embedded at 33 kV (the plant's output already taken off) or gross (the plant's output added back)? Does this differ by substation or plant?
- **Q6.** Which months contain estimated or substituted readings, and for which figures or meters? Was any month's Summary revised after it was issued?
- **Q7.** What time zone do the Summary's timestamps use, for example the time of the peak? Does a timestamp mark the start or the end of the interval? Is the peak an instantaneous, 15-minute, 30-minute or hourly value?
- **Q8.** How are energy sent out and energy delivered defined? Does sent out include imports? Does delivered include exports and station supply? Are the losses simply sent out minus delivered?
- **Q9.** What does NCC count as an incident due to a constraint? Which kinds of event count? Is an incident that lasts several hours, or repeats on several days, counted once or each time?
- **Q10.** How do you separate deemed energy, unserved energy and load shedding in the Summary? In which of them do you record the curtailment of a large customer, such as a data centre?

## What not to send
- **No personal data:** no staff names, signatures or phone numbers. If a Summary carries a sign-off block, delete it before sending.
- **No customer names:** describe a curtailed or direct customer by its substation and kind (for example data centre), never by name.
- **No PDF copies** of months you send in Excel.

## How to deliver
As set out in the handling note (`handling-note.md`, sent with this request):
- Put the files in the Grid Atlas folder on the UETCL share, or in the landing folder on the Grid Atlas server. The handling note gives both locations.
- Never use personal email, WhatsApp, USB sticks of unknown origin, or personal cloud storage.
- Start each file name with `T03` and say what it holds, for example `T03_summary_2026-03.xlsx` or `T03_sample_days.xlsx`. If you correct a file, send it again under the same name and tell us it replaces the earlier one.
- Send each file when it is ready; there is no need to wait for all 13 months.
- Then tell the contact below which files you have put there. Do not attach the data to that message.
- The data stays on UETCL systems. Nothing based on it is shown outside UETCL until management has cleared it at the preview planned for Friday 20 November.

## Contact
[name, phone], Grid Atlas team. If something blocks the request, the escalation route is in the covering memo.
