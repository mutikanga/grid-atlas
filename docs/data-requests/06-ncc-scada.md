# Request 06: hourly SCADA data for Central

**To:** UETCL NCC, SCADA / historian team  
**Cc:** NCC mentor to the Grid Atlas team  
**From:** Grid Atlas team (graduate trainees), under the covering memo from the Head of Network Operations  
**Date:** Monday 2 November 2026  
**Due:** Friday 6 November 2026. Please send the point list and the sample days (item 5) first, as soon as they are ready.  
**Template:** `templates/T04_scada.xlsx`, sheets `README`, `points`, `hourly_data`, `breaker_changes` and `questions`

## Why we need it
Hourly MW and MVAr turn our load flows into monthly MWh losses for every Central line and transformer, reconciled with NCC's monthly totals: demo item 2 and acceptance criterion 3 (the 10 % loss check). They also let us check the model against measured flows and voltages, and give Kawanda's measured loading for the N-1 run and the Kawanda page (demo item 3 and criterion 4).

This replaces row 4 of the data list in the scope of work, which asked for two sample days a month. Two days a month is now the minimum, not the target.

## What to send
Your native format is welcome; the template lists the minimum fields. If your historian exports a different layout, send it as it is, with a short note on what each column means.

### 1. The point list (sheet `points`)
One row for every point in the data files. A tag export from the historian with these facts is fine.

| Column | What to put | Required |
|---|---|---|
| `point_id` | Your tag or point ID, exactly as in the data files | yes |
| `substation` | Substation name as you use it | yes |
| `bay` | Bay name. For a direct customer's bay, a code such as `DC-1`, not the customer's name | yes |
| `voltage_kv` | Nominal voltage of the bay or busbar, in kV | |
| `element_type` | `line`, `transformer`, `generator`, `bsp` (a bulk supply point: a bay supplying UEDCL or a direct customer), `busbar` or `other` | yes |
| `remote_substation` | Lines only: the substation at the other end | |
| `winding` | Transformers only: `hv`, `mv` or `lv` (`na` for other points) | |
| `element_ref` | Planning model ID, only if you know it | |
| `quantity` | `P`, `Q`, `V` or `I` | yes |
| `unit` | `MW`, `MVAr`, `kV` or `A` | yes |
| `sign_convention` | What a positive value means, for example "+ = from the busbar into the line" | |
| `interval_minutes` | 60 or 30 | |
| `notes` | Calculated point, faulty since a date, CT changed, and so on | |

### 2. Hourly data for all 13 months (layout in sheet `hourly_data`)
- **Points:** every measurement point in Central and on its infeeds:
  - MW and MVAr at every line end, every transformer winding, every generator and every bulk supply point;
  - kV (phase to phase) on every busbar;
  - amps only where a bay has no MW measurement.

  33 kV outgoing feeders are needed only where a grid transformer's 33 kV side is not measured.
- **Stations:** Kawanda, Mutundwe, Lugogo, Kampala North, Queensway, Namanve, Mukono, Kapeeka, Kabulasoke, Nkonge and Masaka; the Bujagali and Nalubaale delivery points; and the ties into Central, including Bujagali–Kawanda, Masaka–Mbarara and the 400 kV infeed at Kawanda, at both ends where measured. This is the list in the MVP scope of work. Tell us if we have missed a station.
- **Period:** every hour from 1 September 2025 00:00 to 30 September 2026 23:00 (EAT).
- **Granularity:** the average over each hour. 30-minute averages are welcome too. If the historian can only give instantaneous samples, send those and say so.
- **Format:** one CSV file per month, 13 files named `scada_2025-09.csv` to `scada_2026-09.csv`. Comma-separated, with a header row and five columns, one value per row:

  ```
  timestamp,point_id,value,unit,quality
  2026-03-12 20:00,EXA.L1.P,92.4,MW,good
  2026-03-12 20:00,EXA.L1.Q,18.1,MVAr,good
  2026-03-12 20:00,EXA.BB1.V,133.2,kV,estimated
  ```
  EXA (Example A) is a dummy name, and the numbers are not real.
  - `timestamp`: `YYYY-MM-DD HH:MM` in East Africa Time (UTC+3), at the **start** of the interval. `2026-03-12 20:00` is the average from 20:00 to 21:00.
  - `point_id`: as in the point list.
  - `value`: in the point's unit (MW, not kW), with a decimal point and no thousands separators.
  - `unit`: `MW`, `MVAr`, `kV` or `A`.
  - `quality`: your flag mapped to `good`, `bad`, `estimated`, `substituted` or `missing`. Keep doubtful values with their flag. Do not fill gaps or edit values; leave an hour out only if the historian holds no value for it.
- **Size:** 200 points make about 150,000 rows (roughly 6 MB) a month. Zip the files if that helps.

