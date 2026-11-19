# Request 10: Planned projects and large-load connections in Central

- **To:** UETCL Grid Development and Planning (connections, and Grid Development Plan projects); UETCL Commercial
- **Cc:** Planning mentor to the Grid Atlas team
- **From:** Grid Atlas team (UETCL graduate trainees), under the covering memo from the Head of Network Operations
- **Date:** Monday 2 November 2026
- **Due:** Friday 13 November 2026
- **Template:** `templates/T08_projects_and_loads.xlsx` (attached), sheets `README`, `questions`, `projects`, `committed_loads`, `sgr_points` and `ilds_sites`

## Why we need it

- **Industrial sites (acceptance criterion 5 in the scope of work).** Each candidate site shows the MW it can take now and in 2030, and its unserved-energy risk. We show that risk as firm headroom in MW: what the substation can supply with one element out, minus the load already committed there. So we need the committed load.
- **The 2030 case.** It adds the Grid Development Plan projects and puts new load where it is actually coming, instead of growing every substation at one rate.
- **Kawanda page.** It compares the demand waiting to connect with Kawanda's headroom before and after the planned relief.

## What to send

Your native format is welcome; the template lists the minimum fields. Each team can send its own copy of T08 with only its sheets filled.

1. **Large loads in Central** (Planning connections and Commercial). Sheet `committed_loads`. Every load of 1 MW or more, supplied or to be supplied from a Central substation, that is:
   - connected since 1 September 2025 (so we neither miss it nor count it twice);
   - signed: connection agreement signed, not yet connected;
   - pending: offered, approved or on hold, not yet signed;
   - applied: application received and under study.

   For each load: a reference that does not name the customer; type (data centre, industrial park, manufacturing, railway traction, commercial, other); supplying substation and connection voltage; MW, and whether that is the requested, contracted or expected peak figure; power factor if stated; firm or interruptible; status; the month it starts drawing power; whether it sits at an ILDS (Industrial Load Development Strategy) anchor site; and any project or network limit it is waiting for. A load that comes in phases is one row per phase. Give the status as at the date you send. If Planning and Commercial both hold the same load, send it once.

   Include applications held back by a network limit, for example at Kawanda, with `waiting_for` filled in. NCC is asked for its own list of deferred applications (request 8). If you can, use your application number as `load_ref`: it lets us match the two lists without any names.
2. **ILDS anchor sites**, only if a list exists. Sheet `ilds_sites`. The ILDS anchor sites in Central: name, district, expected load type and MW, the substation expected to supply each, expected start, and location if known. If the list is held outside UETCL, tell us who holds it.
3. **SGR (standard gauge railway) traction supply points** in or near Central. Sheet `sgr_points`. For each traction supply point: the supplying substation, supply voltage, expected peak MW, the month supply is needed, how firm the plan is, and location if known.
4. **Grid Development Plan projects in Central, with parameters** (Planning). Sheet `projects`. Every line, substation, transformer, reconductoring and compensation project in Central, or on a line that feeds it, due in service by the end of 2030:
   - type, status (planned, committed or under construction) and expected in-service month;
   - substations, kV, circuits, length and conductor;
   - MVA per transformer unit or rating per line circuit, number of transformer units, and MVAr for compensation;
   - the existing element it replaces or uprates;
   - the source: plan edition and table, or project file.

   If a project is in your 2030 case (request 2), its element IDs in `model_ref` with the basic fields are enough. The Planning mentor is asked for the Kawanda relief under request 3; list it once, with `relief_for` = Kawanda.

Format: Excel preferred; PDF extracts of the plan are fine.

## Questions to answer

Answer in the `questions` sheet, or in your reply.

1. What does the MW in your list of connection applications mean: the applied-for maximum demand, the contracted capacity, or the expected peak draw? If you know how quickly large loads usually ramp up to it, say so.
2. Which applications are on hold because of a network limit, for example at Kawanda? Which project would release them, and when?
3. Which loads are interruptible by agreement, and on what terms (notice period, hours per year)?
4. Do any of these loads bring their own generation? If so, what MW will they draw from the grid at peak?
5. Is there an ILDS anchor-site list? If it is held outside UETCL, who holds it, and can it be shared?
6. SGR traction supply: which substations will supply it, at what voltage, and from when? Is the supply agreed?
7. Which edition of the Grid Development Plan is current? Which Central projects have changed date or scope since it was issued?
8. Does your list cover large loads that UEDCL will connect from a Central substation? If not, who holds them?

## What not to send

- No customer or company names, contact persons, phone numbers, account numbers or addresses. Put your application number or another code in `load_ref`, and keep the key yourself.
- No copies of applications, agreements, invoices or tariff terms.
- No other personal data.

## How to deliver

Follow the handling note (`handling-note.md`) sent with this request.

- Put the files in the UETCL share folder or the Atlas server landing folder named in the handling note.
- Then send the contact below a short UETCL email, without attachments, listing the file names, so we can log what arrived.
- If a file cannot leave your workstation, tell us and we will work through it with you there.
- Never use personal email, WhatsApp, personal cloud storage, or USB sticks of unknown origin.

## Contact

- Loads, ILDS sites and SGR: [name, phone], Grid Atlas team (economics and sites).
- Projects and the Kawanda relief: [name, phone], Grid Atlas team (power systems).

If part of this is ready before the rest, please send it as it is ready. If the due date is a problem, or anything here is unclear, tell us early; the covering memo gives the escalation route.
