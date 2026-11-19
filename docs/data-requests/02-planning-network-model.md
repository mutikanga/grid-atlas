# Request 02: the national network model, as solved load-flow cases

- **To:** UETCL Grid Development and Planning: the engineers who keep the national load-flow cases
- **Cc:** Planning mentor to the Grid Atlas team
- **From:** Grid Atlas team (UETCL graduate trainees), under the covering memo from the Head of Network Operations
- **Date:** Monday 2 November 2026
- **Due:** Friday 6 November 2026. If the peak case is ready sooner, please send it straight away: we test the conversion on it first.
- **Template:** `templates/T01_network_model.xlsx` (attached), sheets `README`, `cases`, `buses`, `lines`, `transformers`, `transformers_3w`, `generators`, `loads`, `shunts`, `switches`, `boundary`, `solved_buses`, `solved_branches` and `changes`

## Why we need it

Your network model is the base of the Grid Atlas. Loaded into pandapower, an open-source load-flow tool, it colours the network map (demo item 1 in the scope of work), gives the monthly losses on every Central line and transformer from September 2025 to September 2026 for the check against NCC's totals (demo item 2, acceptance criterion 3), runs N-1 and the Kawanda page (demo item 3, criterion 4), and gives the MW each candidate industrial site can take now and in 2030 (demo item 4, criterion 5). We use your model as it is, so our results can be checked against your own studies: the Atlas supports Planning's work and does not replace it. Without it we can only hand-build an approximate model, which cannot pass the loss check.

This replaces row 1 of the data list in the scope of work: we now ask for the whole national network at every voltage level, not a Central extract at 220 and 132 kV. A national model compares like with like with NCC's losses, which cover the whole network; it gets the flows into Central right; and it saves you cutting out Central. We still report on Central only.

## What to send

Your native format is welcome; the template lists the minimum fields. If you send case files, you do not need the element sheets: fill in `cases` and `changes`, and give only the facts your files lack (item 3). If native files are hard to share, fill in all the sheets instead.

### 1. Three national solved cases
- **(a) As-operated peak, nearest September 2026.** The network as it stood, with the loads and dispatch of a real peak hour. If your nearest case is a planning base case for 2026 rather than a real hour, send it and say so.
- **(b) Light load.** A minimum-demand case (a night or weekend minimum), from 2026 if you have one. We use it to check for high voltages after an outage.
- **(c) 2030.** Your Grid Development Plan case for 2030, with the projects planned by then and Planning's load forecast per bulk supply point (item 5). If you hold several 2030 cases, send the one you treat as the reference and tell us which it is.

Each case should hold:
- **The whole national network** at every transmission voltage (400, 220 and 132 kV, and any other you model), plus the 33 kV busbar at each grid substation. Leave out the 33 kV network beyond that busbar.
- **Each transformer to 33 kV as its own element,** with its load on the 33 kV busbar, not lumped at 132 kV.
- **Three-winding transformers as three-winding elements,** with the rating and impedance of each winding.
- **Ratings:** every rating set your case holds. Tell us which is continuous, which is emergency, and which, if any, is NCC's operating limit and what sets it (question 3 and item 3).
- **Generators:** each unit's P and Q limits (MW, MVAr), voltage set-point (pu) and control mode (PV, PQ or swing). If you use reactive capability curves, send them too, in any format.
- **Taps as in service:** fixed (off-load) taps at the position set on site, and on-load tap changers at their solved position, with the voltage band they control to.
- **Shunts:** every capacitor bank and reactor, line reactors included, with MVAr per step and the steps switched in.
- **Normally-open points:** circuits, bus couplers and bus sections that are open in normal operation, shown open in the case, or listed in sheet `switches` if the case does not model them.

Format, by the tool you use:
- **PSS/E:** the .raw saved as version 33 or 35, and the .sav as well if convenient. Save each case after a solved load flow, so the voltages, taps and switched-shunt steps in the file are the solved ones.
- **PowerFactory:** the project export (.pfd), plus one file we can read without PowerFactory, whichever your licence allows: a CGMES export or a PSS/E RAW export (version 33 or 35); failing those, a DGS export. If none is possible, tell us: we will sit with you at your workstation and run the export together, at a time that suits you.
- **If case files cannot be shared:** fill in every sheet of the workbook instead. Sheet `boundary` is needed only for a case that is not the whole national network.

### 2. Your own solved results for each case
We convert your case into pandapower and solve it again. We accept the conversion only when it reproduces your solution: every bus voltage within 0.005 pu of yours, and branch flows within 1 to 2 % (within 1 MW on lightly loaded branches). We will send you and the Planning mentor the comparison. Until it passes, we use no result from the model. If it fails, we will bring you the buses and branches that differ.
- **Buses:** voltage (pu) and angle (degrees) at every bus. A .raw or .sav saved after the solve already holds these; just tell us it was saved solved.
- **Branches:** MW and MVAr at both ends of every line and transformer, and the loading in % against the rating your tool uses. A .raw file does not hold flows, so please export them.
- **Losses:** total losses of the case in MW, and by voltage level if your tool reports it.
- **Format:** your tool's own report or result tables, exported to Excel or CSV in any layout, with a line saying what each column holds. Or sheets `solved_buses` and `solved_branches`.