### 3. Priority points
If everything cannot come at once, send these points for all 13 months before the other points:
- every bay at Kawanda, at every voltage: each line, each transformer winding and the 400 kV infeed;
- the ties that cross the Central boundary (listed above), at both ends where measured;
- MW and MVAr on every 132/33 kV transformer in Central;
- kV on every 132 kV and 220 kV busbar in Central.

### 4. If the historian does not hold all 13 months
Send what it holds, most recent months first (September 2026, then August 2026, and so on). Tell us the first month it holds. If the historian will soon delete its oldest months, please copy them out now so they are not lost, even if you send them later.

### 5. The minimum: sample days, sent first
Whatever else you send, please export these days first. They are the least we can work with.
- **Which days:** for each month, the peak day and the light-load day, plus a Kawanda day where there is one.
  - **Peak day:** the day of the month's system peak.
  - **Light-load day:** the day with the month's lowest demand, usually a Sunday or public holiday. Skip a day with a major outage or blackout.
  - **Kawanda day:** a day that month when the Kawanda constraint bound, if NCC knows of one.
- **Who picks them:** NCC reporting has been asked to list these days in request 05 (sheet `sample_days` of `templates/T03_ncc_monthly.xlsx`), if possible by Wednesday 4 November. We will pass their list on to you as soon as it arrives. Use their days. If they have not arrived when you are ready, pick the days by the rules above and tell us which you used.
- **What:** all 24 hours of each day, every point, in the CSV layout of item 2.

Whole months are much better than two days. Losses grow with the square of the flow, so every extra day makes the monthly MWh more accurate.

### 6. Breaker changes (sheet `breaker_changes`), useful but not blocking
Every open or close of a circuit breaker on a Central bay, 1 September 2025 to 30 September 2026: `timestamp` (EAT), `substation`, `bay`, `breaker_id`, `new_state` (`open` or `closed`) and `reason` (trip, planned outage or switching). A plain export of the event list is fine, without operator names. Send it after the hourly data if needed.

### 7. Your answers to the questions below
In sheet `questions`, or in your reply.

**If it cannot all come by Friday 6 November:** send it in this order, each part as soon as it is ready, and tell us when the rest will follow:
- first, the point list (item 1) and your answers to questions 1 to 3;
- then the sample days (item 5), every point;
- then the priority points (item 3), all 13 months;
- then everything else.

By Friday 6 November, please send at least the point list, the answers and the sample days, and the priority points too if you can.

## Questions to answer
Questions 1 to 3 decide how we read the data, so please answer them with the first files.

1. What time zone are the timestamps in, and does each one mark the start or the end of the interval?
2. Are the values averages over the interval or instantaneous samples? If averages, how often is the raw value scanned?
3. What does a positive MW or MVAr value mean at a line end, a transformer winding, a generator and a bulk supply point? We assume positive means power flowing from the busbar into the bay.
4. How far back does the historian hold hourly or finer data? Which months, stations or points are missing or partial between September 2025 and September 2026?
5. What quality flags does the historian use, and how did you map them to good, bad, estimated, substituted and missing?
6. Which Central bays have no MW and MVAr measurement, or one you know is faulty or out of calibration? Since when?
7. On which side (HV, LV or both) are the Kawanda transformers and each 132/33 kV transformer measured? Is the 400 kV infeed at Kawanda measured, and at which end?
8. Does the historian also keep transformer tap positions and capacitor or reactor switching? Just tell us; we are not asking for them now.
9. Is our station list complete? Name any Central station or infeed we have missed.

## What not to send
- **No personal data:** no operator or staff names, user IDs or phone numbers, and no log comments that name people.
- **No customer names:** where a bay or tag name carries a customer's name, replace it with a code such as `DC-1`, the same code for the same customer in every file. If NCC operations has already given that customer a code for request 08, use the same one. Keep the key to the codes yourself.
- **No access details:** no passwords, IP addresses, RTU addresses or communications settings.
- **No live connection:** we want exported files only. Nothing in the Grid Atlas connects to SCADA or the historian.

## How to deliver
As set out in the handling note (`handling-note.md`, sent with this request):
- Put the files in the Grid Atlas folder on the UETCL share, or in the landing folder on the Grid Atlas server. The handling note gives both locations.
- Never use personal email, WhatsApp, USB sticks of unknown origin, or personal cloud storage (Google Drive, Dropbox, WeTransfer and the like).
- Keep the CSV file names above. If you send a month in parts, give each part its own name, for example `scada_2026-03_days.csv` and `scada_2026-03_priority.csv`, so that no part overwrites another. Start the name of any other file with `T04` and say what it holds, for example `T04_points.xlsx` or `T04_breaker_changes.csv`.
- Zip large files. If you correct a file, send it again whole under the same name and tell us it replaces the earlier one.
- Then tell the contact below which files you have put there. Do not attach the data to that message.

## Contact
[name, phone], Grid Atlas team. If something blocks the export, the escalation route is in the covering memo.
