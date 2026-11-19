# Covering memo (request 1): Grid Atlas data requests

**INTERNAL MEMO, for signature by the Head of Network Operations on Monday 2 November 2026**

- **To:** Grid Development and Planning (including the GIS unit); NCC (reporting, SCADA, metering and operations); Commercial; ICT and Information Security; the Data Protection Officer. For the attention of the head of each unit.
- **Cc:** Planning mentor and NCC mentor to the Grid Atlas team; the Grid Atlas team
- **From:** Head of Network Operations, sponsor of the Grid Atlas
- **Date:** Monday 2 November 2026
- **Reference:** [memo reference]
- **Subject:** Grid Atlas: read-only copies of data, due Friday 6 and Friday 13 November 2026

## Authority
This memo rests on [Board/management approval of recommendations 3 and 5, ref], from the board paper "UETCL Grid Atlas" of 15 October 2026. On that basis, I ask each unit below to give the Grid Atlas team read-only copies of the data listed, by the dates shown.

## Purpose
- The Grid Atlas is a trainee showcase for the ERA SDP session in late November 2026: a map of the Central transmission network showing where energy is lost, where the network is constrained (including Kawanda) and where new load could connect.
- It is advisory. It makes no decisions; planning and operating decisions stay with Planning and NCC.
- It uses read-only copies held on the NCC server, and it is never connected to SCADA, EMS or any other control system.

## What I ask of each unit
1. Name one contact for each dataset in the table below, and give the name to the team contact by Tuesday 3 November.
2. Send the data by the due date, as set out in the request note for your unit. Your native format is welcome; the template lists the minimum fields.
3. Send each part as soon as it is ready. Part of the data early helps more than all of it late.
4. If a due date cannot be met, tell the team contact as soon as you know: what you can send, and when.
5. Follow the attached handling note for every file.

## The requests
| # | Data or decision | Holder | Holder contact | Team contact | Due |
|---|---|---|---|---|---|
| 1 | This memo, the contacts and the management preview | Head of Network Operations | [name, phone] | [name, phone], team lead | Mon 2 Nov |
| 2 | Network model: national solved cases at all voltages, with ratings and Planning's own solved results | Grid Development and Planning | [name, phone] | [name, phone] | Fri 6 Nov |
| 3 | Contingency studies and criteria; Kawanda relief scope and date; commissioning years; unit costs | Planning mentor | [name, phone] | [name, phone] | Fri 13 Nov |
| 4 | GIS layers: substations and circuits | Planning GIS unit | [name, phone] | [name, phone] | Fri 6 Nov |
| 5 | Monthly Power System Summaries, and how the losses by voltage level are worked out | NCC reporting | [name, phone] | [name, phone] | Fri 6 Nov |
| 6 | Hourly SCADA data for Central | NCC SCADA / historian | [name, phone] | [name, phone] | Fri 6 Nov |
| 7 | Monthly meter readings at the Central boundary, generators and bulk supply points | NCC metering and energy accounting | [name, phone] | [name, phone] | Fri 6 Nov |
| 8 | The Kawanda constraint, curtailment, deferred connections and the outage log | NCC operations | [name, phone] | [name, phone] | Fri 6 Nov |
| 9 | Approved bulk supply tariff, bulk sales, deemed energy and plant agreements | Commercial | [name, phone] | [name, phone] | Fri 13 Nov |
| 10 | Planned projects and large loads in Central | Grid Development and Planning (connections and projects); Commercial | [name, phone]; [name, phone] | [name, phone] | Fri 13 Nov |
| 11 | Date, venue and format of the ERA SDP session | ERA SDP secretariat (outside UETCL) | [name, phone] | [name, phone] | Sent Mon 2 Nov; reply by Fri 6 Nov |
| 12 | Data classification, hosting conditions and personal-data rules | ICT and Information Security; Data Protection Officer | [name, phone]; [name, phone] | [name, phone] | Fri 6 Nov |
| 13 | Industrial parks and industrial land in Central | UIA (outside UETCL) | [name, phone] | [name, phone] | Fri 13 Nov |
| 14 | 33 kV feeder totals at Central bulk supply points (not blocking) | UEDCL (outside UETCL) | [name, phone] | [name, phone] | Fri 13 Nov |
| 15 | Open data: boundaries, population, protected areas, terrain and roads | Grid Atlas team | none | [name, phone] | Fri 6 Nov |

