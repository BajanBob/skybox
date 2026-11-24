import sys
sys.path.insert(0, "hardware/rx1/scripts")
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import ParagraphStyle
from pypdf import PdfReader, PdfWriter
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment

FD = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DV", FD + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", FD + "DejaVuSans-Bold.ttf"))
NAVY = colors.HexColor("#1F3A5F"); TEAL = colors.HexColor("#2A7F8E")
B = ParagraphStyle("b", fontName="DV", fontSize=9.4, leading=12.6, spaceAfter=4)
H = ParagraphStyle("h", fontName="DVB", fontSize=10, leading=13, textColor=TEAL, spaceBefore=4, spaceAfter=2)
T = ParagraphStyle("t", fontName="DVB", fontSize=14, leading=18, textColor=NAVY, spaceAfter=4)
SM = ParagraphStyle("sm", fontName="DV", fontSize=7.6, leading=9.6)
SMB = ParagraphStyle("smb", parent=SM, fontName="DVB")
BUL = ParagraphStyle("bul", parent=B, leftIndent=12, bulletIndent=2, spaceAfter=2)
OUT = "hardware/rx1/rfq/"

OPTIONAL = [
 ("O1", "Media module", "Raspberry Pi", "Raspberry Pi 5, 4 GB or 8 GB", "Phase-2 HDMI video + audio out; runs Skybox Recon headless + Kodi/VLC", 1),
 ("O2", "Media module", "TBS Technologies (or eq.)", "USB DVB-S/S2/S2X tuner box, e.g. TBS5927 (Linux driver support required)", "Demodulates the satellite TV signal for the Pi", 1),
 ("O3", "Media module", "Any", "2-way satellite splitter 950–2400 MHz, one port DC-pass", "Shares the J3 dish feed between RX-1 and the tuner", 1),
 ("O4", "Media module", "Pololu (or eq.)", "D36V50F5 step-down 12 V → 5 V 5 A", "Runs the Pi 5 from the same 12.8 V battery", 1),
 ("O5", "Media module", "Raspberry Pi", "Active Cooler + micro-HDMI to HDMI cable + 64 GB microSD", "Pi accessories", 1),
 ("O6", "On-board (DNP option)", "Texas Instruments", "PCM5102APWR + J11 SJ-3523-SMT", "3.5 mm line/headphone out (fit if wanted)", 1),
 ("O7", "On-board (DNP option)", "Any", "0.96 in SSD1306 I2C OLED, 128×64, on J12", "Status display: band, voltage, LO lock", 1),
 ("O8", "On-board (alternate)", "Espressif", "ESP32-S3-WROOM-1U-N16R8 + u.FL 2.4 GHz antenna", "Use instead of U27 if the metal case blocks Wi-Fi", 1),
 ("O9", "On-board (DNP option)", "Analog Devices", "LTC3260EMSE#PBF", "-3.3 V rail, only if the chosen RF switches need it", 1),
 ("O10", "External", "Leo Bodnar (or eq.)", "Mini GPS-disciplined 10 MHz reference (GPSDO)", "Feeds J8 for very stable LO / Ka-band work", 1),
 ("O11", "External", "Any", "Second LiFePO4 4S 12.8 V 6 Ah pack (UN38.3)", "Spare / longer field use", 1),
 ("O12", "External", "Nuand", "bladeRF 2.0 micro xA4 (if supplier can source)", "Digitizer — only if quoting a complete kit", 1),
]

