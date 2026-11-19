# Request 08: the Kawanda constraint, curtailment and the outage log

**To:** UETCL NCC, operations: whoever keeps the operating limits, the curtailment instructions and the incident log  
**Cc:** NCC mentor to the Grid Atlas team  
**From:** Grid Atlas team, under the covering memo from the Head of Network Operations  
**Date:** Monday 2 November 2026  
**Due:** Friday 6 November 2026. If you can, send part A by Wednesday 4 November: it decides which element we model this week.  
**Template:** `templates/T05_ncc_operations.xlsx`, sheets `README`, `questions`, `constraints`, `constraint_hours`, `curtailments`, `deferred_connections` and `events`

## Why we need it
The Kawanda page of the Grid Atlas is the constraints step of the ERA SDP demo and the subject of acceptance criterion 4: our N-1 results must match a constraint NCC knows. Without your records we cannot be sure we model the right element, or add back the demand that was curtailed. The incident log also gives the dashboard its count of incidents due to constraints, tells the loss model which elements were out each month, and shows the site scores how often each line and transformer trips, and for how long.

## What to send
Your native format is welcome; the template lists the minimum fields. If your log or system exports a different layout, send it as it is, with a short note on what each column means. Use the sheets only for what your own files lack.

For every item, unless it says otherwise:
- **Period:** 1 September 2025 to 30 September 2026 (13 months).
- **Times:** East Africa Time, written `YYYY-MM-DD HH:MM`, to the minute where your records have it.
- **Units:** MVA, MW, MWh and kV, as named in each column.
- **Area:** the Central substations Kawanda, Mutundwe, Lugogo, Kampala North, Queensway, Namanve, Mukono, Kapeeka, Kabulasoke, Nkonge and Masaka; the Bujagali and Nalubaale delivery points; and the lines and transformers that feed Central, including Bujagali–Kawanda, Masaka–Mbarara and the 400 kV infeed at Kawanda. This is our working list; tell us if we have missed anything. If filtering is extra work, send the national records and we will filter them.
- **Customer codes:** never a customer's name. Give each customer a code such as `DC-1` (data centre) or `IND-1` (industrial), and keep the same code for the same customer in every sheet. The SCADA and metering requests (06 and 07) also code customers and ask for the codes you give here, so please agree one set within NCC. Keep the key to the codes yourselves.

### A. The Kawanda constraint (please send first)
We will model whichever element you name, and we will not choose the element tripped in the demo until you have confirmed it.

1. **Answers to questions Q1 to Q8** below, in sheet `questions` or in your reply.
2. **The constraint itself** (sheet `constraints`, first row, code `KAW-1`):
   - the limiting element, named as on your single-line diagram, and whether it is a transformer, a line, a busbar or something else;
   - its voltage: for a line, its kV; for a transformer, both voltages;
   - the operating limit NCC applies, in MVA, and also in MW or amps if that is how you apply it;
   - what sets that limit (thermal rating, protection setting, CT ratio, stability or other), and the nameplate or continuous rating if it is different;
   - any short-time emergency limit allowed after a trip, and for how long;
   - whether it binds with everything in service (N-0) or only after an outage (N-1), and for N-1 the outage that makes it bind;
   - any special protection, inter-trip or automatic load-shedding scheme tied to it;
   - the relief project, the capacity it adds, and the month it is due in service;
   - the month it first bound.

   If more than one element limits Kawanda, add rows `KAW-2`, `KAW-3`. If one limit covers a group, for example two transformers together, use one row and name them all.
3. **When it bound** (sheet `constraint_hours`). "Bound" means the loading reached the limit, or NCC had to act to keep within it. One row per period, a single hour or longer, with:
   - start and end;
   - the highest loading, as a percentage of the limit, and the highest MW;
   - any elements out of service at the time;
   - what NCC did;
   - where the times come from: SCADA, operator log, instruction or estimate.

   If you keep no such record, say so; we will find the hours from the SCADA data in request 06.
4. **Every curtailment and load-shedding action in Central, whatever the reason** (sheet `curtailments`). We need every reason, not only Kawanda, so we can separate Kawanda from generation shortfall. One row per customer or feeder per instruction, with:
   - start and end;
   - substation, and the voltage the load is supplied at;
   - customer category (data centre, industrial, export, domestic feeder or other) and customer code, or for feeder shedding the feeder;
   - MW curtailed, and MWh if you worked it out;
   - how it was done: customer curtailment, feeder shedding or an automatic scheme;
   - the reason NCC recorded at the time (Kawanda constraint, other network constraint, generation shortfall or other), and the constraint code;
   - your instruction reference.
