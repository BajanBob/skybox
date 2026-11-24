# RX-1 multiband receiver front-end — RFQ package (Rev A draft)

Hardware companion to Skybox Recon: a battery-powered, receive-only RF front-end with four inputs (1–1000 MHz, L-band, dish LNB IF with 13/18 V + 22 kHz, 2–12 GHz) switched to one output for an external digitizer.

`rfq/` — files to send to manufacturers:
- `RX-1_RFQ_Package_RevA.zip` — everything below in one download
- `Letter_PCBWay_…`, `Letter_JLCPCB_…`, `Letter_AtlasPCB_…` — RFQ letters with optional parts list and schematic sheets bound in (fill in the [placeholders] first)
- `RX-1_Design_Package_RevA.pdf` — spec, block diagram, functional schematic sheets 1–5, stack-up, test plan, compliance
- `RX-1_BOM_RevA.xlsx` / `.csv` — BOM, optional parts, power budget, RFQ asks

`scripts/` — Python generators (reportlab, openpyxl, pypdf). Run from the repo root:
`python3 hardware/rx1/scripts/make_bom.py && python3 hardware/rx1/scripts/make_pdf.py && python3 hardware/rx1/scripts/make_letters.py`

Status: functional design for quoting — not pin-accurate and not yet built or tested. Parts marked "Verify" need confirmation by the design house.