- Critical items (2, 4, 5, 6, 7, 8 and 12) are due on Friday 6 November; the rest on Friday 13 November.
- All data covers September 2025 to September 2026 (13 months), unless the request note says otherwise.
- Requests 11, 13 and 14 go outside UETCL with the letter in the annex, not with this memo.

## If data is late: escalation
1. Before a due date, the holder contact and the team contact may agree a new date. The team contact records it.
2. If a due date passes with no data and no agreed new date, the team lead raises it with the head of the holding unit on the next working day: Monday 9 November for critical items, Monday 16 November for the rest.
3. If it is still open two working days later (Wednesday 11 or Wednesday 18 November), the team lead brings it to me, and I take it up with the head of the unit. For UIA, UEDCL and ERA, I follow up through the management introductions.

Escalation contact: Head of Network Operations, [name, phone].

## Handling
The attached handling note applies to every file. In short:
- Deliver only to the Grid Atlas folder on the UETCL share, or to the landing folder on the Grid Atlas server. Never by personal email, WhatsApp, personal cloud storage or USB sticks of unknown origin.
- No personal data and no customer names: anonymised codes only.
- The data stays on the NCC server, in the project's data folder, and never goes into git. At the end of the rotation it is handed over or deleted.
- Nothing based on the data goes outside UETCL until the management preview has cleared it.

ICT and Information Security are asked to confirm the classification (request 12).

## Management preview: Friday 20 November 2026
Please hold one hour on Friday 20 November 2026, [time, room], for a management preview of the Grid Atlas. My office will send the invitation.
- **Who:** myself (chair); the heads of Grid Development and Planning, NCC and Commercial, or their delegates; the Planning and NCC mentors; ICT and Information Security; the Grid Atlas team.
- **What:** the team shows, on the NCC server, the five items planned for the ERA demo: the network map, monthly losses checked against NCC's figures, the N-1 contingency results with Kawanda, the ranked industrial sites, and the dashboard with its downloads.
- **Decision:** which screens and figures may be shown outside UETCL, at the ERA SDP session and in any slides or recording. I will sign that list. Anything not on it is not shown outside UETCL.
- N-1 results go on the list only after the Planning mentor has signed the comparison with Planning's own studies (request 3). Every figure shown carries the label "trainee showcase: not official UETCL figures".

Signed: ............................................

Head of Network Operations, [name]

Date: Monday 2 November 2026

**Attachments:**
1. The handling note.
2. The request note and template workbook for your unit (listed in `docs/data-requests/README.md`).
3. [Copy of the approval, if it can be shared.]

---

## Annex: covering letter for holders outside UETCL
For requests 11 (ERA SDP secretariat), 13 (UIA) and 14 (UEDCL). Print on UETCL letterhead, sign, and send with the request note. Delete the bracketed sentences that do not apply.

> [UETCL letterhead]
>
> [Reference], Monday 2 November 2026
>
> [Name, role], [organisation]
>
> Dear [name],
>
> **Grid Atlas: [title of the request note]**
>
> A team of UETCL graduate trainees is building the Grid Atlas, a showcase map of the transmission network in the Central region. It shows where energy is lost, where the network is constrained, and where new industry could best be supplied. It is due to be presented at the ERA SDP session in late November 2026. The work is advisory, uses read-only copies of data, and is not connected to any control system.
>
> I sponsor this work. The attached note from the team sets out what we are asking for, why, and by when. [For UIA and UEDCL: This follows the introduction of [date, reference].]
>
> [For UIA and UEDCL: Any data you send is kept on UETCL's internal systems and used only for the Grid Atlas. We ask for no personal data. Nothing you send is passed on, or shown outside UETCL, without your agreement. The attached handling note gives the details.]
>
> The team contact is [name, phone]. My office can be reached on [phone].
>
> Thank you for your help.
>
> Yours sincerely,
>
> Head of Network Operations, UETCL
>
> [name]
