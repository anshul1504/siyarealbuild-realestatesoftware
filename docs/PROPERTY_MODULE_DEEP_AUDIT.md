# Property Module Deep Audit Sheet

Audit date: 2026-06-11

## Executive Verdict

The Properties module is a strong operational base, but it is not yet 100% production-complete. Inventory CRUD, category-aware forms, colony plots, media/documents, status history, bulk status/delete, client sharing, and basic visits exist. The biggest remaining risks are role-wise visibility, hard-delete behavior, assigned-record scoping, visit lifecycle depth, export/reporting, and test coverage.

Current practical completion after the Phase 1 implementation batch: 88-90%.

## Completion Estimate

- App wiring and routes: 98%
- Property model coverage: 92%
- Category-wise create/edit wizard: 90%
- Property detail workspace: 90%
- Colony plot inventory: 92%
- Photos/documents: 65%
- Role-wise visibility and permissions: 70%
- Assignment workflow: 60%
- Bulk actions: 70%
- Client sharing: 70%
- Visit workflow: 65%
- Reports/dashboard: 65%
- Audit logging: 70%
- Tests: 45%
- Production readiness: 65%

## Existing Features

- Dedicated `properties` app with split view modules: dashboard, inventory, visits, helpers.
- Routed dashboard, list, create, edit, detail, bulk action, share email, plot detail, visit list, visit create/edit/detail/delete.
- Property categories: Colony, Plot, Resale Plot, Flat, Residential House, Commercial Shop, Row House, Villa, Farm House, Office, Warehouse, Agricultural Land.
- Listing types: Sale, Rent, Lease.
- Statuses: Available, Hold, Negotiation, Sold, Rented.
- Core property fields for title, category, listing type, city, locality, address, price, area, dimensions, facing, road width, legal data, contact, internal notes.
- Built-property fields for bedrooms, bathrooms, balconies, floor, parking, furnishing, construction, possession.
- Colony fields for total plots, available plots, amenities, PLC rules, nearby infra, and plot inventory.
- Individual `ColonyPlot` records with plot number, area, dimensions, facing, road width, price, status, notes.
- Photo and document upload models.
- Property form supports multiple photos and documents.
- Category-aware create/edit wizard with dynamic sections.
- Property detail page shows core data, status history, pricing, colony plot inventory, nearby infrastructure, client share, visits, legal details, photos/documents, contact/notes.
- Property list supports search, category filter, status filter, listing-type filter.
- Bulk status changes for Available, Hold, Negotiation, Sold, Rented.
- Bulk delete exists and records audit before deletion.
- Status changes create `PropertyStatusHistory`.
- Create/update/status/delete actions write audit logs through service layer.
- Property share through WhatsApp text and email.
- Property visits with client, plot, assigned employee, schedule, status, outcome, follow-up fields, conversion timestamp.
- Dashboard has property value, active count, lead count, average price, plots, conversion, category/status/listing charts, and visit metrics.
- Basic tests exist and pass.
- Developer master exists for colony/project builder details.
- Colony rate fields exist for base, residential, commercial, LIG, MIG, HIG, EWS rates.
- Colony charge fields exist for electricity, maintenance, development, registry, and other charges.
- PLC rate fields exist for corner, garden-facing, main-road, and wide-road pricing.
- Amenity checklist and custom amenity fields exist.
- Plot category, block, base rate, PLC rate, extra charges, calculated price, corner/garden/main-road flags exist.
- Dedicated plot create/edit pages exist.
- Plot status history exists.
- Plot quotation and plot booking workflows exist.
- Booking can update plot status to Booked and recalculates available plots.

## Current Role-Wise Behavior

Company Owner:
- Can see company-wide properties.
- Can create, edit, bulk update, bulk delete, schedule/edit/delete visits.
- Can share properties by email/WhatsApp.

Manager:
- Can see company-wide properties.
- Can create, edit, bulk update, bulk delete, schedule/edit/delete visits.
- Can share properties by email/WhatsApp.

Team Lead:
- Can see company-wide properties.
- Can create, edit, bulk update, bulk delete, schedule/edit/delete visits.
- Can share properties by email/WhatsApp.

