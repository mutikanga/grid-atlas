# Request 14: UEDCL feeders at Central bulk supply points

- **To:** [name, role], UEDCL, through the introduction from UETCL management ([reference, date])
- **From:** Grid Atlas team, UETCL. Sponsor: Head of Network Operations
- **Date:** Monday 2 November 2026
- **Due:** Friday 13 November 2026. Not blocking: send what you have by then, and the rest can follow.

## Why we need it
Some generators connect to the 33 kV network rather than directly to UETCL's transmission grid. Unless we know which substation and feeder each one sits behind, our model counts its output twice or misses it. That skews two things in the Grid Atlas demo: the line-by-line loss figures and their check against NCC's monthly totals, and the MW each candidate industrial site can take, now and in 2030. Knowing how each substation's load splits across its feeders sharpens both.

**Not blocking.** NCC's substation data is our primary source, and our work does not wait for this request. Partial data, or data sent after the due date, still helps.

## What to send
We ask only for totals per feeder per month (aggregate data). Nothing here is customer-level or personal, so we understand no data-sharing MoU is needed. If UEDCL's rules say otherwise, please tell us and we will work with what you can share.

**Template:** `templates/T07_uedcl_feeders.xlsx` (attached), sheets `feeders` and `questions`. Its README sheet repeats these instructions. Your native format is welcome; the template lists the minimum fields.

**Period:** September 2025 to September 2026, 13 months (`2025-09` to `2026-09`), one row per feeder per month.

**Substations:** every UEDCL feeder that leaves a Central bulk supply point. Central means the substations in our scope: Kawanda, Mutundwe, Lugogo, Kampala North, Queensway, Namanve, Mukono, Kapeeka, Kabulasoke, Nkonge and Masaka, plus the Bujagali and Nalubaale delivery points. Tell us if we have missed a substation that supplies your Central network, or if one on the list has no UEDCL feeders.

1. **Monthly figures for every feeder** (sheet `feeders`). Include every feeder you operate that leaves the substation: normally 33 kV, plus any 11 kV feeder that leaves it directly. For each feeder and month:
   - `month` (YYYY-MM), `bulk_supply_point` (the UETCL substation), `feeder` (your name or code) and `kv` (the feeder voltage).
   - `peak_mw`: the month's highest demand from the substation into the feeder, in MW. `peak_at`: when it happened, as YYYY-MM-DD HH:MM in East Africa Time.
   - `energy_mwh`: energy delivered into the feeder in the month, in MWh. If power ever flowed back into the substation and your meter records it, give that energy in `reverse_flow_mwh`.
   - `power_factor`: the month's average, as a decimal (0.93, not 93).
   - `load_basis`: `net` if measured at the feeder head (the feeder's own generation already subtracted), `gross` if that generation is added back, `unknown` if you are not sure.
   - `quality`: `actual`, `estimated` (some readings estimated) or `partial` (data missing for part of the month).
   - `feeder_type`: the main load, one of `domestic`, `commercial`, `industrial`, `mixed`, `generator_only` or `other`.
   - `single_customer`: `Y` if the feeder supplies only one customer (see "What not to send").
   - `notes`: anything unusual, such as a feeder transfer, a long outage or a meter change.
2. **The generators on each feeder** (same sheet, same rows). Count every generator of 1 MW or more that can export into the feeder, wherever it connects downstream:
   - `embedded_gen_plants`: plant names, separated by `;`.
   - `embedded_gen_mw`: their total installed capacity in MW. Put 0 if there are none; leave it blank if you do not know.
   - `embedded_gen_mwh`: the energy they produced in the month, if metered.

   A line that connects only a generator counts as a feeder. Give it its own row, with `feeder_type` set to `generator_only`.
3. **Answers to the five questions below** (sheet `questions`, or a short note with your files).

**Units and format:** MW, MWh and kV, not kW or kWh. Excel or CSV; one file for all months or one per month. Use a decimal point and no thousands separators. Repeat `kv`, `feeder_type` and the generator columns on every month's row. Leave a cell blank if you do not have the figure, and do not fill gaps with estimates unless `quality` says `estimated`.

**If time is short, send this first:** the feeders at each substation with the generators on each, plus `peak_mw` and `energy_mwh` for September 2026 (`month` = `2026-09`). The other twelve months can follow.

## Questions to answer
1. Where are the meters behind these figures: at the feeder breaker inside the UETCL substation, or elsewhere on the feeder? Are they the same meters UETCL bills UEDCL from?
2. Are peak MW and MWh net of the generation on each feeder (measured at the feeder head), or gross (that generation added back)? If it differs by feeder, use the `load_basis` column.
3. How is power factor worked out: the month's average from MWh and MVArh, or the value at the time of the peak?
4. How long is the demand interval behind peak MW (15, 30 or 60 minutes)? Does the meter's time stamp mark the start or the end of that interval?
5. Between September 2025 and September 2026, did any feeder move to another substation, or was any feeder added, split or retired? Which, and when?

Questions 1 and 2 decide how we read the figures, so please answer them with the first files.

## What not to send
- No personal data: no customer names, account numbers, addresses or phone numbers, no readings for individual customers, and no staff names in the data files.
- No customer names at all, companies included. If a feeder supplies only one customer, set `single_customer` to `Y` and leave the customer unnamed. If you would rather not show that feeder on its own, add its figures to another feeder at the same substation and say so in `notes`.
- If a feeder's name identifies a customer, use a code instead (for example `EXA-F7`) and keep the key yourself.
- Nothing below feeder level: no distribution transformers, customer lists or network drawings.

We will not show feeder-level figures outside UETCL.

## How to deliver
Follow the handling note sent with this request (`docs/data-requests/handling-note.md`).
- Upload the files through the upload link we send you from an official UETCL email address: [upload link]. If that does not suit you, a team member can collect the files on a UETCL-issued drive and copy them straight to the UETCL share. We move them to the Atlas server's landing folder ourselves.
- Never send them by personal email, WhatsApp or other chat apps, or personal cloud storage (Google Drive, Dropbox, WeTransfer and the like), and never on a USB stick of unknown origin. Do not attach data to an email: upload the files, then tell us which files are there.
- Name each file with UEDCL, the content and the months, for example `UEDCL_feeders_2025-09_2026-09.xlsx`.
- To correct a file, upload it again under the same name and tell us it replaces the earlier one.
- When the files are uploaded, tell [name, phone]. If the link does not work, call the same number and we will agree a route that follows the handling note.

## Contact
[name, phone], Grid Atlas team, UETCL. Call with any question, or if 13 November does not suit you, so we can agree what to send first.

Thank you for your help.