SUPPLIERS = {
 "PCBWay": dict(file="Letter_PCBWay", addr="PCBWay — PCB Design Service<br/>Hangzhou, China<br/>Via: pcbway.com → PCB Design → Quote",
   ask=["Schematic capture from the attached functional sheets (sheets 1–5) and BOM, using the listed parts or approved alternates.",
        "PCB layout of a 4-layer hybrid board: Rogers RO4350B 0.254 mm RF layer over FR-4, 50 Ω controlled impedance, shield frames.",
        "Fabrication and assembly of 5 prototypes, with a price for 25 units, including sourcing of all parts.",
        "Native design files (schematic + layout, KiCad preferred) as well as Gerbers, drill, pick-and-place and final BOM."],
   why="your design service can start from a concept or block diagram and carry it through schematic, layout, prototype and assembly"),
 "JLCPCB": dict(file="Letter_JLCPCB", addr="JLCPCB — PCB Layout Service<br/>Shenzhen, China<br/>Via: design.jlcpcb.com",
   ask=["PCB layout from our schematic (we will supply the captured schematic and netlist once ready; please quote now from the attached functional sheets).",
        "Layout of a 4-layer hybrid board with an RF section to 12 GHz: RO4350B top dielectric over FR-4, 50 Ω CPWG, via fences, shield frames.",
        "Fabrication + SMT assembly of 5 prototypes and a price for 25, with JLC parts library matches and alternates for anything not stocked.",
        "Native layout files (KiCad or EasyEDA), Gerbers, pick-and-place, and an impedance/TDR report."],
   why="your layout service covers RF and high-speed boards and works with KiCad, Altium and EasyEDA"),
 "AtlasPCB": dict(file="Letter_AtlasPCB", addr="Atlas PCB — RF / Microwave PCB<br/>Sales &amp; Engineering<br/>Via: the RFQ form on the company website",
   ask=["Fabrication quote for a 4-layer hybrid stack: Rogers RO4350B 0.254 mm (L1–L2) bonded to FR-4, ~1.6 mm total, ENIG, filled and capped via-in-pad.",
        "An engineering review of the 2–12 GHz section (sheet 4): stack-up, grounded coplanar waveguide dimensions, via fencing and shield-frame placement.",
        "Optional: layout of the microwave section only, if you offer it, to be merged with the rest of the board.",
        "Impedance coupons, TDR report and X-ray inspection of QFN/LGA parts; quantities 5 and 25."],
   why="you specialise in RF and microwave materials, which is the hardest part of this board"),
}

