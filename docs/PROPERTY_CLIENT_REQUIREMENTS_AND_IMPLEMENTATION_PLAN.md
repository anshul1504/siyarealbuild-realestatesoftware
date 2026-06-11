# Property Module Client Requirements and Implementation Plan

Date: 2026-06-11

## Client Requirement Summary

The client wants a next-level property module where every property starts with a category selection, and the rest of the form opens only according to that selected category. Colony is the highest-priority workflow. A colony is not just one listing; it contains developer/project details, location, map, amenities, plot inventory, plot categories, rates, charges, PLC rules, client sharing, quotation, booking, registration, and customer tracking.

## Core Product Direction

The property module should become a category-driven real estate inventory system.

Flow:

1. Select property category.
2. Open only relevant form sections for that category.
3. Save property/project master.
4. Manage units/plots under that property.
5. Share property/plot details by WhatsApp or email.
6. Add clients/enquiries for the property or plot.
7. Generate quotation.
8. Book plot/unit.
9. Track payment/registration/commission later.

## Category-First Form Requirement

Every new property must start from:

- Colony
- Plot
- Resale Plot
- Flat
- Residential House
- Commercial Shop
- Row House
- Villa
- Farm House
- Office
- Warehouse
- Agricultural Land

After category selection:

- Colony opens colony-specific project and plot inventory forms.
- Flat/House/Villa opens built-unit forms.
- Commercial Shop/Office/Warehouse opens commercial unit forms.
- Plot/Resale Plot/Agricultural Land opens land/plot forms.

No irrelevant fields should be shown for a selected category.

## Colony Workflow

### Colony Master Details

Required sections:

- Developer / Builder details
- Project / colony name
- RERA number
- T&CP approval number
- Registry/diversion/mutation status
- Khasra/survey number
- Legal status
- Legal notes
- Colony address
- City
- Locality
- Landmark
- Google Maps link
- Nearby residential area
- Nearby commercial area
- Connectivity
- Schools/colleges
- Hospitals
- Landmarks

### Developer Details

Add developer master or inline fields:

- Developer name
- Company name
- Contact person
- Mobile
- Email
- Office address
- GST/PAN optional
- RERA developer number optional
- Notes

Recommended: create a reusable `Developer` model so multiple colonies can use the same developer.

## Colony Amenities

Amenities should not be only a textarea. Client wants checklist plus custom add.

Default checklist examples:

- Boundary wall
- Main gate
- Security
- Garden
- Temple
- Club house
- Kids play area
- Water connection
- Electricity
- Street lights
- Drainage
- Cement road
- Blacktop road
- CCTV
- Sewerage
- Borewell
- Narmada/water line
- Commercial shops
- Parking
- Open gym

Custom amenity:

- User can add custom amenity text.
- Saved custom amenities should show in project detail/share/quotation.

Recommended data:

- `AmenityMaster`
- `PropertyAmenity`
- or JSON field for faster first version.

## Plot Inventory Inside Colony

A colony contains many plots. Each plot needs complete CRUD.

Plot fields:

- Plot number
- Plot category
- Plot type
- Block/sector
- Area sqft
- Length
- Width
- Facing
- Road width
- Corner plot yes/no
- Garden-facing yes/no
- Main-road plot yes/no
- Status: Available, Hold, Reserved, Booked, Sold, Cancelled
- Base rate
- PLC rate
- Final rate
- Total plot value
- Notes

Plot categories requested:

- Residential
- Commercial
- LIG
- MIG
- HIG
- EWS
- Premium
- Corner
- Garden-facing
- Main-road
- Custom category

Important: plot category and plot features can change rate.

## Colony Rate and Charge Setup

Colony should have project-level rate settings.

Base charges:

- Base rate per sqft
- Residential plot rate
- Commercial plot rate
- LIG rate
- MIG rate
- HIG rate
- EWS rate
- Premium rate
- Custom category rate

Extra charges:

- Electricity charge
- Maintenance charge
- Development charge
- Registry charge estimate
- Legal/documentation charge
- Club/garden/amenity charge
- Other charge

PLC:

- Corner PLC
- Garden-facing PLC
- Main-road PLC
- Wide-road PLC
- East-facing PLC
- Custom PLC

Calculation:

- Plot amount = area sqft * applicable base/category rate
- PLC amount = area sqft * applicable PLC rate or fixed amount
- Extra charges = configured fixed/percentage charges
- Total quotation = plot amount + PLC + charges - discount

## Plot CRUD Requirement

Need dedicated plot pages:

- Plot list under colony
- Add plot
- Edit plot
- Plot detail
- Plot status update
- Plot booking
- Plot quotation
- Plot registration details
- Plot share by WhatsApp/email

