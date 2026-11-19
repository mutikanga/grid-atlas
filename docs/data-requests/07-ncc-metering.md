# Request 07: NCC metering for a Central energy balance

**To:** UETCL NCC, metering and energy accounting  
**Cc:** NCC mentor to the Grid Atlas team  
**From:** Grid Atlas team, under the covering memo from the Head of Network Operations  
**Date:** Monday 2 November 2026  
**Due:** Friday 6 November 2026  
**Template:** `templates/T03_ncc_monthly.xlsx`, sheets `README`, `boundary_meters`, `internal_meters` and `definitions` (questions Q3 to Q6 and Q11 to Q14). The other sheets in the workbook are for NCC reporting (request 05).

## Why we need it
Acceptance criterion 3 (demo item 2) compares the model's monthly losses for Central with metered losses, but as far as we know NCC reports losses only for the whole grid. A Central figure has to come from an energy balance at the Central boundary:

> Central losses = energy imported over boundary circuits + generation inside Central − energy delivered to UEDCL and direct customers − energy exported over boundary circuits

Accuracy classes tell us how much of any gap could be meter error. Knowing whether substation loads are net or gross of embedded plants stops 33 kV generation being counted twice, or not at all.

## What to send
Your native format is welcome; the template lists the minimum fields. If your energy accounting already holds these figures, send its monthly export as it is (Excel or CSV), with a short note on what each column means.

For every meter below:
- **Period:** each month from September 2025 to September 2026 (13 months).
- **One total per meter per month in each direction,** as separate rows, even when one of them is zero.
- **Units:** active energy in MWh and reactive energy in MVArh, as primary values, with CT and VT ratios applied (see Q12).
- **Where the meter is:** meter ID, substation, the line, transformer or feeder it is on, which end of a line, and which side of a transformer.
- **Accuracy:** the meter's accuracy class, and the CT and VT classes if you know them.
- **Estimated readings:** `estimated` = `Y` for any month with estimated or substituted readings.

**The Central boundary.** We use the substations in the MVP scope of work: Kawanda, Mutundwe, Lugogo, Kampala North, Queensway, Namanve, Mukono, Kapeeka, Kabulasoke, Nkonge and Masaka. The scope of work also names the Bujagali and Nalubaale delivery points; for metering we treat the circuits from them as boundary circuits. Correct the list if it is wrong or incomplete, and tell us if your energy accounting draws Central differently (Q3).

1. **Boundary meters** (sheet `boundary_meters`). Every circuit that links a Central substation to a substation or plant outside the list, at least:
   - the 400 kV infeed to Kawanda;
   - Bujagali–Kawanda;
   - Masaka–Mbarara;
   - any circuit arriving from Nalubaale or the Jinja side.

   Send the meter at whichever end it is. If a circuit is metered at both ends, send both and mark the one you use for accounting as `main`. Direction: `import` is into Central, `export` is out of Central.

   Columns: `month`, `meter_id`, `substation` (the Central end), `circuit`, `far_end_substation`, `circuit_kv`, `line_end` (where the meter sits), `hv_or_lv`, `direction`, `energy_mwh`, `energy_mvarh`, `accuracy_class`, `ct_vt_class`, `main_or_check`, `estimated` and `notes`. If a boundary circuit has no meter, name it in your answer to Q3.

2. **Every generator inside Central** (sheet `internal_meters`, `point_type` = `generator`). Every plant, whatever its size or voltage, including plants on 33 kV feeders. Our working list, from the scope of work, is Namanve thermal and the solar plants at Kabulasoke, Nkonge and Kapeeka; add any we have missed. For each plant:
   - energy sent out (`into_grid`), and energy taken from the grid for the plant's own use (`out_of_grid`);
   - `connection_kv`: the grid voltage it connects at;
   - `substation`, and in `circuit` the 33 kV feeder if it is on one;
   - `substation_load_basis`: whether NCC's reported load for that substation is `net` of this plant's output (already taken off) or `gross` (added back).