### 3. Facts your case files may not carry
Fill in sheet `cases` for every case: type, date and hour, tool and version, system base MVA, perimeter, what each rating set means (`rating_note`), and who to ask (a role is enough). Then, only where your files lack them, give these facts in the sheet named or in a plain list of your own:
- **NCC operating limits:** where protection, a CT ratio or stability limits a line or transformer below its rating, the limit in MVA and what sets it (`rate_ncc_mva` and `rate_ncc_basis` in `lines` and `transformers`). NCC is asked for its limits too (request 08); send what Planning holds.
- **The substation of each bus** (`buses`), where the bus name does not make it clear. We use it to match your buses to NCC, SCADA and GIS names.
- **Line length in km, conductor type and sub-conductors per phase** (`lines`). Length gives the losses per km and the check against the GIS routes.
- **The bulk supply point name** that NCC and Commercial use for each load (`bsp_name` in `loads`). We scale each load to NCC's metered energy through it.
- **Transformer no-load losses** in kW (`pfe_kw` in `transformers`), if the case leaves them out.
- **Commissioning year** (`commissioning_year` in `lines` and `transformers`), only if it is easy to add here. It then covers item 4 of request 03.

### 4. Network changes since September 2025 (sheet `changes`)
Every line, transformer, generator, shunt or busbar commissioned, retired, uprated or reconductored from 1 September 2025 to the date you send, with the date of each change. We work out losses month by month from September 2025, so we need to know what was in service in each month. Note in `detail` any change that is not yet in the peak case.

### 5. The 2030 load forecast
The forecast behind case (c): MW, and MVAr or power factor, at each bulk supply point for 2030 (other years too if they are in the same table); the scenario the case uses (base, high or other); and the date or edition of the forecast. Excel, as you hold it.

### 6. Your answers to the questions below
In your reply, or in a short note with the files.

**The minimum:** case (a) for the whole national network, as native files or the filled-in sheets, with your solved bus voltages and branch flows for it and the answer to question 3.

**If it cannot all come by Friday 6 November:** send the minimum by then, and tell us when the light-load case, the 2030 case and the rest will follow.

## Questions to answer
Questions 1 to 4 decide how we read your files, so please answer them with the first files.

1. Which tool and version do you use? Which RAW version or export did you send?
2. For each case: what date and hour does it stand for, and where do its loads and dispatch come from (NCC's records for that hour, a forecast, or scaled)?
3. What does each rating set in your files mean: continuous, emergency (for how long), or NCC's operating limit? At what ambient and conductor temperatures? Which rating does your tool use for the loading %?
4. Which solution options did you use: tap adjustment, switched-shunt adjustment, generator reactive limits (applied at once, after some iterations, or ignored), area interchange or active-power control, and the convergence tolerance?
5. Which bus is the swing (slack) bus in each case? Are the interconnections with neighbouring countries fixed MW injections or modelled lines?
6. Is the 400 kV infeed at Kawanda in each case, with every Kawanda transformer at every voltage level? We understand the infeed comes from Karuma; please confirm.
7. Does every grid substation have its 33 kV busbar and its own transformers to 33 kV in the case? Which loads, if any, sit at 132 kV with no transformer?
8. Are plants embedded in the 33 kV network modelled as generators at the 33 kV busbar, or netted off the load there?
9. Are any three-winding transformers modelled as three two-winding branches around a star-point bus? Which ones?
10. At what conductor temperature is line resistance given? Do your transformer models include no-load losses?
11. Which Grid Development Plan projects are in the 2030 case, and when does each enter service? Is the planned Kawanda relief among them? Which edition of the plan does the case follow?
12. Does any case carry a restriction on use or sharing, for example a consultant's licence, that we should record?

## What not to send
- **No personal data:** no staff names, initials, phone numbers or email addresses, including in case titles and comments. In the `contact` column of `cases`, a role is enough.
- **No customer names:** where a bus, load or substation is named after a customer, for example a customer's own substation, rename it in the copy you send to a code such as `DC-1`, and keep the key yourself. Power stations keep their names.
- **Not needed:** dynamic-simulation data, short-circuit (sequence) data, protection settings, or your whole PowerFactory database (only the projects that hold these cases). Contingency files go with request 03.
- If a file with personal data reaches us by mistake, we delete it, record that we did, and ask you for a clean copy.

## How to deliver
As set out in the handling note (`handling-note.md`, sent with this request):
- Put the files in the Grid Atlas folder on the UETCL share, or in the landing folder on the Grid Atlas server. The handling note gives both locations.
- Never use personal email, WhatsApp, USB sticks of unknown origin, or personal cloud storage (Google Drive, Dropbox, WeTransfer and the like).
- Start each file name with `T01` and the case, for example `T01_peak_case.raw`, `T01_peak_results.xlsx` or `T01_2030_forecast.xlsx`. Zip a case with its results if that is easier. If you correct a file, send it again whole under the same name and tell us it replaces the earlier one.
- Then tell the contact below which files you have put there. Do not attach the data to that message.
- If a file cannot leave your workstation, tell us and we will work through it with you there.

This is critical-infrastructure information. We keep it on UETCL systems, use it only for the Grid Atlas, and show nothing based on it outside UETCL until management has cleared it at the preview planned for Friday 20 November.

## Contact
[name, phone], Grid Atlas team (power systems). If anything here would take you more than an hour, call us first; there may be a simpler way. If something blocks the export, the escalation route is in the covering memo.

Thank you for your help.