Executive:
- Can see only properties where `owner=request.user`.
- Cannot create/edit through UI policy.
- Can share visible properties by email/WhatsApp.
- Assigned properties are not visible unless the Executive is also the owner.

Channel Partner:
- Can see only properties where `owner=request.user`.
- Cannot create/edit through UI policy.
- Can share visible properties by email/WhatsApp.
- Assigned properties are not visible unless the Channel Partner is also the owner.

No-company user:
- Falls back to own-created property visibility.

## Confirmed Gaps

### P0 - Must Fix Before Calling Properties 100%

- Assigned property visibility is partially complete.
  - Executive and Channel Partner can now see properties assigned to them.
  - TL subordinate scoping still needs a more precise business rule.
  - TL sees all company properties instead of a subordinate/assigned scope.

- Permission model is too coarse.
  - `can_manage_properties()` allows Owner, Manager, and TL to create/edit/delete all visible company properties.
  - Create permission allows TL in the view but sidebar context says add-property is Owner/Manager only.
  - There is no separate view/create/update/delete/export/share permission split for properties.

- Bulk delete is hard delete.
  - Deleted properties are removed from the database.
  - Audit is recorded first, but property, plots, visits, photos, documents are gone.
  - Safer production flow should be archive/restore with owner-only permanent delete if required.

- Direct URL permission test matrix is missing.
  - Need tests for list/detail/create/edit/bulk/delete/share/visit create/edit/delete/plot detail across Owner, Manager, TL, Executive, Channel Partner, no-company user, and another company user.

- Visit permissions are too broad for management roles and too narrow for assigned employees.
  - Owner/Manager/TL can manage all visits on company properties.
  - Executive can only access visits through own-created properties, not visits assigned to them on company properties.
  - Assigned visit visibility should be based on `assigned_employee` and `scheduled_by`.

- Client share can be used by any user who can view the property.
  - This may be intended, but client sharing exposes property details by email/WhatsApp.
  - Needs explicit role policy and tests.

### P1 - Important Workflow Gaps

- No property export.
  - CRM has export; Properties does not.
  - Need CSV/XLS export with role checks and filters.

- No single-property delete/archive route.
  - Only bulk delete exists.
  - Users cannot archive/restore one property from detail.

- Assignment UI workflow is still basic.
  - Assigned To field is inside create/edit form.
  - There is no dedicated assign/reassign action, assignment note, or assignment history page.

- No automatic assignment rules.
  - CRM has assignment rules; Properties only manual `assigned_to`.
  - If property intake needs owner/manager routing, add property assignment rules later.

- Property lifecycle validation is still basic.
  - Status can move freely to sold/rented without mandatory note, buyer/client, visit, booking reference, commission trigger, or approval.
  - Sold/Rented should normally require a conversion note or linked visit/deal before commission.

- Colony plot status is now audited through dedicated plot create/edit flow.
  - Inline formset status changes still need parity with dedicated plot edit service.

- Photo/document management is incomplete.
  - Upload exists, but no delete/replace/primary photo management UI.
  - Documents do not have access/download audit.
  - File type/size validation is basic through input accept only; backend validation is not strict.

- Search/filtering is basic.
  - Missing filters for assigned_to, price range, area range, legal status, owner, city dropdown, created date, visit status, and plots available.

- Dashboard metrics are useful but not drilldown-grade.
  - No source/assignment performance, aging, stale inventory, sold/rented value, visit conversion by employee, or category availability breakdown.

- No pagination on visit list.
  - Property visit list can grow without pagination.

- No notification records for property assignment/status/visit creation.
  - CRM records notifications; Properties does not consistently create NotificationDelivery rows.

### P2 - Optional Enhancements

- Drag/drop status workflow for property lifecycle.
- Saved filters and user preferences.
- Public/client-safe property share page without exposing internal app login.
- Map preview/embed for properties.
- Duplicate detection by title/address/RERA/T&CP.
- Price history.
- Property scoring and stale listing reminders.
- Bulk import from Excel/CSV.
- Advanced media gallery.
- Commission hooks after Sold/Rented/Booked visit status.