3. **Every bulk supply point and direct customer inside Central** (sheet `internal_meters`, `point_type` = `bsp` or `direct_customer`). Every supply point to UEDCL, at whatever voltage it is metered, and every customer UETCL supplies directly. For each:
   - energy delivered (`out_of_grid`), and any reverse flow back into the grid (`into_grid`);
   - in `circuit`, the transformer or bay the meter is on; `metering_kv`; and `hv_or_lv`, the side of the transformer the meter is on;
   - a direct customer is named only by a code such as `DC-1`, never by name. If NCC operations has already given the customer a code for request 08, use the same one.

   Add substation station-supply meters (`point_type` = `station_supply`) if you have them.

   Columns for items 2 and 3: `month`, `meter_id`, `substation`, `point_type`, `point_name`, `circuit`, `connection_kv`, `metering_kv`, `hv_or_lv`, `direction`, `energy_mwh`, `energy_mvarh`, `accuracy_class`, `ct_vt_class`, `main_or_check`, `estimated`, `substation_load_basis` (plants only) and `notes`.

4. **A monthly Central balance, if NCC already produces one** (for Central or a Kampala-metro zone): all 13 months, with the list of meters it uses.

5. **Your meter register, if you keep one:** meter ID, location, CT and VT ratios, and accuracy classes. If you send it, you may leave the location and class columns blank in the monthly rows.

6. **Your answers to the questions below**, in sheet `definitions` or in your reply.

**If it cannot all come by Friday 6 November:** send the boundary meters and the answers to Q3, Q11 and Q12 first, and tell us when the rest will follow.

## Questions to answer
Answer in sheet `definitions` (column `answer`) or in your reply. "Not known" is a useful answer. Q3, Q5 and Q6 also go to NCC reporting (request 05); one joint answer is fine.

- **Q3.** Can NCC produce a monthly energy balance for the Central region from boundary meters? If your energy accounting already uses a Central or Kampala-metro zone, which substations does it cover? Which boundary circuits have no meter?
- **Q4.** Are the bulk supply point meters on the HV (132 kV) or LV (33 kV) side of the 132/33 kV transformers? Name any that differ.
- **Q5.** Are the substation loads in the Summary net of generation embedded at 33 kV (the plant's output already taken off) or gross (the plant's output added back)? Does this differ by substation or plant?
- **Q6.** Which months contain estimated or substituted readings, and for which figures or meters? Was any month's Summary revised after it was issued?
- **Q11.** Is the 400 kV infeed to Kawanda metered? At which end of the line, and at which voltage?
- **Q12.** Are the energies you send primary values, with CT and VT ratios already applied? If not, give the multiplier for each meter.
- **Q13.** How are missing or faulty readings filled: from a check meter, from SCADA, or estimated? Which boundary or Central meters were replaced, recalibrated or faulty between September 2025 and September 2026, and when?
- **Q14.** Do the boundary meters store interval data (15- or 30-minute load profiles)? If so, which ones? We may ask for three months of it later; nothing is needed now.

## What not to send
- **No customer names, account numbers or contact details:** direct customers by code only.
- **No personal data:** no staff names (for example on meter-reading sheets) and no phone numbers.
- **No access details:** no meter passwords, communication settings, IP addresses or modem numbers.
- **No billing:** we do not need invoices, amounts or tariffs here. Commercial covers those in request 09.

## How to deliver
As set out in the handling note (`handling-note.md`, sent with this request):
- Put the files in the Grid Atlas folder on the UETCL share, or in the landing folder on the Grid Atlas server. The handling note gives both locations.
- Never use personal email, WhatsApp, USB sticks of unknown origin, or personal cloud storage.
- Start each file name with `T03` and say what it holds, for example `T03_boundary_meters_2025-09_to_2026-09.xlsx`. If you correct a file, send it again under the same name and tell us it replaces the earlier one.
- Then tell the contact below which files you have put there. Do not attach the data to that message.
- The data stays on UETCL systems. Nothing based on it is shown outside UETCL until management has cleared it at the preview planned for Friday 20 November. If an item must never leave UETCL, mark it and we will follow your marking.

## Contact
[name, phone], Grid Atlas team. If something blocks the request, the escalation route is in the covering memo.
