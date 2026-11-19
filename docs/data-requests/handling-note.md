# Grid Atlas: data handling note

Sent with every Grid Atlas data request, under the sponsor's covering memo of Monday 2 November 2026. It covers data files. Questions and replies may go by official UETCL email; data files may not.

## 1. Classification
- The HV network model, GIS routes, SCADA exports, NCC reports and the N-1 results computed from them are handled as [classification under the UETCL ICT policy], to be confirmed by ICT and Information Security (request 12).
- Until then, we treat all of it as critical-infrastructure information: together, it shows where the grid is weakest.
- If an item must never leave UETCL, mark it. We follow your marking.

## 2. How to deliver
- **UETCL share:** [path to the Grid Atlas folder]. Only the Grid Atlas team can open it.
- **Landing folder on the Grid Atlas server** (the NCC App VM): [path, and how to reach it]. It opens once ICT approves the hosting (request 12). Until then, use the share.
- **Holders outside UETCL:** use the upload link we send from an official UETCL address, or a team member collects the files on a UETCL-issued drive and copies them straight to the share.

Never use personal email, WhatsApp or other chat apps, personal cloud storage (Google Drive, Dropbox, WeTransfer and the like) or USB sticks of unknown origin. Do not attach data to an email: put the files in place, then tell the team contact which files are there. Name files as your request note says. To correct a file, send it again under the same name and say that it replaces the earlier one.

## 3. What not to send
- **No personal data:** no names, ID numbers, phone numbers or addresses of any person; no landowner, affected-person or compensation fields; no staff or operator names in logs.
- **No customer names:** use an anonymised code (for example `DC-1`), the same code for the same customer in every file. Keep the key yourself.
- **No access details:** no passwords, IP addresses or communication settings.

If a file arrives with any of these, we delete it and ask you for a clean copy. Our loaders read only the template's columns and drop the rest.

## 4. Where the data is kept
- Only on the NCC server, in the Grid Atlas project's data folder. Git ignores that folder, so data never goes into the code repository.
- The share is only a drop point. Once the hosting is approved, we move each file to the server within one working day, by the route ICT approves, and then delete it from the share.
- Never on personal laptops or phones, in email or in personal cloud storage. Any other copy, such as a results-only copy on a UETCL laptop for the demo, needs ICT's written approval first (request 12).
- Each file is logged on arrival (holder, date received, checksum, permitted use) and kept unchanged.
- The Atlas pages and downloads are open only to UETCL addresses that ICT approves, with a password if ICT asks.

## 5. What may be shown outside UETCL
- Nothing based on this data goes outside UETCL until the management preview on Friday 20 November 2026 has cleared it, screen by screen.
- External showings never include tower-level geometry or the full contingency list.
- N-1 results are shown only after the Planning mentor has signed the comparison with Planning's own studies.
- Every figure shown is labelled "trainee showcase: not official UETCL figures". Slides and any recording of the demo are handled like the data.

## 6. At the end of the rotation
The team hands the data and results over to an owner the sponsor names, or deletes them from the server and the share. The sponsor confirms in writing which was done. A holder may ask for its own files to be deleted sooner.

**Contact:** [name, phone], Grid Atlas team. Escalation: see the covering memo.
