# Request 04: GIS layers for substations and circuits

**To:** UETCL Planning, GIS unit  
**Cc:** Planning mentor to the Grid Atlas team  
**From:** Grid Atlas team (graduate trainees), under the covering memo from the Head of Network Operations  
**Date:** Monday 2 November 2026  
**Due:** Friday 6 November 2026  
**Template:** `templates/T02_gis.xlsx`, sheets `README`, `substations`, `circuits`, `crosswalk` and `questions`

## Why we need it
Your layers draw the Grid Atlas network map: demo item 1 and acceptance criterion 1 (the map loads on the NCC server). They are also one of the critical datasets that criterion 2 needs loaded. The map colours each circuit by the loading and losses from Planning's network model, so each circuit must match one model branch. Route lengths also check the model's line lengths, commissioning years give asset age, and substation positions give each candidate industrial site its distance to the grid (demo item 4).

This replaces row 2 of the data list in the scope of work. It adds the infeeds, one feature per circuit, the model IDs, commissioning years and the EPSG code.

## What to send
Your native format is welcome; the template lists the minimum fields. Send your layers as they are. The `substations` and `circuits` sheets list the attribute fields those layers need; they are not forms to fill in.

### 1. Substations: a point layer (fields in sheet `substations`)
One point per substation, switching station, power-station switchyard or tee point in the area in part 3. If you hold only footprint polygons, send those.

| Field | What to put | Required |
|---|---|---|
| `source_id` | Your feature ID | yes |
| `name` | Substation name as you use it | yes |
| `status` | `existing`, `committed` or `planned`. Under construction counts as committed. | yes |
| `kv_levels` | Voltage levels, highest first, separated by `/`, for example `220/132/33` | |
| `model_bus_ids` | Bus numbers in Planning's network model, separated by `;` | |
| `commissioning_year` | Year first energised, four digits; the expected year if not yet built | |
| `ss_code` | Our three-letter code from the table in part 3, if you can tell | |
| `facility_type` | `substation`, `switching_station`, `power_station` (a plant switchyard), `tee_point` or `other` | |
| `district` | District | |
| `capture_method` | How the position was captured: `survey`, `digitised`, `approximate` or `unknown` | |
| `notes` | Anything else | |

### 2. Circuits: a line layer, one feature per circuit (fields in sheet `circuits`)

| Field | What to put | Required |
|---|---|---|
| `circuit_id` | Your feature ID for the circuit | yes |
| `from_substation` | Substation at one end, named as in your substations layer | yes |
| `to_substation` | Substation at the other end | yes |
| `kv` | Operating voltage, in kV | yes |
| `status` | `existing`, `committed` or `planned` | yes |
| `model_branch_id` | The branch ID in Planning's network model (from bus, to bus and circuit) | |
| `circuit_no` | Circuit number on this route: 1, 2 and so on | |
| `double_circuit_with` | The `circuit_id` of the other circuit on the same towers | |
| `conductor` | Conductor type and size | |
| `route_length_km` | Route length in km, as recorded in the line schedule or asset register | |
| `commissioning_year` | Year first energised, four digits; the expected year if not yet built | |
| `name` | Circuit name as you use it | |
| `design_kv` | Voltage the line is built for, if different from `kv` | |
| `reconductored_year` | Year the present conductor was strung, if later than commissioning | |
| `capture_method` | `survey`, `digitised`, `approximate` (including straight lines) or `unknown` | |
| `notes` | Anything else | |

Rules for the circuits layer:
- **Double circuits.** A double-circuit line is two features. Copy the line, set `circuit_no` to 1 and 2, and put the other circuit's `circuit_id` in `double_circuit_with`.
- **Sections.** If a route is stored in sections, merge them into one feature per circuit. If the conductor changes along the route, list each section in `conductor` with its length, for example `Type A 12.1 km; Type B 4.3 km`.
- **Tees.** If a circuit is teed, add the tee point to the substations layer (`facility_type` = `tee_point`) and split the circuit there.
- **Towers.** Route lines are enough. If a route exists only as tower points, send the points with the circuit ID and tower number.
- **Model IDs.** Fill `model_branch_id` and `model_bus_ids` if your layers carry them or Planning can add them quickly. Otherwise leave them blank; we will match by name and position with the Planning mentor.

### 3. Area and date
- **Central:** every transmission substation and circuit (above 33 kV). The table below is our working list: the substations named in the MVP scope of work, with our codes, plus the far ends of the infeeds. Please tell us what it misses.
- **The infeeds,** each drawn whole to its far-end substation: the 400 kV infeed to Kawanda (we understand it comes from Karuma; please confirm), the Bujagali–Kawanda tie, the Masaka–Mbarara tie, and any other circuit above 33 kV that enters Central.
- If clipping is extra work, send your national layers as they are. We report only on Central.
- Leave out lines at 33 kV and below.
- **Date:** the network as at September 2026, including anything commissioned since September 2025. Add committed and planned circuits and substations in Central where you hold a route or site, for example the planned Kawanda relief, marked by `status`. Leave out retired circuits, but tell us which circuits or substations were added, retired or rerouted since September 2025 (question 6).

