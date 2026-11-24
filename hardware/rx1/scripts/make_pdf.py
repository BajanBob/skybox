import sys
sys.path.insert(0, "hardware/rx1/scripts")
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
                                Table, TableStyle, PageBreak, Flowable, NextPageTemplate, KeepTogether)
from reportlab.lib.styles import ParagraphStyle
from bom_data import BOM

FD = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DV", FD + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", FD + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DVC", FD + "DejaVuSansCondensed.ttf"))
NAVY = colors.HexColor("#1F3A5F"); TEAL = colors.HexColor("#2A7F8E"); AMB = colors.HexColor("#C77D1A")
GREY = colors.HexColor("#5A6270"); LIGHT = colors.HexColor("#EEF2F6")
FILLS = {"rf": colors.HexColor("#E3F0F4"), "pwr": colors.HexColor("#FCEBD7"), "ctl": colors.HexColor("#E8E6F5"),
         "con": colors.HexColor("#FFFFFF"), "ext": colors.HexColor("#EDEDED"), "lo": colors.HexColor("#E2F2E2")}

H1 = ParagraphStyle("h1", fontName="DVB", fontSize=15, leading=19, textColor=NAVY, spaceAfter=6, spaceBefore=4)
H2 = ParagraphStyle("h2", fontName="DVB", fontSize=11, leading=14, textColor=TEAL, spaceAfter=4, spaceBefore=8)
B = ParagraphStyle("b", fontName="DV", fontSize=9, leading=12.5, spaceAfter=4)
SM = ParagraphStyle("sm", fontName="DV", fontSize=7.5, leading=9.5)
SMB = ParagraphStyle("smb", parent=SM, fontName="DVB")
BUL = ParagraphStyle("bul", parent=B, leftIndent=10, bulletIndent=2)

def P(t, s=B): return Paragraph(t, s)
def bullets(items): return [Paragraph(i, BUL, bulletText="•") for i in items]