Current module has plot rows inside colony form and plot detail. It needs full CRUD pages for plot-level management.

## Client/Customer Requirement

Client should be connectable to property or plot.

Client fields:

- Client name
- Mobile
- Email
- Address
- Requirement
- Budget
- Source
- Assigned employee
- Notes

Recommended approach:

- Reuse CRM Lead where possible.
- Add `PropertyClient` only if booking/registration needs customer master separate from lead.

Best flow:

- Client enquiry creates CRM Lead.
- Lead can be linked to property and plot.
- Booking can be created from lead.

## Booking Workflow

Plot booking is required.

Booking fields:

- Colony
- Plot
- Client
- Lead optional
- Booking date
- Booking amount
- Agreed rate
- Discount
- PLC amount
- Charges amount
- Total deal value
- Payment mode
- Booking status: Draft, Booked, Cancelled, Converted to Sale
- Booking note
- Created by
- Approved by

Status effect:

- When booking is confirmed, plot status should become Booked/Reserved.
- If booking is cancelled, plot can return to Available/Hold based on business rule.
- Booking should write audit history.

## Quotation Workflow

Quotation should be generated before booking.

Quotation fields:

- Quotation number
- Client
- Colony
- Plot
- Rate breakdown
- PLC breakdown
- Extra charge breakdown
- Discount
- Valid until
- Terms and conditions
- Created by
- Status: Draft, Sent, Accepted, Rejected, Expired

Output:

- Printable quotation page
- WhatsApp share text
- Email share
- Later PDF export

## Registration Workflow

Each plot registration needs tracking.

Registration fields:

- Booking
- Plot
- Client
- Registry date
- Registry office
- Registry amount
- Stamp duty
- Registration number
- Document upload
- Mutation/diversion notes
- Status: Pending, Documents Collected, Registry Scheduled, Registered, Cancelled
- Notes

This can be phase 3 after booking/quotation.

## Sharing Requirement

Property and plot should be shareable:

- WhatsApp share
- Email share
- Client-safe details only
- Quotation share
- Plot availability share

Share content should include:

- Colony/project name
- Developer name
- Location/map link
- Amenities
- Plot number
- Plot area
- Plot category
- Facing/road/corner/garden-facing
- Rate
- Charges summary
- Total estimate
- Contact details

Need avoid internal notes/legal sensitive fields in public share.

## Suggested Data Model Additions

P0 models:

- `PropertyDeveloper`
- `PropertyAmenity`
- `PlotCategory`
- `ColonyRateCard`
- `PlotRateOverride`
- `PlotBooking`
- `PlotQuotation`
- `PlotStatusHistory`

P1 models:

- `PropertyClient` if CRM Lead is not enough
- `PlotRegistration`
- `PlotPaymentSchedule`
- `PlotPayment`

## Implementation Phases

### Phase 1 - Category and Colony Foundation

- Refine category-first wizard. Implemented.
- Add Developer model and colony developer fields. Implemented.
- Convert amenities textarea into checklist + custom amenities. Implemented.
- Add colony rate card fields. Implemented.
- Add plot category and rate fields. Implemented.
- Add plot full CRUD pages. Implemented for create/edit/detail.
- Add plot status history. Implemented.
- Add tests. Implemented baseline tests.

### Phase 2 - Client, Share, Quotation

- Connect property/plot to CRM leads.
- Add client create/select flow from property/plot.
- Add quotation model and quotation page. Implemented baseline quotation create/list on plot detail.
- Add WhatsApp/email share for plot and quotation. Plot WhatsApp share implemented; quotation email/PDF still pending.
- Add filtered property/plot export.
- Add tests.

### Phase 3 - Booking and Registration

- Add plot booking model. Implemented baseline booking create/list on plot detail.
- Add booking create/approve/cancel flow. Booking create implemented; approve/cancel review flow pending.
- Auto-update plot status from booking. Implemented for Booked status.
- Add registration tracking.
- Add document upload for registration.
- Add audit trail and permission tests.

### Phase 4 - Reports and Automation

- Colony inventory report.
- Plot availability report.
- Booking report.
- Revenue projection.
- Employee/channel partner performance.
- Commission hooks.

## Immediate Next Development Step

Start with Phase 1. The first code batch should implement:

1. Developer model.
2. Amenity checklist/custom amenities.
3. Plot category/rate fields.
4. Colony rate card.
5. Dedicated plot CRUD.
6. Assigned property visibility fix from audit.
7. Tests for category-wise colony flow.

This creates the correct foundation before booking, quotation, and commission.