def letter(name, s):
    path = OUT + "_tmp_" + s["file"] + ".pdf"
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=16*mm, bottomMargin=16*mm,
                            title=f"RFQ - RX-1 receiver - {name}", author="Skybox Recon project")
    S = []
    head = Table([[Paragraph("<b>Skybox Recon project</b><br/>[Your name]<br/>[Street address]<br/>[City, Country]<br/>[Email] • [Phone / WhatsApp]<br/>github.com/BajanBob/skybox", SM),
                   Paragraph("24 November 2026<br/><br/><b>Ref:</b> RX-1 Rev A — RFQ", SM)]], colWidths=[120*mm, 50*mm])
    head.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LINEBELOW", (0,0), (-1,0), 1, NAVY), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
    S += [head, Spacer(1, 4*mm), Paragraph(s["addr"], B), Spacer(1, 3*mm),
          Paragraph("Request for quotation: RX-1 multiband satellite and radio receiver board", T),
          Paragraph("Dear Sir or Madam,", B),
          Paragraph(f"We are developing <b>RX-1</b>, a battery-powered, receive-only RF front-end for our open satellite and radio software, Skybox Recon. "
                    f"We are approaching {name} because {s['why']}. We would like a quotation for the work listed below.", B),
          Paragraph("About the board", H),
          Paragraph("Four RF inputs — 1–1000 MHz, L-band 1–2 GHz, dish LNB IF 950–2150 MHz (with on-board 13/18 V and 22 kHz LNB control), and 2–12 GHz with a downconverter — are switched to one SMA output for an external digitizer. "
                    "An ESP32-S3 controls the board over USB-C and Wi-Fi. Power is 9–16 V DC or USB-C PD. The product is intended for sale worldwide.", B),
          Paragraph("Scope of work requested", H)]
    S += [Paragraph(a, BUL, bulletText="•") for a in s["ask"]]
    S += [Paragraph("Please include in your quotation", H)]
    S += [Paragraph(a, BUL, bulletText="•") for a in [
            "Price and lead time for: (a) design/layout only, (b) design + 5 prototypes, (c) design + 25 units.",
            "Any BOM parts you cannot source, with proposed alternates (items marked “Verify” in the BOM need your confirmation).",
            "Your DFM requirements for the RF section, and the CAD tool you will use.",
            "Payment terms, shipping options to our location, and whether an NDA is required or offered."]]
    S += [Paragraph("Enclosed", H),
          Paragraph("Bound into this PDF: the optional parts list and the functional schematic sheets (system block diagram plus sheets 1–5 with connection tables). "
                    "Sent with it: the full design package (RX-1_Design_Package_RevA.pdf) and the BOM (RX-1_BOM_RevA.xlsx / .csv). "
                    "The schematics are functional, not pin-accurate; we expect your engineers to complete pin-level schematics from the manufacturers’ datasheets and send them to us for approval before layout.", B),
          Paragraph("Thank you for your time. We look forward to your quotation and are happy to answer technical questions by email.", B),
          Spacer(1, 4*mm), Paragraph("Yours faithfully,", B), Spacer(1, 7*mm),
          Paragraph("[Your name]<br/>Skybox Recon project", B),
          PageBreak(),
          Paragraph("Attachment A — Optional parts list", T),
          Paragraph("Not part of the base quotation. Please quote separately only if you can supply or fit these items. "
                    "DNP = footprint placed on the board, part not fitted unless ordered.", B)]
    rows = [["#", "Group", "Manufacturer", "Part", "Purpose", "Qty"]] + [list(map(str, r)) for r in OPTIONAL]
    t = Table([[Paragraph(c, SMB if i == 0 else SM) for c in r] for i, r in enumerate(rows)],
              colWidths=[10*mm, 26*mm, 28*mm, 50*mm, 50*mm, 8*mm], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#C5CCD6")), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#EEF2F6")),
                           ("VALIGN", (0,0), (-1,-1), "TOP")]))
    S += [t, Spacer(1, 4*mm),
          Paragraph("Attachment B — Schematic sheets", T),
          Paragraph("The following pages are the system block diagram and functional schematic sheets 1–5 from the RX-1 design package, Rev A.", B)]
    doc.build(S)
    # merge: letter + schematic pages (design package pages 2-7)
    w = PdfWriter()
    for p in PdfReader(path).pages: w.add_page(p)
    dp = PdfReader(OUT + "RX-1_Design_Package_RevA.pdf")
    for i in range(1, 7): w.add_page(dp.pages[i])
    w.add_metadata({"/Title": f"RFQ - RX-1 receiver - {name}", "/Author": "Skybox Recon project"})
    final = OUT + s["file"] + "_RX-1_RFQ.pdf"
    with open(final, "wb") as f: w.write(f)
    import os; os.remove(path)
    return final

for n, s in SUPPLIERS.items(): print(letter(n, s))

# add optional parts sheet to the BOM workbook
wb = load_workbook(OUT + "RX-1_BOM_RevA.xlsx")
if "Optional parts" in wb.sheetnames: del wb["Optional parts"]
ws = wb.create_sheet("Optional parts", 1)
ws.append(["#", "Group", "Manufacturer", "Part", "Purpose", "Qty", "Unit price (supplier)", "Lead time (supplier)"])
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F3A5F")
for r in OPTIONAL:
    ws.append(list(r) + ["", ""])
    for c in ws[ws.max_row]: c.alignment = Alignment(wrap_text=True, vertical="top")
for col, wd in zip("ABCDEFGH", [6, 20, 24, 48, 52, 6, 16, 16]): ws.column_dimensions[col].width = wd
ws.freeze_panes = "A2"
wb.save(OUT + "RX-1_BOM_RevA.xlsx")