def table(rows, widths, head=True, fs=7.5):
    data = [[Paragraph(str(c), SMB if (head and r == 0) else SM) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C5CCD6")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
          ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if head: st += [("BACKGROUND", (0, 0), (-1, 0), LIGHT)]
    t.setStyle(TableStyle(st)); return t

# ---------------- diagram engine (units = mm) ----------------
class Diagram(Flowable):
    def __init__(self, w, h, blocks, wires, title=None, notes=None):
        super().__init__(); self.w, self.h = w * mm, h * mm
        self.blocks, self.wires, self.title, self.notes = blocks, wires, title, notes or []
    def wrap(self, *a): return self.w, self.h
    def draw(self):
        c = self.canv
        c.setStrokeColor(GREY); c.setLineWidth(0.6); c.rect(0, 0, self.w, self.h)
        bx = {}
        for k, (x, y, w, h, t, sub, kind) in self.blocks.items():
            bx[k] = (x, y, w, h)
            c.setFillColor(FILLS.get(kind, colors.white)); c.setStrokeColor(NAVY if kind != "ext" else GREY)
            c.setDash(2, 1.5) if kind == "ext" else c.setDash()
            c.setLineWidth(0.8); c.roundRect(x * mm, y * mm, w * mm, h * mm, 1.2 * mm, fill=1, stroke=1); c.setDash()
            lines = sub.split("|") if sub else []
            tot = 1 + len(lines); top = y + h / 2 + (tot - 1) * 1.55
            c.setFillColor(NAVY); c.setFont("DVB", 6.3); c.drawCentredString((x + w / 2) * mm, (top - 1) * mm, t)
            c.setFillColor(colors.black); c.setFont("DVC", 5.4)
            for i, l in enumerate(lines): c.drawCentredString((x + w / 2) * mm, (top - 1 - 3.1 * (i + 1)) * mm, l)
        for wdef in self.wires:
            a, b, lab = wdef[0], wdef[1], wdef[2] if len(wdef) > 2 else ""
            col = wdef[3] if len(wdef) > 3 else "sig"
            ax, ay, aw, ah = bx[a]; bx_, by, bw, bh = bx[b]
            # choose sides
            if bx_ >= ax + aw - 0.1: x1, y1, x2, y2 = ax + aw, ay + ah / 2, bx_, by + bh / 2
            elif bx_ + bw <= ax + 0.1: x1, y1, x2, y2 = ax, ay + ah / 2, bx_ + bw, by + bh / 2
            elif by >= ay + ah: x1, y1, x2, y2 = ax + aw / 2, ay + ah, bx_ + bw / 2, by
            else: x1, y1, x2, y2 = ax + aw / 2, ay, bx_ + bw / 2, by + bh
            stroke = {"sig": NAVY, "pwr": AMB, "ctl": colors.HexColor("#6A55B5"), "lo": colors.HexColor("#2E8B57")}[col]
            c.setStrokeColor(stroke); c.setFillColor(stroke); c.setLineWidth(0.9 if col == "sig" else 0.7)
            if col == "ctl": c.setDash(1.6, 1.2)
            horiz = abs(x2 - x1) >= abs(y2 - y1) or (x2 != x1 and abs(y2 - y1) < 0.5)
            if horiz and abs(y2 - y1) > 0.3:  # elbow
                xm = (x1 + x2) / 2
                pts = [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]
            elif not horiz and abs(x2 - x1) > 0.3:
                ym = (y1 + y2) / 2
                pts = [(x1, y1), (x1, ym), (x2, ym), (x2, y2)]
            else: pts = [(x1, y1), (x2, y2)]
            p = c.beginPath(); p.moveTo(pts[0][0] * mm, pts[0][1] * mm)
            for q in pts[1:]: p.lineTo(q[0] * mm, q[1] * mm)
            c.drawPath(p, stroke=1, fill=0); c.setDash()
            # arrow head
            (px, py), (qx, qy) = pts[-2], pts[-1]
            import math
            ang = math.atan2(qy - py, qx - px); L = 1.6
            ah_ = c.beginPath(); ah_.moveTo(qx * mm, qy * mm)
            ah_.lineTo((qx - L * math.cos(ang - 0.4)) * mm, (qy - L * math.sin(ang - 0.4)) * mm)
            ah_.lineTo((qx - L * math.cos(ang + 0.4)) * mm, (qy - L * math.sin(ang + 0.4)) * mm); ah_.close()
            c.drawPath(ah_, stroke=0, fill=1)
            if lab:
                mx, my = pts[len(pts) // 2 - 1] if len(pts) > 2 else ((x1 + x2) / 2, (y1 + y2) / 2)
                if len(pts) > 2: mx, my = (pts[1][0] + pts[2][0]) / 2, (pts[1][1] + pts[2][1]) / 2
                c.setFont("DVC", 4.8); c.setFillColor(stroke)
                c.drawCentredString(mx * mm, (my + 0.8) * mm, lab)
        # legend
        c.setFont("DVC", 5); y = 2.5
        for i, (nm, colr) in enumerate([("RF signal", NAVY), ("Power", AMB), ("Control (I2C/SPI/GPIO)", colors.HexColor("#6A55B5")), ("LO / 10 MHz ref", colors.HexColor("#2E8B57"))]):
            x = 3 + i * 32; c.setStrokeColor(colr); c.setLineWidth(1); c.line(x * mm, (y + 0.8) * mm, (x + 5) * mm, (y + 0.8) * mm)
            c.setFillColor(colors.black); c.drawString((x + 6) * mm, y * mm, nm)

def blk(x, y, w, h, t, sub="", kind="rf"): return (x, y, w, h, t, sub, kind)

# ---------------- page furniture ----------------
def furniture(c, d):
    c.saveState(); W, Hh = c._pagesize
    c.setFillColor(NAVY); c.rect(0, Hh - 9 * mm, W, 9 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("DVB", 8); c.drawString(12 * mm, Hh - 6 * mm, "RX-1 Multiband Receiver Front-End  |  Design & Quote Package  |  Rev A (draft)")
    c.setFont("DV", 7); c.drawRightString(W - 12 * mm, Hh - 6 * mm, "Skybox Recon project  •  2026-11-24")
    c.setFillColor(GREY); c.setFont("DV", 6.5)
    c.drawString(12 * mm, 7 * mm, "Functional design for schematic capture & layout. Not pin-accurate: the design house completes pin-level schematics from the cited datasheets.")
    c.drawRightString(W - 12 * mm, 7 * mm, f"Page {d.page}")
    c.restoreState()

out = "hardware/rx1/rfq/RX-1_Design_Package_RevA.pdf"
doc = BaseDocTemplate(out, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=13 * mm,
                      title="RX-1 Multiband Receiver - Design & Quote Package Rev A", author="Skybox Recon project")
fp = Frame(14 * mm, 13 * mm, A4[0] - 28 * mm, A4[1] - 27 * mm, id="p")
LW, LH = landscape(A4)
fl = Frame(12 * mm, 12 * mm, LW - 24 * mm, LH - 24 * mm, id="l")
doc.addPageTemplates([PageTemplate("port", [fp], onPage=furniture, pagesize=A4),
                      PageTemplate("land", [fl], onPage=furniture, pagesize=landscape(A4))])
S = []

# ---------------- 1. cover / summary ----------------
S += [Spacer(1, 6 * mm), P("RX-1 Multiband Receiver Front-End", ParagraphStyle("t", fontName="DVB", fontSize=22, leading=26, textColor=NAVY)),
      P("Design &amp; Quote Package (RFQ) — Revision A, draft for supplier review", ParagraphStyle("st", fontName="DV", fontSize=11, textColor=TEAL, leading=15)),
      Spacer(1, 4 * mm)]
S += [table([["Item", "Value"],
             ["Product", "RX-1: battery-powered, receive-only multiband RF front-end for the Skybox Recon software (global market)"],
             ["Coverage", "A: 1–1000 MHz  •  B: L-band 1–2 GHz (active-antenna bias)  •  C: dish LNB IF 950–2150 MHz with 13/18 V + 22 kHz + DiSEqC  •  D: 2–12 GHz (X-band, Ku direct, C-band direct)"],
             ["Output", "One SMA RF output to an external 12-bit digitizer (Nuand bladeRF 2.0 micro xA4) → USB 3 → laptop"],
             ["Control", "ESP32-S3: USB-C (CDC serial) and Wi-Fi/BLE to Skybox Recon; I2C/SPI to all RF parts"],
             ["Power", "9–16 V DC (LiFePO4 4S 12.8 V, 13.8 V station supply, 12 V vehicle) or USB-C PD 9/12 V; ~3–5 W typical, ~12 W worst case with LNB"],
             ["Audio", "Speaker for satellite-finder beep and alerts; optional 3.5 mm line/headphone out (I2S DAC)"],
             ["Video", "Not on RX-1. See section 9 for the optional media module (HDMI + audio)"],
             ["Files", "This PDF  •  RX-1_BOM_RevA.xlsx (BOM, power budget, RFQ asks)  •  RX-1_BOM_RevA.csv  •  README.txt"]],
            [32, 150])]
S += [P("1. What we are asking suppliers to do", H2)]
S += bullets(["<b>Schematic capture</b> from the functional sheets in this package (sections 3–7), using the BOM part numbers or approved alternates.",
              "<b>PCB layout</b> of a 4-layer hybrid board (Rogers RO4350B RF layer over FR-4), with 50 Ω controlled impedance and shield cans (section 8).",
              "<b>Prototype fabrication and assembly</b>: 5 boards, with a price for 25.",
              "<b>Deliverables</b>: native CAD files (KiCad preferred; Altium accepted), PDF schematics, Gerbers/ODB++, drill files, pick-and-place, final BOM, impedance/TDR report, X-ray of RF QFN/LGA parts.",
              "Firmware is supplied by the Skybox Recon project; the supplier only needs to confirm that the board enumerates over USB and that every I2C/SPI part answers (section 10)."])

# ---------------- 2. block diagram (landscape) ----------------
S += [NextPageTemplate("land"), PageBreak(), P("2. System block diagram", H1)]
bw, bh = 31, 13
blocks = {
 "JA": blk(2, 140, 26, bh, "J4 SMA", "Input A|1–1000 MHz", "con"),
 "A1": blk(36, 140, bw, bh, "Limiter + FM notch", "CLA4609 | NSBP-108+ |bypass SPDT"),
 "A2": blk(75, 140, bw, bh, "LNA + LPF", "SPF5189Z | LFCN-1000+"),
 "JB": blk(2, 116, 26, bh, "J5 SMA", "Input B|L-band 1–2 GHz", "con"),
 "B1": blk(36, 116, bw, bh, "Limiter + BPF", "1.45–1.7 GHz | bypass|bias-T 5/3.3 V"),
 "B2": blk(75, 116, bw, bh, "LNA", "SPF5189Z"),
 "JC": blk(2, 92, 26, bh, "J3 F-type", "Input C|Dish LNB IF", "con"),
 "C1": blk(36, 92, bw, bh, "DC block + BPF", "950–2150 MHz"),
 "C2": blk(75, 92, bw, bh, "IF gain", "ADL5611"),
 "LNB": blk(36, 74, bw, 12, "LNBH25", "13/18 V • 22 kHz|DiSEqC 2.0 • I2C", "pwr"),
 "JD": blk(2, 50, 26, bh, "J7 SMA 18 GHz", "Input D|2–12 GHz", "con"),
 "D1": blk(34, 50, 28, bh, "LNAs", "HMC8410 (2–8)|ADL8107 (8–12)"),
 "D2": blk(68, 50, 30, bh, "Filter bank", "2×ADRF5040 SP4T|2–4/4–6/6–9/9–12"),
 "D3": blk(104, 50, 28, bh, "Mixer / bypass", "LTC5552 → 1.5 GHz IF|ADRF5024 bypass 2–6"),
 "D4": blk(138, 50, 24, bh, "IF filter + amp", "1–2 GHz BPF|ADL5611"),
 "LO": blk(104, 30, 28, 12, "LO synthesizer", "LMX2595|4.5–10.5 GHz", "lo"),
 "REF": blk(138, 28, 30, 14, "10 MHz reference", "SiT5356 TCXO|ext ref in J8|buffer → J9 out", "lo"),
 "SW": blk(172, 92, 26, 30, "Output SP4T", "ADRF5040|A / B / C / D"),
 "OUT": blk(206, 100, 24, bh, "J10 SMA", "RF OUT", "con"),
 "SDR": blk(206, 72, 26, 16, "bladeRF 2.0", "micro xA4|(external)", "ext"),
 "PC": blk(240, 72, 26, 16, "Laptop", "Skybox Recon|Win / Linux / Android", "ext"),
 "MCU": blk(206, 36, 30, 20, "ESP32-S3", "USB-C CDC • Wi-Fi/BLE|I2C / SPI / GPIO|speaker + 3.5 mm out", "ctl"),
 "PWR": blk(206, 10, 60, 18, "Power", "XT60 9–16 V / USB-C PD 9–12 V|reverse prot. + eFuse → bucks → LT3045 LDOs|per-path load switches • INA226", "pwr"),
}
wires = [("JA", "A1"), ("A1", "A2"), ("A2", "SW", "A"), ("JB", "B1"), ("B1", "B2"), ("B2", "SW", "B"),
         ("JC", "C1"), ("C1", "C2"), ("C2", "SW", "C"), ("LNB", "JC", "DC + 22 kHz", "pwr"),
         ("JD", "D1"), ("D1", "D2"), ("D2", "D3"), ("D3", "D4"), ("D4", "SW", "D"),
         ("LO", "D3", "LO", "lo"), ("REF", "LO", "10 MHz", "lo"), ("REF", "SDR", "10 MHz out", "lo"),
         ("SW", "OUT"), ("OUT", "SDR", "SMA cable"), ("SDR", "PC", "USB 3"), ("MCU", "PC", "USB-C / Wi-Fi", "ctl"),
         ("MCU", "SW", "ctl", "ctl"), ("PWR", "MCU", "3.3 V", "pwr")]
S += [Diagram(268, 160, blocks, wires),
      P("Only one RF path is powered at a time (load switches), which saves power and isolates paths. The output SP4T feeds one SMA cable to the digitizer. All LO/reference and microwave parts sit under shield cans.", SM)]

# ---------------- 3-7. functional schematic sheets ----------------
def sheet(num, title, blocks, wires, nets, note):
    out = [PageBreak(), P(f"{num}. Functional schematic — {title}", H1), Diagram(268, 98, blocks, wires),
           Spacer(1, 2 * mm), P(note, SM), Spacer(1, 2 * mm)]
    out.append(table([["Net", "From (part : function)", "To (part : function)", "Design notes"]] + nets, [32, 70, 70, 96]))
    return out

# Sheet 1 Power
b = {"BAT": blk(2, 74, 26, 14, "J1 XT60", "9–16 V battery|or 13.8 V PSU", "con"),
     "USB": blk(2, 50, 26, 14, "J2 USB-C", "STUSB4500|PD 12 V / 9 V", "con"),
     "F": blk(34, 74, 22, 14, "F1 3 A", "fuse", "pwr"),
     "RP": blk(62, 62, 30, 20, "LTC4359 + Q1/Q2", "reverse protect|+ battery/USB OR-ing", "pwr"),
     "EF": blk(98, 62, 26, 20, "TPS26600", "eFuse|OVP 17 V • 2 A", "pwr"),
     "VIN": blk(130, 62, 24, 20, "VIN_PROT", "9–16 V bus|INA226 shunt", "pwr"),
     "B1": blk(162, 78, 30, 14, "LMR33630 #1", "→ 5.6 V", "pwr"),
     "B2": blk(162, 52, 30, 14, "LMR33630 #2", "→ 3.8 V", "pwr"),
     "L5": blk(200, 82, 34, 12, "LT3045 ×2 → 5.0 V", "+5V_RF_A / +5V_RF_B", "pwr"),
     "L3": blk(200, 64, 34, 12, "LT3045 ×2 → 3.3 V", "+3V3_LO / +3V3_MIX", "pwr"),
     "LD": blk(200, 46, 34, 12, "TLV755 → 3.3 V", "+3V3_DIG", "pwr"),
     "NEG": blk(200, 28, 34, 12, "LTC3260 (DNP?)", "-3V3_SW if needed", "pwr"),
     "LS": blk(240, 64, 26, 30, "TPS22918 ×5", "path A/B/C/D/LO|enables from MCU", "pwr"),
     "LNB": blk(130, 28, 30, 14, "→ LNBH25 VIN", "direct from VIN_PROT", "pwr")}
w = [("BAT", "F"), ("F", "RP", "", "pwr"), ("USB", "RP", "VBUS 9–12 V", "pwr"), ("RP", "EF", "", "pwr"), ("EF", "VIN", "", "pwr"),
     ("VIN", "B1", "", "pwr"), ("VIN", "B2", "", "pwr"), ("VIN", "LNB", "", "pwr"), ("B1", "L5", "", "pwr"), ("B2", "L3", "", "pwr"),
     ("B2", "LD", "", "pwr"), ("B2", "NEG", "", "pwr"), ("L5", "LS", "", "pwr"), ("L3", "LS", "", "pwr")]
w = [x if len(x) == 4 else (x[0], x[1], x[2] if len(x) > 2 else "", "pwr") for x in w]
S += [NextPageTemplate("land")] + sheet(3, "Sheet 1: power input and regulation", b, w, [
    ["VIN_BAT", "J1 : battery +", "F1 → U2 LTC4359 (Q1)", "Wire gauge 18 AWG; keep loop small"],
    ["VBUS", "J2 USB-C VBUS (via U1 STUSB4500)", "Q2 OR-ing → VIN_PROT", "STUSB4500 NVM: PDO2 9 V, PDO3 12 V, min 1.5 A"],
    ["VIN_PROT", "U3 TPS26600 OUT", "U4, U5, U13 LNBH25 VIN, U12 INA226", "OVP 17 V protects LNBH25 (16 V max)"],
    ["+5V6_PRE / +3V8_PRE", "U4 / U5 SW node + LC", "LT3045 inputs", "Bucks at 400 kHz with spread spectrum; pi-filter on outputs; place away from RF"],
    ["+5V_RF_A/B", "U6/U7 LT3045 OUT", "Load switches → LNAs, ADL5611", "Separate LDOs for low-band and microwave paths"],
    ["+3V3_LO / +3V3_MIX", "U8/U9 LT3045 OUT", "U22 LMX2595, U21 LTC5552, Y1, U26", "Star-ground at LMX2595; heavy decoupling per datasheet"],
    ["+3V3_DIG", "U10 TLV755 OUT", "U27 ESP32-S3, sensors, audio", "Keep digital return separate from RF ground pour (single stitch point)"],
    ["EN_PATH_A..D, EN_LO", "U27 GPIO", "U31–U35 TPS22918 ON", "Default OFF at reset (pull-downs)"]],
    "Accepts any 9–16 V source (LiFePO4 4S, 13.8 V station supply, 12 V vehicle) or a USB-C PD charger/power bank at 9 or 12 V, so the unit can be powered anywhere in the world. A plain 5 V USB supply will run the MCU only (RF disabled) — the LNB needs ≥ 8 V into the LNBH25.")

# Sheet 2 LNB
b = {"VIN": blk(2, 70, 28, 14, "VIN_PROT", "9–16 V", "pwr"),
     "LNBH": blk(40, 60, 36, 28, "U13 LNBH25PQR", "boost (L1, D1) • 13/18 V|22 kHz tone • DiSEqC 2.0|I2C addr per ADDR pin|over-current flag", "pwr"),
     "TVS": blk(86, 66, 26, 14, "D2 SMBJ20A", "TVS", "pwr"),
     "BT": blk(122, 60, 30, 28, "Bias-T", "L2 choke (DC + 22 kHz)|C1 100 pF C0G DC block|75 Ω line to J3", "rf"),
     "J3": blk(122, 30, 30, 14, "J3 F-type 75 Ω", "to LNB coax", "con"),
     "FL": blk(162, 66, 30, 14, "FL3 BPF", "950–2150 MHz"),
     "AMP": blk(200, 66, 28, 14, "U14 ADL5611", "+22 dB"),
     "OUT": blk(236, 66, 28, 14, "→ U25 RF3", "path C to output SP4T"),
     "MCU": blk(40, 22, 36, 16, "U27 ESP32-S3", "I2C0 SDA/SCL • IRQ", "ctl")}
w = [("VIN", "LNBH", "", "pwr"), ("LNBH", "TVS", "VLNB", "pwr"), ("TVS", "BT", "", "pwr"), ("BT", "J3", "DC+RF", "sig"),
     ("BT", "FL", "RF only"), ("FL", "AMP"), ("AMP", "OUT"), ("MCU", "LNBH", "I2C", "ctl")]
S += sheet(4, "Sheet 2: dish LNB input (C/Ku/Ka LNB IF) with 13/18 V and 22 kHz", b, w, [
    ["VLNB", "U13 VOUT", "D2 TVS, L2 choke → J3 centre pin", "13 V = vertical/right, 18 V = horizontal/left; 22 kHz on = Ku high band"],
    ["LNB_RF", "J3 centre (via C1 DC block)", "FL3 → U14 → U25 RF3", "75→50 Ω mismatch accepted (~0.2 dB); keep the bias-T stub short"],
    ["I2C0_SDA/SCL", "U27 GPIO8/GPIO9 (suggested)", "U13, U12, U28", "4.7 kΩ pull-ups to +3V3_DIG"],
    ["LNB_FLT", "U13 fault output", "U27 GPIO (IRQ)", "Short-circuit / over-temperature flag shown in the app"],
    ["DSQIN", "Not used", "-", "DiSEqC 2.0 receive is optional; route to test pad"]],
    "The RX-1 does the polarization and band switching itself: Skybox Recon sends the band/polarization over USB and the ESP32 sets LNBH25 over I2C. No external LNB power inserter is needed. A C-band LNB uses 13/18 V only (no 22 kHz); a universal Ku LNB uses 13/18 V and 22 kHz.")

# Sheet 3 A/B
b = {"JA": blk(2, 70, 24, 14, "J4 SMA", "1–1000 MHz", "con"), "LA": blk(32, 70, 26, 14, "D3 limiter", "CLA4609"),
     "NA": blk(64, 70, 34, 14, "FM notch / bypass", "SW1–SW2 + NSBP-108+"), "AA": blk(104, 70, 28, 14, "U15 SPF5189Z", "LNA"),
     "FA": blk(138, 70, 28, 14, "FL2 LFCN-1000+", "LPF 1 GHz"), "OA": blk(236, 70, 28, 14, "→ U25 RF1", "path A"),
     "JB": blk(2, 36, 24, 14, "J5 SMA", "L-band", "con"), "BT": blk(32, 16, 30, 14, "U36 TPS2553", "bias-T 5/3.3 V 100 mA", "pwr"),
     "LB": blk(32, 46, 26, 14, "D4 limiter", "CLA4609"), "FB": blk(64, 46, 34, 14, "FL4 BPF / bypass", "1.45–1.7 GHz"),
     "AB": blk(104, 46, 28, 14, "U16 SPF5189Z", "LNA"), "OB": blk(236, 46, 28, 14, "→ U25 RF2", "path B")}
w = [("JA", "LA"), ("LA", "NA"), ("NA", "AA"), ("AA", "FA"), ("FA", "OA"), ("JB", "LB"), ("LB", "FB"), ("FB", "AB"), ("AB", "OB"),
     ("BT", "JB", "DC via choke", "pwr")]
S += sheet(5, "Sheet 3: input A (below 1 GHz) and input B (L-band)", b, w, [
    ["RFA_IN", "J4", "D3 → SW1", "Limiter at the connector; ESD-rated"],
    ["RFA_NOTCH", "SW1/SW2 (GPIO FM_NOTCH_EN)", "FL1 or through path", "Switch the notch in when strong local FM is present"],
    ["RFA_OUT", "FL2", "U25 RF1", "50 Ω CPWG"],
    ["RFB_IN", "J5 (+ DC from U36 via choke)", "D4 → FL4 / bypass", "Bias for active GNSS / Inmarsat / L-band patch antennas; off by default"],
    ["RFB_OUT", "U16", "U25 RF2", "-"],
    ["EN_BIAS_B, BIAS_SEL", "U27 GPIO", "U36 EN, 5 V/3.3 V select", "Current-limit fault → U27 GPIO"]],
    "Input A covers HF-to-UHF (weather satellites at 137 MHz, ADS-B 1090 MHz is in path B or A). Input B covers L-band satellites (Inmarsat, GNSS, HRPT 1.7 GHz with bypass).")

# Sheet 4 microwave
b = {"JD": blk(2, 70, 24, 14, "J7 SMA", "2–12 GHz", "con"), "LN1": blk(32, 78, 28, 12, "U17 HMC8410", "2–8 GHz LNA"),
     "LN2": blk(32, 60, 28, 12, "U18 ADL8107", "8–12 GHz LNA"), "S1": blk(66, 66, 24, 22, "U19 SP4T", "filter bank in"),
     "FB": blk(96, 62, 30, 30, "FL5–FL8", "2–4 GHz|4–6 GHz|6–9 GHz|9–12 GHz"), "S2": blk(132, 66, 24, 22, "U20 SP4T", "filter bank out"),
     "BY": blk(162, 82, 28, 12, "U23 ADRF5024", "bypass 2–6 GHz"), "MX": blk(162, 60, 28, 14, "U21 LTC5552", "mixer 6–12 GHz"),
     "IF": blk(198, 60, 30, 14, "FL9 + U24", "IF 1–2 GHz + ADL5611"), "O": blk(236, 70, 28, 14, "→ U25 RF4", "path D"),
     "LO": blk(162, 28, 28, 16, "U22 LMX2595", "LO 4.5–10.5 GHz|SPI", "lo"), "RF": blk(110, 26, 40, 20, "Y1 SiT5356 + U37 + U26", "10 MHz TCXO / ext ref (J8)|buffer → LO + J9 ref out", "lo"),
     "MCU": blk(198, 24, 30, 16, "U27 ESP32-S3", "SPI • GPIO", "ctl")}
w = [("JD", "LN1"), ("JD", "LN2"), ("LN1", "S1"), ("LN2", "S1"), ("S1", "FB"), ("FB", "S2"), ("S2", "BY"), ("S2", "MX"),
     ("MX", "IF"), ("IF", "O"), ("BY", "O"), ("LO", "MX", "LO", "lo"), ("RF", "LO", "10 MHz", "lo"), ("MCU", "LO", "SPI", "ctl")]
S += sheet(6, "Sheet 4: 2–12 GHz microwave path, LO and 10 MHz reference", b, w, [
    ["RFD_IN", "J7", "Splitter/SPDT → U17 or U18", "Design house to choose: wideband SPDT ahead of the LNAs (preferred) or a diplexer"],
    ["FB_SEL[1:0]", "U27 GPIO", "U19, U20 V1/V2", "Both switches driven by the same lines so in/out track"],
    ["MIX_RF / MIX_IF", "U20 → U21 RF; U21 IF → FL9", "U24 → U25 RF4", "Low-side LO: LO = RF − 1.5 GHz"],
    ["BYP_SEL", "U27 GPIO", "U23", "2–6 GHz goes straight to the digitizer (it tunes up to 6 GHz)"],
    ["LO_P/LO_N", "U22 RFOUTA", "U21 LO input", "Use the differential or single-ended LO input per datasheet; 50 Ω, shielded"],
    ["SPI_LMX (SCK/SDI/CS/MUXOUT)", "U27 SPI2", "U22", "MUXOUT = lock detect → shown in the app"],
    ["REF_10M", "Y1 or J8 via U37", "U26 → U22 OSCin, J9", "J9 feeds the digitizer's ref input where supported, so LO and digitizer share one clock"]],
    "Microwave layout rules: RO4350B top layer, grounded coplanar waveguide, via fences along every RF line, shield can over LO + mixer, no RF lines crossing splits. The 8–12 GHz section is the critical area — the supplier should simulate the filter-bank transitions or use the filter vendor's evaluation footprint.")

# Sheet 5 control
b = {"MCU": blk(100, 40, 44, 50, "U27 ESP32-S3-WROOM-1", "N16R8 (16 MB flash, 8 MB PSRAM)|USB-OTG → J2 (CDC)|Wi-Fi 2.4 GHz / BLE 5|I2C0 • SPI2 • I2S0 • GPIO", "ctl"),
     "USB": blk(4, 72, 34, 14, "J2 USB-C + U30 ESD", "D+/D− to ESP32", "con"),
     "I2C": blk(4, 46, 40, 20, "I2C0 bus", "U13 LNBH25 • U12 INA226|U28 TMP117 • U1 STUSB4500|J12 OLED (opt.)", "ctl"),
     "SPI": blk(160, 74, 40, 14, "SPI2", "U22 LMX2595", "ctl"),
     "GP": blk(160, 46, 52, 22, "GPIO (outputs default LOW)", "SW_SEL[1:0] (U25) • FB_SEL[1:0]|BYP_SEL • FM_NOTCH • EN_PATH_A..D|EN_LO • EN_BIAS_B • BIAS_SEL", "ctl"),
     "I2S": blk(160, 16, 52, 18, "I2S0", "U29 MAX98357A → LS1 speaker|U38 PCM5102A → J11 3.5 mm", "ctl"),
     "UI": blk(4, 18, 40, 16, "UI", "LED1 WS2812 • SW3 reset|SW4 boot • SW5 mode", "ctl")}
w = [("USB", "MCU", "USB", "ctl"), ("MCU", "I2C", "", "ctl"), ("MCU", "SPI", "", "ctl"), ("MCU", "GP", "", "ctl"), ("MCU", "I2S", "", "ctl"), ("MCU", "UI", "", "ctl")]
S += sheet(7, "Sheet 5: control (ESP32-S3), audio and user interface", b, w, [
    ["USB_D+/D−", "J2", "U27 GPIO19/20 (native USB)", "90 Ω differential; U30 ESD at connector"],
    ["I2C0", "U27", "U1, U12, U13, U28, J12", "100/400 kHz; address map fixed by the design house and listed on the schematic"],
    ["SPI2", "U27", "U22 LMX2595", "Keep SPI lines away from the LO; series 33 Ω"],
    ["SW_SEL[1:0]", "U27", "U25 output SP4T", "00=A 01=B 10=C 11=D"],
    ["I2S_BCLK/LRCK/DOUT", "U27", "U29 + U38", "Finder beep pitch follows signal level (same as the app's finder tone)"],
    ["STRAP / BOOT", "SW4", "GPIO0", "Firmware update over USB without a programmer"]],
    "Firmware (by the project, not the supplier): a simple text command set over USB-CDC and Wi-Fi, e.g. PATH D; LO 10.25G; LNB 18V TONE ON; which Skybox Recon will drive from its Tuning and Band panels.")

# ---------------- 8+ portrait sections ----------------
S += [NextPageTemplate("port"), PageBreak(), P("8. PCB stack-up and layout requirements", H1)]
S += [table([["Layer", "Material / thickness", "Use"],
             ["L1 (top)", "Copper 1 oz on Rogers RO4350B 0.254 mm (10 mil)", "All RF routing (50 Ω grounded CPWG), RF parts"],
             ["L2", "Solid ground", "RF reference plane — no splits under RF"],
             ["Core", "FR-4 (Tg 170) to make ~1.6 mm total", "-"],
             ["L3", "Power planes / pours", "Rails from section 3"],
             ["L4 (bottom)", "Signals, digital, power parts", "MCU, bucks, audio, connectors"]], [26, 82, 74])]
S += bullets(["Board ~150 × 95 mm, sized to slide into a Hammond 1455N-series extruded aluminium case with SMA/F connectors on the end panels.",
              "Surface finish ENIG; via-in-pad filled and capped under QFN/LGA thermal pads; stitching vias every ~λ/10 at 12 GHz (≈ 1.2 mm) along RF lines and shield frames.",
              "Shield cans over: (1) LO + mixer, (2) microwave LNAs + filter bank, (3) LNBH25 boost converter, (4) buck converters.",
              "Separate the low-band (A/B/C) and microwave (D) sections physically; the output SP4T sits at the junction.",
              "Impedance coupons on the panel; supplier to provide the TDR report. 75 Ω section only between J3 and the bias-T."])
S += [P("Interfaces and connectors", H2)]
S += [table([["Ref", "Connector", "Signal", "Notes"],
             ["J1", "XT60", "9–16 V DC in", "Reverse-polarity protected"], ["J2", "USB-C", "PD power + USB data", "To laptop or charger"],
             ["J3", "F-type 75 Ω", "Dish LNB IF + LNB power", "13/18 V, 22 kHz, up to 0.5 A"],
             ["J4 / J5", "SMA", "Input A / Input B", "B has switchable antenna bias"], ["J7", "SMA (18 GHz)", "Input D 2–12 GHz", "Use a precision SMA"],
             ["J8 / J9", "SMA", "10 MHz ref in / out", "GPSDO input; out to digitizer"], ["J10", "SMA", "RF out to digitizer", "One cable to bladeRF RX1"],
             ["J11", "3.5 mm TRS", "Audio line/headphone out", "Optional"], ["J12", "4-pin header", "I2C OLED", "Optional"]], [16, 30, 60, 76])]

S += [PageBreak(), P("9. Audio and video output — answer and options", H1)]
S += [P("<b>Was audio or video out included?</b> Not in the earlier design. RX-1 is an RF front-end: it hands raw IQ samples to the laptop, and Skybox Recon already streams the decoded transport stream over the network (AV Stream tab) to VLC/Kodi on any device. Rev A now adds <b>audio</b> (speaker + 3.5 mm out, sheet 5) mainly for the satellite-finder beep, which is very useful at the dish when you cannot see the laptop.", B)]
S += [P("<b>Video (HDMI) is a separate job.</b> Decoding DVB-S/S2 to pictures needs a demodulator chip plus a video decoder, which would double the board's complexity and cost and bring licensing questions for some codecs. The practical route is an optional media module:", B)]
S += [table([["Option", "What it is", "Effort"],
             ["1. Software (now)", "Laptop decodes; Skybox Recon AV Stream sends the stream to TVs/phones on the LAN", "Already works"],
             ["2. Media module (phase 2)", "Raspberry Pi 5 (HDMI + audio + Wi-Fi) with an off-the-shelf USB DVB-S2/S2X tuner, fed from a second output of J3 via a splitter; runs Skybox Recon headless + Kodi/VLC", "Low — no custom RF"],
             ["3. Custom demod board", "Dedicated DVB-S2X demodulator IC + HDMI SoC on a new PCB", "High — only for volume production"]], [36, 112, 34])]
S += [P("10. Test and acceptance (prototype)", H2)]
S += bullets(["Power: all rails within ±3 %; current at idle and per path; eFuse trips at > 17 V and > 2 A; reverse polarity survives.",
              "LNB: 13.0/18.0 V ±0.3 V at 300 mA; 22 kHz 0.65 Vpp ±0.1 V; short-circuit flag works.",
              "RF gain/NF per path with a signal generator and noise source (supplier: gain ±3 dB of target is acceptable at prototype).",
              "LO lock at 4.5, 7.5 and 10.5 GHz; reference switching internal/external.",
              "USB enumerates as a CDC serial port on Windows, Linux and Android (OTG); every I2C/SPI device answers.",
              "The project team does the final over-the-air tests with Skybox Recon (C-band and Ku dishes, L-band, 137 MHz)."])
S += [P("11. Compliance — global market", H2)]
S += [P("Receive-only design (no intentional transmitter except the pre-certified ESP32-S3 module). Plan for: CE (RED, because of Wi-Fi/BLE) and UKCA; FCC Part 15B plus the module's modular grant; ISED (Canada); RCM (Australia/NZ); MIC/TELEC (Japan) and other regions via the module's existing certificates; RoHS and REACH declarations; WEEE marking. Battery packs must carry UN38.3 and IEC 62133 test reports for shipping. The 77 Wh pack stays under the 100 Wh airline carry-on limit. The ESP32-S3-WROOM-1U (external-antenna) version is an option if the metal case blocks Wi-Fi.", B)]

S += [PageBreak(), P("12. Where to send this package", H1)]
S += [table([["Supplier", "What to ask them for", "Why this one"],
             ["PCBWay", "Full design service: schematic + layout + prototype + assembly (upload this PDF and the BOM as a 'PCB Design' request)", "Takes a project from a concept or block diagram through schematic and layout, and supplies the schematic/layout files if you ask (extra cost)"],
             ["JLCPCB", "Layout service from your schematic, then fab + assembly (best value if the schematic is captured first, e.g. by PCBWay or a freelancer)", "Layout service lists RF and high-speed boards and supports KiCad, Altium and EasyEDA"],
             ["AtlasPCB (or a similar RF specialist)", "Quote fabrication of the hybrid Rogers RO4350B/FR-4 stack and an RF layout review", "RF/microwave material specialist — useful as a second opinion on the 2–12 GHz section"]], [30, 76, 76])]
S += [P("How to submit", H2)]
S += bullets(["Send all three files: this PDF, RX-1_BOM_RevA.xlsx, and README.txt. Paste the 'RFQ asks' sheet into the request form.",
              "Ask every supplier to quote three options: design only; design + 5 prototypes; design + 25 units. Ask them to name the CAD tool and to list part substitutions.",
              "Insist on receiving the native schematic and layout files (not only Gerbers) so you own the design and can move it to another factory.",
              "Ask for an NDA if you want one before sending; the project can still choose to open-source the hardware later.",
              "Expect a schematic review cycle: the supplier will send PDF schematics for you to approve before layout starts — check them against sections 3–7."])
S += [P("Important limits of this package", H2)]
S += [P("This is a functional design for quoting, made without bench testing. Pin numbers, passive values, matching networks and some filter part numbers (marked <b>Verify</b> in the BOM) must be completed by the design house from the manufacturers' datasheets and reference designs. Prices and lead times are left blank for suppliers to fill in.", B)]

doc.build(S)
print("ok", out)
