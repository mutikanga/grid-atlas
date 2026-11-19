# Request 12: data classification, hosting beside Grid Monitor, and personal data

- **To:** UETCL ICT and Information Security (parts A to D); the Data Protection Officer (part E)
- **Cc:** NCC mentor to the Grid Atlas team
- **From:** Grid Atlas team (UETCL graduate trainees), under the covering memo from the Head of Network Operations
- **Date:** Monday 2 November 2026
- **Due:** Friday 6 November 2026. Please answer part B (hosting) by Thursday 5 November if you can: we plan a dry run on the server on Friday 6 November, and we will install nothing until you agree.
- **Template:** none. Please answer in your reply. Where a policy clause already answers a question, quoting or citing the clause is enough.

## Why we need it
The Grid Atlas will hold copies of the HV network model, NCC reports and SCADA exports on the NCC App VM, beside Grid Monitor, and will compute N-1 results from them. We need your rules before the first real file arrives and before anything is installed. They decide two acceptance checks in our scope of work: the stack runs on the NCC server (criterion 1), and no container has a route to SCADA, EMS or any production database (criterion 8). They also fix the handling note sent with every request, and how the ERA SDP demonstration can be given.

## What to send
1. Your answers to the questions below.
2. The parts of the UETCL ICT policy that apply: the classification levels, and the rules for servers, removable media and code repositories.
3. Any corrections to the attached handling note.

## Questions to answer

### A. Classification
1. What is the classification, under the UETCL ICT policy, of:
   - the HV network model with its ratings;
   - the N-1 results, loadings and spare-capacity figures computed from it;
   - NCC monthly reports, SCADA exports, curtailment records and the outage log;
   - GIS routes of substations and circuits?
2. What does each level require: who may see the data, where it may be kept, for how long, and whether any of it may be shown outside UETCL?

### B. Hosting on the NCC App VM, beside Grid Monitor
The VM has two network cards: one on the control-room network, and one on the substation network that Grid Monitor uses to reach the substation gateways. Our design:
- **Four containers:** a database (PostgreSQL with PostGIS), a worker that runs the load flows, an API, and a web server (Nginx).
- **No route out.** The database, API and worker sit on an internal Docker network with no route out. They cannot reach the control-room network, the substation network or the internet.
- **One published port.** Only the web server publishes a port: 8090, on the control-room address only, the same address Grid Monitor uses. This avoids Grid Monitor's ports 8000 and 8100 and its loopback ports 5432 and 6379. The database is never published.
- **Firewall rules.** Rules in Docker's DOCKER-USER chain stop the web container from starting any connection, and admit only the client addresses you approve. They match only Atlas traffic, so Grid Monitor is untouched. We apply them only with your agreement.
- **No internet on the VM.** Images are built on a team laptop from open-source packages pinned by version and checksum, and brought in on a USB drive, as Grid Monitor's are. Every web library is bundled; nothing loads from the internet.
- **Read-only.** Nothing writes to any UETCL system. The API reads the database through a read-only account.
- **Grid Monitor first.** The Atlas is capped at about 3 GB of memory in total. If the two compete for memory or CPU, Grid Monitor wins.
- **A check you can watch.** `./atlas verify` lists the published ports, and tries to connect from each container to a substation gateway on port 2404. Every attempt must fail. We would like you to watch it run on the server.

3. Do you approve hosting the Atlas on this VM on these terms? What conditions do you set?
4. Which network zone is the control-room card in? Which client subnets may reach port 8090? Do you also want a password on the site (basic authentication)? Is there any route from that zone to EMS or a production database that we should test? You need not give us addresses: a check you witness is enough.
5. Is port 8090 acceptable, or should we use another?
6. The containers use two small private subnets, by default 172.30.90.0/28 and 172.30.90.16/28. Do these clash with any UETCL range? If so, which should we use?
7. May we apply the firewall rules above? Would you rather apply them yourselves, or witness them?
8. May we bring software in on a UETCL-issued USB drive, scanned before use? How should data files move from the UETCL share to the landing folder on the VM? We assume the VM stays without internet access, including for builds; please confirm.
9. May the Atlas database and data folder be added to Grid Monitor's existing backups? If not, may we keep our own database copies on the VM?
10. Who may have a login on the VM for the Atlas, and do you need logs or monitoring from it?

### C. Code repository
11. Is there an internal Git host we may use? If not, may we keep the repository on the VM? No data and no passwords go into the repository: the data folder is excluded, and a check blocks data files. May the repository also hold our review notes, which quote the internal board paper, or should they stay out?

### D. Showing results outside UETCL
12. If the ERA SDP session is held outside UETCL, may a UETCL laptop carry a results-only copy to the venue? It would hold only the precomputed results, with no network model and no SCADA data, run fully offline, and be wiped afterwards. What conditions apply, for example encryption and who carries it?
13. Or may the team present remotely, from a UETCL desk, over a video call? Only the screen would be shared. Nobody outside UETCL would reach the server, and we are not asking for VPN access. If UETCL policy allows VPN access for a demonstration, please say on what terms; we do not plan to use it.
14. May the demonstration be recorded? If so, how should the recording be classified and stored?

### E. Personal data (Data Protection Officer)
15. **Corridor GIS.** We ask Planning for routes and asset attributes only: no landowner, affected-person, compensation or contact fields. If a file arrives with such fields, we delete it and ask for a clean copy. Is that enough?
16. **Event and operations logs.** We ask for no staff or operator names. Customers appear only as codes (for example `DC-1`), and NCC keeps the key. Do coded customer references need any further safeguard?
17. We plan to hold no personal data at all. Does this use still need an entry in UETCL's data-protection records, such as its registration with the Personal Data Protection Office?
18. At the end of the rotation we hand the data over or delete it. What record of the deletion do you need?

## What not to send
- No passwords or keys by email or chat. If you create an account for us, hand over the password in person.
- No SCADA or EMS addresses unless you choose to: the no-route check can run with you watching instead.
- No personal data.

## How to deliver
- Reply by official UETCL email to the contact below. Policy documents can come the same way.
- Anything you classify as restricted goes to the Grid Atlas folder on the UETCL share, as the handling note (`handling-note.md`, attached) sets out.
- Never personal email, WhatsApp, USB sticks of unknown origin or personal cloud storage.

## Contact
[name, phone], Grid Atlas team. If something blocks an answer, the escalation route is in the covering memo.