## UI Audit

Strong:
- Property form is category-aware and operational.
- Detail page is comprehensive.
- Colony plot inventory is visible and plot-specific visit creation exists.
- List filters are simple and usable.

Needs improvement:
- Add Property button appears on property list without role guard in the template; backend blocks unauthorized users, but UI should hide it for users who cannot create.
- Bulk action includes destructive Delete in same dropdown as status updates.
- No archive/restore UI.
- No export button.
- Assigned To appears in detail/list, but assigned users do not get visibility.
- Form wizard has inline CSS/JS; acceptable short term, but should move to static asset if it keeps growing.
- Visit list lacks filters, pagination, and quick status update.

## Backend Audit

Strong:
- Service layer exists for create/update/bulk status/bulk delete/update visit.
- Status history exists for property status.
- Audit logs exist for core property lifecycle actions.
- Querysets are mostly scoped by `visible_properties()`.

Risks:
- `visible_properties()` does not reflect assignment.
- `can_manage_properties()` is only one boolean; it cannot express create/update/delete/share/export separately.
- `bulk_delete_properties()` hard deletes.
- `PropertyVisit` create path does not use a service function, so visit creation is not audited.
- Visit delete is hard delete and does not audit.
- Property share email does not write explicit audit/notification records from the property module.
- No database indexes for company-scoped property list queries through `owner__profile__company`, status/category/listing filters, or assigned_to.

## Test Audit

Current properties test count observed: 8 tests passing.

Covered:
- Dashboard owner sees pending signup/support.
- Dashboard non-owner does not see owner auth sections.
- Property status/assignment audit.
- Property create audit.
- Bulk status history/audit.
- Bulk delete audit.
- Bulk action requires login.
- Booked visit conversion timestamp.

Missing:
- Role-wise list/detail/create/edit/bulk/share/visit access matrix.
- Assigned-to visibility.
- Cross-company data isolation.
- Channel Partner visibility.
- TL scoping.
- Property wizard category validation through view posts.
- Colony plot formset create/edit/delete behavior.
- File upload validation.
- Property share email success/failure/audit behavior.
- Visit create/delete audit.
- Direct URL unauthorized edit/delete/share tests.
- Export tests after export is added.

## Recommended Execution Plan

1. Fix role and scope foundation.
   - Replace one `can_manage_properties()` boolean with explicit `can_view_property`, `can_create_property`, `can_update_property`, `can_delete_property`, `can_share_property`, `can_export_property`, `can_manage_visit`.
   - Make `visible_properties()` include `assigned_to=request.user` for Executive/Channel Partner.
   - Add TL subordinate scoping or explicitly keep TL company-wide by business decision.
   - Add direct URL tests for every role.

2. Replace hard delete with archive/restore.
   - Add `is_archived`, `archive_reason`, `archived_at`, `archived_by`.
   - Hide archived records from default list.
   - Add archived filter for owner/manager.
   - Keep permanent delete disabled or owner-only.

3. Strengthen assignment workflow.
   - Add dedicated assign/reassign action.
   - Record assignment history/audit notes.
   - Notify assigned employee.
   - Add assigned_to filter.

4. Complete visit workflow.
   - Audit visit create/update/delete.
   - Allow assigned employees to see their visits.
   - Add visit filters, pagination, and quick status update.
   - Add follow-up due list and conversion hooks.

5. Add export and reporting.
   - Export current filtered property list.
   - Add role checks and tests.
   - Add stale inventory and status aging reports.

6. Complete media/document controls.
   - Delete/replace photo/document.
   - Primary photo selection.
   - Backend file size/type validation.
   - Optional document access audit.

7. Run verification after each batch.
   - `python manage.py check`
   - `python manage.py makemigrations --check --dry-run`
   - `python manage.py test properties -v 1`
   - `python manage.py test --verbosity 1`

## Final Readiness

The Properties module is ready for controlled internal use. It should not be called 100% complete until assigned-record visibility, role-specific permissions, archive/restore, visit audit/scoping, export, and permission-matrix tests are implemented.
