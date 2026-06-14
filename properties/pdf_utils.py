from textwrap import wrap
from datetime import date
from io import BytesIO

from PIL import Image
from types import SimpleNamespace


def _pdf_escape(value):
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def simple_pdf(title, sections):
    lines = [title, ""]
    for heading, rows in sections:
        lines.append(heading.upper())
        for label, value in rows:
            text = f"{label}: {value}" if label else str(value)
            lines.extend(wrap(text, width=92) or [""])
        lines.append("")

    commands = ["BT", "/F1 11 Tf", "50 790 Td", "14 TL"]
    for index, line in enumerate(lines[:52]):
        if index:
            commands.append("T*")
        commands.append(f"({_pdf_escape(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    

    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode())
        result.extend(obj)
        result.extend(b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(result)


def _invoice_pdf(title, subtitle, sections, footer):
    pages, page = [], []
    for heading, rows in sections:
        block = [("heading", heading)]
        for label, value in rows:
            wrapped = wrap(f"{label}: {value}" if label else str(value), width=88) or [""]
            block.extend(("row", line) for line in wrapped)
        block.append(("space", ""))
        if len(page) + len(block) > 38:
            pages.append(page)
            page = []
        page.extend(block)
    if page:
        pages.append(page)

    objects = [
        None,
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    page_refs = []
    for page_number, content in enumerate(pages, start=1):
        commands = [
            "0.96 0.43 0.08 rg", "40 760 515 52 re f",
            "1 1 1 rg", "BT /F2 18 Tf 55 790 Td", f"({_pdf_escape(title)}) Tj",
            "0 -22 Td /F1 9 Tf", f"({_pdf_escape(subtitle)}) Tj", "ET",
            "0.15 0.13 0.11 rg",
        ]
        y = 735
        for kind, text in content:
            if kind == "heading":
                commands.extend(["0.96 0.43 0.08 rg", f"40 {y - 5} 515 22 re f", "1 1 1 rg", f"BT /F2 11 Tf 50 {y + 2} Td ({_pdf_escape(text.upper())}) Tj ET", "0.15 0.13 0.11 rg"])
                y -= 32
            elif kind == "row":
                commands.extend([f"BT /F1 9 Tf 50 {y} Td ({_pdf_escape(text)}) Tj ET"])
                y -= 15
            else:
                y -= 5
        commands.extend(["0.45 0.4 0.35 rg", f"BT /F1 8 Tf 40 28 Td ({_pdf_escape(footer)} | Page {page_number} of {len(pages)}) Tj ET"])
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        page_obj = len(objects) + 1
        content_obj = page_obj + 1
        page_refs.append(page_obj)
        objects.extend([
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_obj} 0 R >>".encode(),
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        ])
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{ref} 0 R' for ref in page_refs)}] /Count {len(page_refs)} >>".encode()
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode())
        result.extend(obj)
        result.extend(b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(result)


def _branded_detail_pdf(title, subtitle, company, sections):
    company_name = getattr(company, "name", "") or "Siya Real Build"
    company_contact = " | ".join(filter(None, [getattr(company, "phone", ""), getattr(company, "email", "")]))
    company_address = ", ".join(filter(None, [getattr(company, "address", ""), getattr(company, "city", ""), getattr(company, "state", ""), getattr(company, "pincode", "")]))
    return _invoice_pdf(
        title,
        f"{company_name} | {subtitle}",
        [("Company", [("Name", company_name), ("Contact", company_contact or "-"), ("Address", company_address or "-")])] + sections,
        company_name,
    )


def _quotation_invoice_pdf(quotation, company, document_title="QUOTATION"):
    plot, prop = quotation.plot, quotation.plot.property
    company_name = getattr(company, "name", "") or "Siya Real Build"
    company_address = ", ".join(filter(None, [getattr(company, "address", ""), getattr(company, "city", ""), getattr(company, "state", ""), getattr(company, "pincode", "")])) or "-"
    client_contact = " | ".join(filter(None, [quotation.client_phone, quotation.client_email])) or "-"
    property_location = ", ".join(filter(None, [prop.address, prop.locality, prop.city]))
    features = ", ".join(label for enabled, label in [(plot.is_corner, "Corner"), (plot.is_garden_facing, "Garden facing"), (plot.is_main_road, "Main road"), (plot.is_wide_road, "Wide road")] if enabled) or "-"
    rows = [
        ("Base plot amount", f"{quotation.plot_area_sqft or plot.area_sqft} sqft x Rs {getattr(quotation, 'agreed_rate', plot.base_rate)}/sqft", quotation.base_amount),
        ("PLC amount", f"{plot.plc_rate}% | {features}", quotation.plc_amount),
        ("Other charges", "Development / registry / applicable charges", quotation.charges_amount),
    ]
    logo_bytes = None
    if company and company.logo:
        try:
            with company.logo.open("rb") as logo_file:
                logo = Image.open(logo_file).convert("RGB")
                logo.thumbnail((420, 180))
                output = BytesIO()
                logo.save(output, format="JPEG", quality=88, optimize=True)
                logo_bytes = output.getvalue()
                logo_width, logo_height = logo.size
        except (OSError, ValueError):
            logo_bytes = None
    creator = "-"
    if quotation.created_by:
        creator = quotation.created_by.get_full_name() or quotation.created_by.email
    commands = ["1 1 1 rg 0 0 595 842 re f"]
    if logo_bytes:
        ratio = min(150 / logo_width, 58 / logo_height)
        draw_width, draw_height = logo_width * ratio, logo_height * ratio
        commands.extend(["q", f"{draw_width:.2f} 0 0 {draw_height:.2f} 38 {758 + (58 - draw_height) / 2:.2f} cm", "/Logo Do", "Q"])
    else:
        commands.extend(["0.15 0.13 0.11 rg BT /F2 18 Tf 38 790 Td", f"({_pdf_escape(company_name.upper())}) Tj", "ET"])
    def text(x, y, value, size=9, bold=False, color="0.15 0.13 0.11"):
        commands.extend([f"{color} rg", f"BT /{'F2' if bold else 'F1'} {size} Tf {x} {y} Td ({_pdf_escape(value)}) Tj ET"])
    def right_text(right_x, y, value, size=9, bold=False, color="0.15 0.13 0.11"):
        estimated_width = len(str(value)) * size * 0.48
        text(max(38, right_x - estimated_width), y, value, size, bold, color)
    def wrapped_text(x, y, value, width, size=9, bold=False, line_height=13, max_lines=2):
        for index, line in enumerate(wrap(str(value), width=width)[:max_lines]):
            text(x, y - (index * line_height), line, size, bold)
    def section_title(x, y, value):
        text(x, y, value.upper(), 10, True, "0.96 0.43 0.08")
    text(38, 744, company_name, 14, True)
    text(38, 727, company_address, 9)
    text(38, 711, f"{getattr(company, 'phone', '') or '-'} | {getattr(company, 'email', '') or '-'}", 9)
    title_size = 19 if len(document_title) > 12 else 24
    title_x = 350 if len(document_title) > 12 else 380
    text(title_x, 782, document_title, title_size, True, "0.96 0.43 0.08")
    text(380, 754, f"Created by: {creator}", 9)
    text(380, 738, f"Date: {quotation.created_at.strftime('%d %b %Y')}", 9)
    text(380, 722, f"Valid until: {quotation.valid_until or '-'}", 9)
    commands.extend(["0.96 0.43 0.08 rg 38 692 519 4 re f"])

    section_title(38, 662, "Bill To")
    text(38, 642, quotation.client_name, 11, True)
    text(38, 625, client_contact, 9)
    section_title(320, 662, "Property & Plot")
    text(320, 642, f"{prop.title} | Plot {plot.plot_number}", 10, True)
    text(320, 625, f"{plot.get_plot_category_display()} | {quotation.plot_area_sqft or plot.area_sqft} sqft | {quotation.plot_facing or (plot.get_facing_display() if plot.facing else '-')}", 9)
    wrapped_text(320, 609, property_location, 43, 8, False, 12, 2)

    table_left, table_right = 38, 557
    qty_right, description_right, detail_right = 78, 278, 467
    commands.extend(["0.14 0.12 0.10 rg 38 552 519 30 re f"])
    text(49, 563, "QTY", 9, True, "1 1 1")
    text(90, 563, "DESCRIPTION", 9, True, "1 1 1")
    text(290, 563, "RATE / DETAIL", 9, True, "1 1 1")
    text(482, 563, "AMOUNT", 9, True, "1 1 1")
    y = 525
    for index, (label, detail, amount) in enumerate(rows):
        label_lines = wrap(label, width=25)[:2]
        detail_lines = wrap(detail, width=28)[:3]
        line_count = max(len(label_lines), len(detail_lines), 1)
        row_height = max(42, 18 + (line_count * 12))
        row_center_y = y - ((row_height - 26) / 2)
        label_start_y = row_center_y + ((len(label_lines) - 1) * 6)
        detail_start_y = row_center_y + ((len(detail_lines) - 1) * 6)
        if index % 2 == 0:
            commands.extend(["0.99 0.95 0.90 rg", f"38 {y - row_height + 14} 519 {row_height} re f"])
        text(54, row_center_y, "1", 9)
        for line_index, line in enumerate(label_lines):
            text(90, label_start_y - (line_index * 13), line, 9, True)
        for line_index, line in enumerate(detail_lines):
            text(290, detail_start_y - (line_index * 13), line, 9)
        text(482, row_center_y, f"Rs {amount}", 9, True)
        y -= row_height + 4
    divider_y = y + 8
    commands.extend(["0.96 0.43 0.08 rg", f"38 {divider_y} 519 2 re f"])

    section_title(38, divider_y - 38, "Terms & Conditions")
    terms_lines = wrap(quotation.terms or "Rates and availability are subject to final verification at the time of booking.", width=58)[:6]
    for index, line in enumerate(terms_lines):
        text(38, divider_y - 58 - (index * 15), line, 9)

    totals_top = divider_y - 38
    text(375, totals_top, "Subtotal", 9, True)
    right_text(547, totals_top, f"Rs {quotation.base_amount + quotation.plc_amount + quotation.charges_amount}", 9, True)
    text(375, totals_top - 28, "Discount", 9, True)
    right_text(547, totals_top - 28, f"Rs {quotation.discount_amount}", 9, True)
    commands.extend(["0.96 0.43 0.08 rg", f"375 {totals_top - 82} 182 40 re f"])
    text(390, totals_top - 67, "TOTAL", 11, True, "1 1 1")
    right_text(547, totals_top - 67, f"Rs {quotation.total_amount}", 11, True, "1 1 1")

    commands.extend(["0.14 0.12 0.10 RG 360 142 197 1 re S"])
    right_text(547, 122, "Authorized Signature", 9)
    commands.extend(["0.96 0.43 0.08 rg 0 0 595 8 re f"])
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    resources = "/Font << /F1 3 0 R /F2 4 0 R >>"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [5 0 R] /Count 1 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        None,
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    if logo_bytes:
        resources += " /XObject << /Logo 7 0 R >>"
        objects.append(
            f"<< /Type /XObject /Subtype /Image /Width {logo_width} /Height {logo_height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(logo_bytes)} >>\nstream\n".encode()
            + logo_bytes
            + b"\nendstream"
        )
    objects[4] = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << {resources} >> /Contents 6 0 R >>".encode()
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(result)); result.extend(f"{number} 0 obj\n".encode()); result.extend(obj); result.extend(b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(result)


def _property_letterhead_pdf(prop, company):
    company_name = getattr(company, "name", "") or "Siya Real Build"
    company_address = ", ".join(filter(None, [getattr(company, "address", ""), getattr(company, "city", ""), getattr(company, "state", ""), getattr(company, "pincode", "")])) or "-"
    logo_bytes = None
    if company and company.logo:
        try:
            with company.logo.open("rb") as logo_file:
                logo = Image.open(logo_file).convert("RGB")
                logo.thumbnail((420, 180))
                output = BytesIO()
                logo.save(output, format="JPEG", quality=88, optimize=True)
                logo_bytes, logo_width, logo_height = output.getvalue(), *logo.size
        except (OSError, ValueError):
            logo_bytes = None
    commands = ["1 1 1 rg 0 0 595 842 re f"]
    if logo_bytes:
        ratio = min(150 / logo_width, 58 / logo_height)
        draw_width, draw_height = logo_width * ratio, logo_height * ratio
        commands.extend(["q", f"{draw_width:.2f} 0 0 {draw_height:.2f} 38 {758 + (58 - draw_height) / 2:.2f} cm", "/Logo Do", "Q"])
    def text(x, y, value, size=9, bold=False, color="0.15 0.13 0.11"):
        commands.extend([f"{color} rg", f"BT /{'F2' if bold else 'F1'} {size} Tf {x} {y} Td ({_pdf_escape(value)}) Tj ET"])
    def wrapped(x, y, value, width=70, size=9, bold=False, max_lines=3):
        for index, line in enumerate(wrap(str(value or "-"), width=width)[:max_lines]):
            text(x, y - (index * 13), line, size, bold)
    def heading(y, value):
        commands.extend(["0.14 0.12 0.10 rg", f"38 {y - 7} 519 26 re f"])
        text(48, y + 2, value.upper(), 10, True, "1 1 1")
    text(38, 744, company_name, 14, True)
    text(38, 727, company_address, 9)
    text(38, 711, f"{getattr(company, 'phone', '') or '-'} | {getattr(company, 'email', '') or '-'}", 9)
    text(345, 782, "PROPERTY DETAILS", 19, True, "0.96 0.43 0.08")
    text(365, 754, prop.get_category_display(), 9)
    text(365, 738, f"Status: {prop.get_status_display()}", 9)
    commands.extend(["0.96 0.43 0.08 rg 38 692 519 4 re f"])
    text(38, 658, prop.title, 18, True)
    wrapped(38, 637, prop.address, 78, 9, False, 2)

    heading(585, "Property Overview")
    overview = [
        ("Category", prop.get_category_display()), ("Listing For", prop.get_listing_for_display()),
        ("Status", prop.get_status_display()), ("Developer", prop.developer or "-"),
        ("Colony", prop.colony_name or "-"), ("Development", prop.development_name or "-"),
    ]
    y = 550
    for index, (label, value) in enumerate(overview):
        x = 38 if index % 2 == 0 else 310
        row_y = y - ((index // 2) * 31)
        text(x, row_y, label.upper(), 8, True, "0.96 0.43 0.08")
        wrapped(x, row_y - 13, value, 34, 9, False, 1)

    heading(430, "Pricing & Inventory")
    pricing = [
        ("Price", f"Rs {prop.price}"), ("Area", f"{prop.area_sqft} sqft"),
        ("Total Plots", prop.total_plots), ("Available Plots", prop.available_plots),
        ("Residential Rate", f"Rs {prop.residential_rate_per_sqft}/sqft"), ("Commercial Rate", f"Rs {prop.commercial_rate_per_sqft}/sqft"),
    ]
    y = 395
    for index, (label, value) in enumerate(pricing):
        x = 38 + ((index % 3) * 180)
        row_y = y - ((index // 3) * 38)
        text(x, row_y, label.upper(), 8, True, "0.96 0.43 0.08")
        text(x, row_y - 14, value, 10, True)

    heading(300, "Location & Legal")
    text(38, 266, "LOCATION", 8, True, "0.96 0.43 0.08")
    wrapped(38, 251, ", ".join(filter(None, [prop.locality, prop.city])), 42, 9)
    text(310, 266, "LANDMARK", 8, True, "0.96 0.43 0.08")
    wrapped(310, 251, prop.landmark or "-", 38, 9)
    text(38, 215, "RERA", 8, True, "0.96 0.43 0.08"); text(38, 200, prop.rera_number or "-", 9)
    text(220, 215, "T&CP", 8, True, "0.96 0.43 0.08"); text(220, 200, prop.tcp_approval_number or "-", 9)
    text(400, 215, "REGISTRY", 8, True, "0.96 0.43 0.08"); text(400, 200, prop.registry_status or "-", 9)
    commands.extend(["0.96 0.43 0.08 rg 0 0 595 8 re f"])
    amenities = ", ".join(str(value).replace("_", " ").title() for value in prop.selected_amenities) or prop.custom_amenities or "-"
    heading(155, "Amenities & Nearby")
    wrapped(38, 122, f"Amenities: {amenities}", 72, 8, False, 2)
    wrapped(38, 94, f"Connectivity: {prop.nearby_connectivity or '-'}", 72, 8, False, 2)
    wrapped(310, 122, f"Education / Healthcare: {prop.nearby_education or '-'} / {prop.nearby_healthcare or '-'}", 45, 8, False, 3)
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    resources = "/Font << /F1 3 0 R /F2 4 0 R >>"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", None, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>", None, b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    if logo_bytes:
        resources += " /XObject << /Logo 7 0 R >>"
        objects.append(f"<< /Type /XObject /Subtype /Image /Width {logo_width} /Height {logo_height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(logo_bytes)} >>\nstream\n".encode() + logo_bytes + b"\nendstream")
    objects[4] = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << {resources} >> /Contents 6 0 R >>".encode()
    page_refs = [5]
    photos = list(prop.photos.all())[:8]
    for photo_group_start in range(0, len(photos), 4):
        photo_group = photos[photo_group_start:photo_group_start + 4]
        page_obj = len(objects) + (len(photo_group) * 1) + 1
        content_obj = page_obj + 1
        page_commands = ["1 1 1 rg 0 0 595 842 re f", "0.96 0.43 0.08 rg 38 778 519 4 re f", f"0.15 0.13 0.11 rg BT /F2 17 Tf 38 800 Td (PROPERTY PHOTOS) Tj ET"]
        xobjects = []
        for index, photo in enumerate(photo_group):
            try:
                with photo.image.open("rb") as image_file:
                    image = Image.open(image_file).convert("RGB"); image.thumbnail((900, 900))
                    output = BytesIO(); image.save(output, format="JPEG", quality=84, optimize=True)
                    image_bytes, image_width, image_height = output.getvalue(), *image.size
            except (OSError, ValueError):
                continue
            image_obj = len(objects) + 1
            objects.append(f"<< /Type /XObject /Subtype /Image /Width {image_width} /Height {image_height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(image_bytes)} >>\nstream\n".encode() + image_bytes + b"\nendstream")
            col, row = index % 2, index // 2
            box_x, box_y = 28 + (col * 272), 398 - (row * 342)
            ratio = min(267 / image_width, 292 / image_height)
            draw_width, draw_height = image_width * ratio, image_height * ratio
            draw_x, draw_y = box_x + (267 - draw_width) / 2, box_y + 34 + (292 - draw_height) / 2
            page_commands.extend(["q", f"{draw_width:.2f} 0 0 {draw_height:.2f} {draw_x:.2f} {draw_y:.2f} cm", f"/Img{image_obj} Do", "Q", f"0.15 0.13 0.11 rg BT /F1 8 Tf {box_x + 4} {box_y + 12} Td ({_pdf_escape(photo.caption or prop.title)}) Tj ET"])
            xobjects.append(f"/Img{image_obj} {image_obj} 0 R")
        page_stream = "\n".join(page_commands + ["0.96 0.43 0.08 rg 0 0 595 8 re f"]).encode("latin-1", errors="replace")
        page_obj = len(objects) + 1; content_obj = page_obj + 1
        objects.extend([f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> /XObject << {' '.join(xobjects)} >> >> /Contents {content_obj} 0 R >>".encode(), b"<< /Length " + str(len(page_stream)).encode() + b" >>\nstream\n" + page_stream + b"\nendstream"])
        page_refs.append(page_obj)
    media_items = []
    for document in prop.documents.all():
        if document.document_type == "map" and document.file.name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            media_items.append(("COLONY MAP / LAYOUT", document.title or "Map / Layout", document.file))
    for page_title, caption, image_field in media_items:
        try:
            with image_field.open("rb") as image_file:
                image = Image.open(image_file).convert("RGB")
                image.thumbnail((1500, 1900))
                output = BytesIO(); image.save(output, format="JPEG", quality=85, optimize=True)
                image_bytes, image_width, image_height = output.getvalue(), *image.size
        except (OSError, ValueError):
            continue
        image_obj = len(objects) + 1
        page_obj = image_obj + 1
        content_obj = page_obj + 1
        ratio = min(515 / image_width, 650 / image_height)
        draw_width, draw_height = image_width * ratio, image_height * ratio
        x, y = (595 - draw_width) / 2, 105 + (650 - draw_height) / 2
        page_commands = [
            "1 1 1 rg 0 0 595 842 re f",
            "0.96 0.43 0.08 rg 38 778 519 4 re f",
            f"0.15 0.13 0.11 rg BT /F2 17 Tf 38 800 Td ({_pdf_escape(page_title)}) Tj ET",
            f"0.45 0.4 0.35 rg BT /F1 9 Tf 38 760 Td ({_pdf_escape(caption)}) Tj ET",
            "q", f"{draw_width:.2f} 0 0 {draw_height:.2f} {x:.2f} {y:.2f} cm", f"/Img{image_obj} Do", "Q",
            "0.96 0.43 0.08 rg 0 0 595 8 re f",
        ]
        page_stream = "\n".join(page_commands).encode("latin-1", errors="replace")
        objects.extend([
            f"<< /Type /XObject /Subtype /Image /Width {image_width} /Height {image_height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(image_bytes)} >>\nstream\n".encode() + image_bytes + b"\nendstream",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> /XObject << /Img{image_obj} {image_obj} 0 R >> >> /Contents {content_obj} 0 R >>".encode(),
            b"<< /Length " + str(len(page_stream)).encode() + b" >>\nstream\n" + page_stream + b"\nendstream",
        ])
        page_refs.append(page_obj)
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{ref} 0 R' for ref in page_refs)}] /Count {len(page_refs)} >>".encode()
    result = bytearray(b"%PDF-1.4\n"); offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(result)); result.extend(f"{number} 0 obj\n".encode()); result.extend(obj); result.extend(b"\nendobj\n")
    xref = len(result); result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(result)


def property_pdf_bytes(prop):
    company = getattr(getattr(prop.owner, "profile", None), "company", None)
    return _property_letterhead_pdf(prop, company)


def plot_pdf_bytes(plot):
    prop = plot.property
    company = getattr(getattr(prop.owner, "profile", None), "company", None)
    features = ", ".join(label for enabled, label in [(plot.is_corner, "Corner"), (plot.is_garden_facing, "Garden facing"), (plot.is_main_road, "Main road"), (plot.is_wide_road, "Wide road")] if enabled) or "-"
    return _plot_letterhead_pdf(plot, prop, company, features)


def _plot_letterhead_pdf(plot, prop, company, features):
    company_name = getattr(company, "name", "") or "Siya Real Build"
    company_address = ", ".join(filter(None, [getattr(company, "address", ""), getattr(company, "city", ""), getattr(company, "state", ""), getattr(company, "pincode", "")])) or "-"
    logo_bytes = None
    if company and company.logo:
        try:
            with company.logo.open("rb") as logo_file:
                logo = Image.open(logo_file).convert("RGB"); logo.thumbnail((420, 180))
                output = BytesIO(); logo.save(output, format="JPEG", quality=88, optimize=True)
                logo_bytes, logo_width, logo_height = output.getvalue(), *logo.size
        except (OSError, ValueError):
            logo_bytes = None
    commands = ["1 1 1 rg 0 0 595 842 re f"]
    if logo_bytes:
        ratio = min(150 / logo_width, 58 / logo_height)
        draw_width, draw_height = logo_width * ratio, logo_height * ratio
        commands.extend(["q", f"{draw_width:.2f} 0 0 {draw_height:.2f} 38 {758 + (58 - draw_height) / 2:.2f} cm", "/Logo Do", "Q"])
    def text(x, y, value, size=9, bold=False, color="0.15 0.13 0.11"):
        commands.extend([f"{color} rg", f"BT /{'F2' if bold else 'F1'} {size} Tf {x} {y} Td ({_pdf_escape(value)}) Tj ET"])
    def wrapped(x, y, value, width=68, size=9, max_lines=2):
        for index, line in enumerate(wrap(str(value or "-"), width=width)[:max_lines]):
            text(x, y - (index * 13), line, size)
    def heading(y, value):
        commands.extend(["0.14 0.12 0.10 rg", f"38 {y - 7} 519 26 re f"])
        text(48, y + 2, value.upper(), 10, True, "1 1 1")
    text(38, 744, company_name, 14, True); text(38, 727, company_address, 9)
    text(38, 711, f"{getattr(company, 'phone', '') or '-'} | {getattr(company, 'email', '') or '-'}", 9)
    text(390, 782, "PLOT DETAILS", 20, True, "0.96 0.43 0.08")
    text(390, 754, f"Plot {plot.plot_number}", 11, True); text(390, 737, f"Status: {plot.get_status_display()}", 9)
    commands.extend(["0.96 0.43 0.08 rg 38 692 519 4 re f"])
    text(38, 658, f"{prop.title} | Plot {plot.plot_number}", 18, True)
    wrapped(38, 637, prop.address, 78, 9, 2)
    heading(585, "Plot Overview")
    overview = [("Plot Number", plot.plot_number), ("Block", plot.block or "-"), ("Category", plot.get_plot_category_display()), ("Status", plot.get_status_display()), ("Features", features), ("Colony", prop.colony_name or prop.title)]
    y = 550
    for index, (label, value) in enumerate(overview):
        x, row_y = (38 if index % 2 == 0 else 310), y - ((index // 2) * 31)
        text(x, row_y, label.upper(), 8, True, "0.96 0.43 0.08"); wrapped(x, row_y - 13, value, 34, 9, 1)
    heading(430, "Dimensions & Features")
    dimensions = [("Area", f"{plot.area_sqft} sqft"), ("Dimensions", f"{plot.length_ft or '-'} x {plot.width_ft or '-'} ft"), ("Facing", plot.get_facing_display() if plot.facing else "-"), ("Road Width", f"{plot.road_width_ft} ft" if plot.road_width_ft else "-"), ("Features", features), ("Notes", plot.notes or "-")]
    y = 395
    for index, (label, value) in enumerate(dimensions):
        x, row_y = (38 if index % 2 == 0 else 310), y - ((index // 2) * 31)
        text(x, row_y, label.upper(), 8, True, "0.96 0.43 0.08"); wrapped(x, row_y - 13, value, 34, 9, 1)
    heading(275, "Pricing")
    pricing = [("Base Rate", f"Rs {plot.base_rate}/sqft"), ("PLC", f"{plot.plc_rate}%"), ("Extra Charges", f"Rs {plot.extra_charges}"), ("Final Price", f"Rs {plot.price}")]
    for index, (label, value) in enumerate(pricing):
        x = 38 + ((index % 2) * 272); row_y = 240 - ((index // 2) * 42)
        text(x, row_y, label.upper(), 8, True, "0.96 0.43 0.08"); text(x, row_y - 15, value, 11, True)
    commands.extend(["0.14 0.12 0.10 RG 360 115 197 1 re S"]); text(425, 95, "Authorized Signature", 9)
    commands.extend(["0.96 0.43 0.08 rg 0 0 595 8 re f"])
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    resources = "/Font << /F1 3 0 R /F2 4 0 R >>"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [5 0 R] /Count 1 >>", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>", None, b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    if logo_bytes:
        resources += " /XObject << /Logo 7 0 R >>"; objects.append(f"<< /Type /XObject /Subtype /Image /Width {logo_width} /Height {logo_height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(logo_bytes)} >>\nstream\n".encode() + logo_bytes + b"\nendstream")
    objects[4] = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << {resources} >> /Contents 6 0 R >>".encode()
    result = bytearray(b"%PDF-1.4\n"); offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(result)); result.extend(f"{number} 0 obj\n".encode()); result.extend(obj); result.extend(b"\nendobj\n")
    xref = len(result); result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(result)


def quotation_pdf_bytes(quotation):
    company = getattr(getattr(quotation.plot.property.owner, "profile", None), "company", None)
    return _quotation_invoice_pdf(quotation, company)


def booking_pdf_bytes(booking):
    plot = booking.plot
    prop = plot.property
    company = getattr(getattr(prop.owner, "profile", None), "company", None)
    area = booking.plot_area_sqft or plot.area_sqft
    invoice = SimpleNamespace(
        plot=plot,
        client_name=booking.client_name,
        client_phone=booking.client_phone,
        client_email=booking.client_email,
        plot_area_sqft=area,
        plot_facing=booking.plot_facing,
        base_amount=area * booking.agreed_rate,
        plc_amount=booking.plc_amount,
        charges_amount=booking.charges_amount,
        discount_amount=booking.discount_amount + booking.coupon_discount_amount,
        total_amount=booking.total_deal_value,
        agreed_rate=booking.agreed_rate,
        terms=f"Booking status: {booking.get_status_display()}. Paid: Rs {booking.paid_amount}. Balance due: Rs {booking.balance_amount}. {booking.note or ''}",
        created_by=booking.created_by,
        created_at=booking.created_at,
        valid_until=booking.booking_date,
    )
    return _quotation_invoice_pdf(invoice, company, document_title="BOOKING INVOICE")