| Our code | Substation | In scope as |
|---|---|---|
| KAW | Kawanda | Central; the 400 kV infeed lands here |
| MUT | Mutundwe | Central |
| LUG | Lugogo | Central |
| KNO | Kampala North | Central |
| QWY | Queensway | Central |
| NMV | Namanve | Central |
| MUK | Mukono | Central |
| MSK | Masaka | Central; end of the Masaka–Mbarara tie |
| KAP | Kapeeka | Central |
| KBS | Kabulasoke | Central |
| NKG | Nkonge | Central |
| BUJ | Bujagali | Delivery point; end of the Bujagali–Kawanda tie |
| NAL | Nalubaale | Delivery point |
| KAR | Karuma | Far end of the 400 kV infeed to Kawanda (please confirm) |
| MBR | Mbarara | Far end of the Masaka–Mbarara tie |

### 4. Format, in order of preference
1. **GeoPackage** (`.gpkg`) with layers named `substations` and `circuits`.
2. **Shapefile,** zipped, one zip per layer, with every part: `.shp`, `.shx`, `.dbf`, `.prj` and `.cpg`. Without the `.prj` we cannot place the data reliably.
3. **GeoJSON** in WGS 84 (EPSG:4326).

KML or KMZ only if nothing else is possible: it often loses the attribute fields.

- **State the EPSG code of every file** (question 1). Common ones for Uganda: EPSG:4326 (WGS 84 latitude and longitude), EPSG:32636 (WGS 84 / UTM 36N), EPSG:21096 (Arc 1960 / UTM 36N), and EPSG:32736 or EPSG:21036 (UTM 36S) for some data south of the equator. Arc 1960 data read as WGS 84 lands about 300 m off, enough to put a substation on the wrong side of a road.
- **Field names:** yours are fine; tell us which field holds what. Shapefiles cut our names to 10 characters (`commissioning_year` becomes `commission`). That is fine too.
- **Attributes kept elsewhere:** if some sit in a spreadsheet rather than in the layer, send the spreadsheet with the feature ID on every row.
- **Coordinates in a spreadsheet:** if substation positions exist only in a spreadsheet, give latitude and longitude in decimal degrees (WGS 84), in two separate columns.

### 5. Name crosswalk (sheet `crosswalk`), useful but not blocking
Only if such a list exists or is quick to make. One row per substation or circuit, with its ID or name in each system: `entity_type` (`substation` or `circuit`, required), `planning_model_id`, `gis_feature_id`, `ncc_report_name`, `scada_name`, `commercial_name` and `notes`. Leave a cell blank where a system has no name for the item. A table in your GeoPackage is fine too.

### 6. Your answers to the questions below
In sheet `questions`, or in your reply.

**The minimum:** substations as points with `source_id`, `name` and `status`; one line per circuit with `circuit_id`, both end substations, `kv` and `status`; and the EPSG code of each file.

**If it cannot all come by Friday 6 November:** send the substations and the circuits in our list by then, with the answer to question 1, and tell us when the rest will follow.

## Questions to answer
Question 1 decides whether we can place the data at all, so please answer it with the first files.

1. What is the EPSG code of each file? If you are not sure, which datum and projection were the data captured in?
2. Do your layers cover every substation and circuit in our working list, and the three infeeds? Which are missing? Are there Central substations above 33 kV that our list leaves out?
3. Where does the 400 kV infeed to Kawanda start, and how many circuits does it have?
4. At Bujagali and Nalubaale, do your layers show the power-station switchyard, a separate substation, or both?
5. How were the routes and positions captured: survey or GPS, digitised from imagery or maps, or drawn as straight lines? Which circuits are only approximate?
6. When were the layers last updated? Do they show the network as at September 2026? Which circuits or substations were added, retired or rerouted since September 2025, and when?
7. Where does `route_length_km` come from: the line schedule or asset register, or measured from the drawn line?
8. Are any circuits teed, or looped in at a point that is not a substation? Which ones?
9. Do your layers carry Planning model bus numbers or branch IDs? If not, can Planning add them, or should we match them ourselves with the Planning mentor?
10. Do these layers carry a security classification or a use restriction (for example a contractor's licence) that we should record?

## What not to send
- **No personal data.** Delete, do not just hide, any landowner, affected-person, parcel, compensation, valuation, ID-number, phone or other contact fields. Wayleave and resettlement layers often carry them.
- **No staff names.** Remove editor-tracking fields (such as `created_user` and `last_edited_user`) and any surveyor or editor names.
- **No customer names.** Where a feature is named after a customer, for example a customer's own substation, replace the name with a code such as `DC-1` and keep the key yourself.
- **Not needed:** wayleave corridors, land parcels, and lines at 33 kV and below.
- If a file with personal data reaches us by mistake, we delete it, record that we did, and ask you for a clean copy.

## How to deliver
As set out in the handling note (`handling-note.md`, sent with this request):
- Put the files in the Grid Atlas folder on the UETCL share, or in the landing folder on the Grid Atlas server. The handling note gives both locations.
- Never use personal email, WhatsApp, USB sticks of unknown origin, or personal cloud storage (Google Drive, Dropbox, WeTransfer and the like).
- Start each file name with `T02_gis` and say what it holds: for example `T02_gis.gpkg`; or `T02_gis_substations.zip` and `T02_gis_circuits.zip` for Shapefiles; and `T02_gis.xlsx` for the workbook with your answers. If you correct a file, send it again whole under the same name and tell us it replaces the earlier one.
- Then tell the contact below which files you have put there. Do not attach the data to that message.

This is critical-infrastructure information. We keep it on UETCL systems, use it only for the Grid Atlas, and show nothing from these layers outside UETCL unless management clears it first. Tower-level geometry is never shown outside UETCL.

## Contact
[name, phone], Grid Atlas team. If anything here would take you more than an hour, call us first; there may be a simpler way. If something blocks the export, the escalation route is in the covering memo.

Thank you for your help.
