# Request 13: industrial parks and industrial land in Central

- **To:** [name, role], Uganda Investment Authority (UIA), the office responsible for industrial parks and their maps, through the introduction from UETCL management ([reference, date])
- **From:** Grid Atlas team, UETCL graduate trainees
- **Sponsor:** Head of Network Operations, UETCL (covering letter attached)
- **Date:** Monday 2 November 2026
- **Due:** Friday 13 November 2026
- **Template:** `templates/T09_sites.xlsx` (attached), sheets `README`, `sites`, `site_boundaries` and `questions`. Its README sheet repeats these instructions.
- **Reference:** Grid Atlas data request 13

## Why we need it

**Who we are.** The Grid Atlas is a four-week showcase project by a team of UETCL graduate trainees, sponsored by UETCL's Head of Network Operations. It maps the transmission network in the Central region: where energy is lost, where the network is constrained, and where new industry could best be supplied. It is due to be presented to ERA in late November 2026. It is advisory. It makes no decisions: those stay with UIA, ERA and MEMD.

**Why your data.** The Atlas ranks candidate industrial sites by how well the grid can supply them now and in 2030 (demo item 4 and acceptance criterion 5 in our scope of work). UIA's parks and gazetted industrial land should be those candidates, so that the ranking rests on land that is really available. Your investors' expected loads show how much of the nearby grid capacity is already taken.

## What to send

Please send what you already hold. **Your native format is welcome; the template lists the minimum fields.** We do not need history. The position at the latest date you have (ideally September 2026 or later) is enough, with expected loads up to 2030.

**Area.** Every industrial park, free zone and parcel of gazetted industrial land in the Central region, covering at least Kampala, Wakiso, Mukono, Buikwe, Mpigi, Luwero, Nakaseke, Gomba and Masaka districts. If it is simpler to send your national layer, please do; we will clip it to Central.

1. **Boundaries**, one polygon per park or parcel. The `site_boundaries` sheet lists the attributes.
   - Format, in order of preference: GeoPackage; Shapefile with all its parts (.shp, .shx, .dbf and .prj), zipped together; GeoJSON; KML or KMZ.
   - State the coordinate reference system as an EPSG code, for example EPSG:21096 (Arc 1960 / UTM zone 36N) or EPSG:4326 (WGS 84 latitude and longitude).
   - Attributes: `site_id` (the same as in the `sites` sheet), `name`, `status`, and `boundary_source` (survey, deed plan, master plan, or digitised from a map).
   - If you hold only CAD drawings (DWG or DXF) or surveyed beacon coordinates, send those with their coordinate system. If you hold only PDF or paper maps, send those: we will digitise them and send you our version to check before we use it.
   - The outer boundary of each park is enough. If parts of a park differ in status (for example a serviced phase 1 and a planned phase 2), give each part its own `site_id`.
2. **One row per site** in the `sites` sheet, or your own park register with the same information:
   - `site_id`, `name` and `district`;
   - `kind`: `uia_park`, `free_zone`, `gazetted_land` (outside a UIA park), `private_estate` or `other`;
   - `status`, the most advanced stage reached: `gazetted`, `serviced` or `planned` (`proposed` for ideas still under study);
   - `owner`: the organisation that owns or develops the land (leave it blank for a private individual);
   - `area_ha` (gross area) and `available_ha` (area not yet allocated and open to new investors), in hectares. If your records are in acres, convert them (1 acre = 0.4047 ha) or tell us and we will;
   - `land_confirmed`: `Y` if the available land is confirmed free for new investors, `N` if not;
   - `lat` and `lon` of the site's centre, in WGS 84 decimal degrees, only for a site with no boundary;
   - `target_sectors`: the industries the site is planned for, if any.
3. **Expected loads of allocated investors**, in the same sheet, as one total per site and never per investor:
   - `allocated_load_mw`: the expected total demand, in MW, of all investors already allocated land, once they are fully operating;
   - `operating_load_mw`: the part of that total already operating today;
   - `allocated_load_year`: the year by which the total is expected.
   - If your records are in kVA or MVA, write them in `notes` and say which.
4. **Planned power supply points**, in the same sheet:
   - `planned_supply_point`: the substation, planned substation or feeder that supplies or will supply the site;
   - `planned_supply_kv`: its voltage in kV, for example 33 or 132.
5. **Answers to the questions below**, in the `questions` sheet or in your reply.

**The minimum**, if time is short: for each site, its name, status, available hectares and a location (a boundary, or a latitude and longitude). Loads and supply points can follow.

Please leave the `metric_overrides` sheet blank; it is for our own use.

## Questions to answer

1. What coordinate reference system do the boundary files use? Please give the EPSG code, or the datum and UTM zone.
2. How were the boundaries made (survey, deed plans, master plan, or digitised from a map), and roughly how accurate are they?
3. What date are the hectares, allocations and loads correct to?
4. What does each status mean in your records? In particular, what does "serviced" include: roads, water, power to each plot?
5. Where do the investor load figures come from: investor applications, connection applications to UEDCL or UETCL, or UIA estimates? Is each figure the investors' maximum demands added up, or an estimate of the site's combined peak?
6. For each planned supply point: who will build it (UETCL, UEDCL or the developer), what capacity is planned (MVA), and when is it due? Has a connection been applied for?
7. Does `available_ha` exclude roads, wetland and other land that cannot be built on? If a boundary includes such land, can you mark it?
8. Are there other industrial parks, free zones or private industrial estates in Central that we should include? Who holds their data?
9. Which of these figures may we show outside UETCL, for example at the ERA session, and which must stay internal?

## What not to send

- No personal data: no names, phone numbers, ID numbers or addresses of any person, landowners included.
- No names of investors, allottees, customers or occupants, whether people or companies. Investor loads come as one total per site. The only organisation we ask you to name is the one that owns or develops each park (`owner`).
- No land titles, leases, investor agreements, or valuation or compensation records.
- If your GIS layers or registers carry such fields (for example a plot's allottee), delete those fields before sending, or send only the outer boundary of each park.
- If any figure is confidential to UIA, mark it and tell us how it may be used (question 9).

## How to deliver

Please use one of these routes. They follow UETCL's data-handling note, which is attached.

1. **Collection.** A team member collects the files from your office on a UETCL-issued drive and copies them straight to the UETCL file share. Please call [name, phone] to agree a time.
2. **Upload.** If you prefer to send the files, we will email you an upload link to the UETCL file share from an official UETCL email address. When the files are uploaded, tell [name, phone] which files are there.

Please do not attach the files to an email, and do not send them by personal email, WhatsApp, a USB stick of unknown origin or a personal cloud account (such as Google Drive, Dropbox or WeTransfer). If neither route suits you, tell us and we will agree another one with UETCL ICT.

Please name each file with UIA, its content and the date, for example `UIA_park_boundaries_2026-11-13.gpkg`. To correct a file, send it again under the same name and tell us that it replaces the earlier one.

**How we handle your data.** Your files are kept only on UETCL's internal systems, alongside UETCL grid data that is handled as critical-infrastructure information. They are used only for the Grid Atlas, and they are not passed on or shown outside UETCL without UIA's agreement. Any result shown outside UETCL is labelled "trainee showcase: not official UETCL figures". At the end of the project, the files are handed over or deleted as the handling note sets out.

## Contact

[name, phone], Grid Atlas team, UETCL.

If Friday 13 November is difficult, please tell us what you can send by then and when the rest can follow; partial data is welcome. We are glad to visit your office to go through this request or to copy the files.

Thank you for your help.
