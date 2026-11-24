import csv, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
sys.path.insert(0, "hardware/rx1/scripts")
from bom_data import BOM, HEAD

out = "hardware/rx1/rfq/"
wb = Workbook(); ws = wb.active; ws.title = "BOM"
ws.append(["RX-1 Multiband Receiver Front-End - Bill of Materials - Rev A draft (2026-11-24)"])
ws["A1"].font = Font(bold=True, size=13)
ws.append(["Functional BOM for design-and-quote. Items marked 'Verify' need part confirmation by the design house. Quantities are per board."])
ws.append([])
ws.append(HEAD + ["Unit price (supplier)", "Lead time (supplier)"])
hdr = ws.max_row
fill = PatternFill("solid", fgColor="1F3A5F"); thin = Side(style="thin", color="BBBBBB")
for c in ws[hdr]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = fill
    c.alignment = Alignment(wrap_text=True, vertical="center")
for r in BOM:
    ws.append(list(r) + ["", ""])
    for c in ws[ws.max_row]:
        c.alignment = Alignment(wrap_text=True, vertical="top"); c.border = Border(bottom=thin)
    if str(r[9]).startswith("Yes") or "select" in str(r[9]).lower():
        ws.cell(ws.max_row, 10).fill = PatternFill("solid", fgColor="FFF2CC")
widths = [6,10,5,20,30,48,12,26,22,26,16,16]
for i, w in enumerate(widths):
    ws.column_dimensions[chr(65+i)].width = w
ws.freeze_panes = ws.cell(hdr+1, 1)
ws.auto_filter.ref = f"A{hdr}:L{ws.max_row}"
t = ws.max_row + 2
ws.cell(t, 1, "Total line items"); ws.cell(t, 3, f"=COUNTA(A{hdr+1}:A{t-2})")
ws.cell(t+1, 1, "Total parts (qty)"); ws.cell(t+1, 3, f"=SUM(C{hdr+1}:C{t-2})")

pw = wb.create_sheet("Power budget")
pw.append(["Load","Rail (V)","Current (A, est.)","Power (W)","Note"])
rows = [
 ("ESP32-S3 (Wi-Fi active)",3.3,0.25,"avg; peaks higher"),
 ("LMX2595 LO",3.3,0.30,"only when path D active"),
 ("LTC5552 mixer",3.3,0.15,"only when path D active"),
 ("HMC8410 / ADL8107 LNA",5.0,0.16,"path D"),
 ("SPF5189Z x2",5.0,0.18,"paths A/B"),
 ("ADL5611 x2",5.0,0.18,"paths C / D IF"),
 ("TCXO + buffer",3.3,0.02,""),
 ("Audio amp (beep peak)",5.0,0.10,"intermittent"),
 ("LNB via LNBH25 (18 V, 250 mA)",18.0,0.25,"worst-case LNB; ~85% boost efficiency not included"),
]
for i, (n, v, a, note) in enumerate(rows, start=2):
    pw.append([n, v, a, f"=B{i}*C{i}", note])
n = len(rows) + 1
pw.append(["Sum of loads", "", "", f"=SUM(D2:D{n})", "all paths on (worst case)"])
pw.append(["Regulator losses (est. 25%)", "", "", f"=D{n+1}*0.25", ""])
pw.append(["Total input power (worst)", "", "", f"=D{n+1}+D{n+2}", "per-path load switches cut typical use to ~3-5 W"])
pw.append(["Battery energy (Wh)", "", "", 77, "LiFePO4 4S 12.8 V x 6 Ah"])
pw.append(["Runtime, worst case (h)", "", "", f"=D{n+4}/D{n+3}", ""])
for c in pw[1]: c.font = Font(bold=True, color="FFFFFF"); c.fill = fill
for col, w in zip("ABCDE", [34,9,16,11,48]): pw.column_dimensions[col].width = w
for r in range(2, pw.max_row+1): pw.cell(r, 4).number_format = "0.00"

rq = wb.create_sheet("RFQ asks")
rq.append(["#","Request to supplier"])
asks = [
 "Quote schematic capture + PCB layout from the attached functional design (KiCad or Altium native files + Gerbers + pick-and-place + BOM).",
 "Quote prototype fabrication: 4-layer hybrid stack (RO4350B 0.254 mm top dielectric + FR-4), controlled impedance 50 Ohm CPWG, ENIG.",
 "Quote assembly of 5 and 25 boards, including part sourcing; flag any part with lead time > 8 weeks and propose alternates.",
 "Confirm you can place 0.4 mm-pitch QFN/LGA and 0201 parts, and fit shield frames.",
 "Provide impedance test coupons and a TDR report; X-ray inspection of QFN/LGA RF parts.",
 "State the DFM rules you need (min trace/space, via-in-pad, back-drill) for the 2-12 GHz section.",
 "Confirm RoHS/REACH compliance and provide a declaration; quote CE/FCC pre-scan if offered.",
 "Lead time and price for: design only / design + 5 prototypes / design + 25 units.",
]
for i, a in enumerate(asks, 1): rq.append([i, a])
rq.column_dimensions["B"].width = 120
for c in rq[1]: c.font = Font(bold=True)
wb.save(out + "RX-1_BOM_RevA.xlsx")

with open(out + "RX-1_BOM_RevA.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(HEAD); w.writerows(BOM)
print(len(BOM), "lines,", sum(r[2] for r in BOM), "parts")