5. **The standing curtailment and load-shedding instructions** for Kawanda and the rest of Central: which customers or feeders are curtailed or shed, at what loading, and in what order. PDF or scans are fine. Replace customer names with their codes and remove staff names before you send them. For instructions issued case by case, the reference in item 4 is enough.
6. **Connection applications deferred because of a constraint** (sheet `deferred_connections`): every application in Central that was deferred, refused or left pending at any time from September 2025 to September 2026 because of Kawanda or another constraint. One row per application, with:
   - application date, and substation or area;
   - customer category and customer code, and the application number if you know it (it lets us match Planning's list in request 10 without names);
   - MW applied for, and when supply was wanted;
   - whether firm or interruptible supply was asked for;
   - status today (deferred, refused, pending or connected later), and the month connected or now offered;
   - the reason given, and the constraint code.

   If Planning or Commercial holds this list, tell us who (Q12) and we will ask them.

### B. Other constraints in Central
7. **Every other Central element with an NCC operating limit below its rating, or that bound at any time in the period:** more rows in sheet `constraints`, with the same facts as item 2 and a code of your choice. Put each special protection, inter-trip or automatic load-shedding scheme in the `special_scheme` column of the constraint it protects, and describe any other scheme in your answer to Q9.
8. **When they bound:** more rows in sheet `constraint_hours`, if you keep them.

### C. The incident and outage log
9. **The log for all 13 months** (sheet `events`): every forced trip, planned outage, curtailment or load-shedding action, blackout and disturbance in the area above. One row per element tripped or switched out, with:
   - your incident reference, the same on every row of one incident;
   - start, and end (when the element or supply was restored);
   - substation, element and its voltage;
   - event type: forced trip, planned outage, load shedding (including the curtailment of a customer), blackout, disturbance or other;
   - MW lost and MWh not supplied;
   - the cause in our codes (table below), and in your own words or code;
   - whether a constraint caused it (`Y` or `N`), and the constraint code if `Y`.

   Mark `Y` when a network limit caused the event, or the action was taken to stay within one, for example load shed to protect Kawanda. This is what we count as an incident due to a constraint. Curtailment and load shedding stay in this log as well as in item 4: the log gives the count, and item 4 gives the MW by customer category.
10. **Your list of cause codes** and what each means, if your log uses its own. We will map them to ours:

| Our code | Use it when |
|---|---|
| `constraint` | a network limit was reached |
| `protection` | protection operated wrongly |
| `equipment` | equipment failed |
| `weather` | lightning, wind or rain |
| `vandalism` | theft or damage |
| `generation` | a generation shortfall or a plant trip |
| `human_error` | a switching or operating error |
| `unknown` | the cause was not found |
| `other` | anything else; say what in your own words |

**If it cannot all come by Friday 6 November:** send part A and the log as it stands by then, and tell us when the rest will follow.

## Questions to answer
Answer in sheet `questions` or in your reply. Q1 to Q8 decide how we model Kawanda, so please answer them first.

- **Q1.** Our notes call it the "Kawanda Tx constraint", and Tx can mean transformer or transmission. Which element limits Kawanda: a transformer, a line, a busbar or something else? Name it as on your single-line diagram, with its voltage (for a transformer, its ratio in kV; for a line, its kV, both ends and circuit number).
- **Q2.** What is its operating limit, in MVA, and in MW or amps if that is how you apply it? What sets it: the thermal rating, a protection setting, a CT ratio, stability or something else? If it is below the nameplate rating, why?
- **Q3.** Does it bind with everything in service (N-0), or only after an outage (N-1)? If N-1, which outage makes it bind? Is a short-time emergency limit allowed after a trip, and for how long?
- **Q4.** Is any special protection, inter-trip or automatic load-shedding scheme tied to it? What does it measure, what does it trip, and when does it act (for example, above what loading)?
- **Q5.** When did it first bind? Roughly how often did it bind from September 2025 to September 2026, at what times of day, and is it still binding?
- **Q6.** The board paper says that, with two Karuma units out in September 2026, UETCL curtailed data centres and exports. A margin note on the paper links that curtailment to the Kawanda constraint instead. Which cause did NCC record for each curtailment and load-shedding action? If both applied, how did you split them?
- **Q7.** When customers were curtailed, do SCADA and the monthly reports show the reduced load? Is there a record of what they would have drawn without curtailment, for example their requested or contracted MW?
- **Q8.** What is the relief project, what will it add (MVA or circuits), and when is it due in service? Who holds its details?
- **Q9.** Which other elements in Central have an NCC operating limit below their rating, or bound at any time from September 2025 to September 2026? Are there special protection schemes in Central that are not tied to one of them? Give each constraint a row in the `constraints` sheet.
- **Q10.** How does your incident log record causes? Please send your cause codes with their meanings, and tell us how an incident caused by a constraint is marked.
- **Q11.** Is the log complete for all 13 months? Note any gaps or changes in how it was kept. Are times in East Africa Time, and are both the trip and the restoration times recorded?
- **Q12.** Who holds the list of connection applications deferred because of Kawanda: NCC, Planning or Commercial? If not NCC, whom should we ask?

## What not to send
- **No personal data:** no names, phone numbers or email addresses of customers or staff, including duty engineers named in logs and instructions. Replace a name with a role, or delete it.
- **No customer names or account numbers:** use the customer codes described above.
- **No setting files or access details:** no relay setting files, passwords, IP addresses or remote-access details. We need each limit, what sets it and when a scheme acts, in plain figures, not the setting files.

## How to deliver
As set out in the handling note (`handling-note.md`, sent with this request):
- Put the files in the Grid Atlas folder on the UETCL share, or in the landing folder on the Grid Atlas server. The handling note gives both locations.
- Never use personal email, WhatsApp, USB sticks of unknown origin, or personal cloud storage.
- Start each file name with `T05` and say what it holds, for example `T05_events_2025-09_to_2026-09.xlsx`. If you correct a file, send it again under the same name and tell us it replaces the earlier one.
- Then tell the contact below which files you have put there. Do not attach the data to that message.
- The data stays on UETCL systems. Nothing based on it is shown outside UETCL until management has cleared it at the preview planned for Friday 20 November. If an item must never leave UETCL, mark it and we will follow your marking.

## Contact
[name, phone], Grid Atlas team. If something blocks the request, the escalation route is in the covering memo.
