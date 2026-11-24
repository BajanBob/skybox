/* Skybox Recon mobile engine -- JavaScript port of the offline parts of skybox.py.
 * Pure functions, no DOM: usable in the app and under Node for tests. */
(function (root) {
  "use strict";

  const VERSION = "6.0.0";
  const CODENAME = "Beryl";

  // ---------------------------------------------------------------- checksums
  const CRC_TABLE = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c >>> 0;
    }
    return t;
  })();

  function crc32(bytes) {
    let c = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  function crc16xmodem(bytes) {
    let crc = 0;
    for (let i = 0; i < bytes.length; i++) {
      crc ^= bytes[i] << 8;
      for (let k = 0; k < 8; k++) crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
    }
    return crc;
  }

  function sum16(bytes) {
    let s = 0;
    for (let i = 0; i < bytes.length; i++) s += bytes[i];
    return s & 0xffff;
  }

  // ---------------------------------------------------------------- helpers
  const hex2 = (x) => x.toString(16).padStart(2, "0");
  const hex8 = (x) => (x >>> 0).toString(16).padStart(8, "0");
  const ascii = (s) => Uint8Array.from(s, (ch) => ch.charCodeAt(0));

  function hexdump(b, base = 0) {
    const out = [];
    for (let i = 0; i < b.length; i += 16) {
      const c = b.subarray(i, i + 16);
      const hexs = Array.from(c, hex2).join(" ");
      const txt = Array.from(c, (x) => (x >= 32 && x < 127 ? String.fromCharCode(x) : ".")).join("");
      out.push(`${hex8(base + i)}  ${hexs.padEnd(47)}  ${txt}`);
    }
    return out.join("\n");
  }

  function parseHex(text) {
    const clean = String(text).replace(/0x/gi, "").replace(/[\s,:]/g, "");
    if (clean.length % 2 || /[^0-9a-f]/i.test(clean)) throw new Error("payload must be hex bytes, e.g. 00 10 ff");
    const out = new Uint8Array(clean.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(clean.substr(i * 2, 2), 16);
    return out;
  }

  // ---------------------------------------------------------------- IPL frames
  // Frame: A5 5A | len:u16le | cmd:u8 | payload | crc32(body):u32le
  function encodeFrame(cmd, payload = new Uint8Array(0)) {
    const body = new Uint8Array(1 + payload.length);
    body[0] = cmd & 0xff;
    body.set(payload, 1);
    const out = new Uint8Array(4 + body.length + 4);
    out[0] = 0xa5; out[1] = 0x5a;
    out[2] = body.length & 0xff; out[3] = (body.length >> 8) & 0xff;
    out.set(body, 4);
    const c = crc32(body);
    out.set([c & 0xff, (c >>> 8) & 0xff, (c >>> 16) & 0xff, (c >>> 24) & 0xff], 4 + body.length);
    return out;
  }

  function decodeFrame(buf) {
    let i = -1;
    for (let k = 0; k + 1 < buf.length; k++) if (buf[k] === 0xa5 && buf[k + 1] === 0x5a) { i = k; break; }
    if (i < 0 || buf.length < i + 6) return null;
    const ln = buf[i + 2] | (buf[i + 3] << 8);
    if (ln === 0 || buf.length < i + 4 + ln + 4) return null;
    const body = buf.subarray(i + 4, i + 4 + ln);
    const p = i + 4 + ln;
    const crc = (buf[p] | (buf[p + 1] << 8) | (buf[p + 2] << 16) | (buf[p + 3] << 24)) >>> 0;
    if (crc32(body) !== crc) return null;
    return { cmd: body[0], payload: body.slice(1) };
  }

  // ---------------------------------------------------------------- firmware
  const MAGICS = [
    [[0x27, 0x05, 0x19, 0x56], "uImage"],
    [[0x1f, 0x8b], "gzip"],
    [[0xfd, 0x37, 0x7a, 0x58, 0x5a], "xz"],
    [[0x28, 0xb5, 0x2f, 0xfd], "zstd"],
    [Array.from(ascii("hsqs")), "squashfs-le"],
    [Array.from(ascii("sqsh")), "squashfs-be"],
    [[0x85, 0x19], "jffs2"],
    [[0x31, 0x18, 0x10, 0x06], "ubifs"],
    [[0xd0, 0x0d, 0xfe, 0xed], "fdt"],
    [Array.from(ascii("ALi")), "ali-magic"],
  ];

  function entropy(b) {
    if (!b.length) return 0;
    const counts = new Uint32Array(256);
    for (let i = 0; i < b.length; i++) counts[b[i]]++;
    let e = 0;
    for (let v = 0; v < 256; v++) if (counts[v]) { const p = counts[v] / b.length; e -= p * Math.log2(p); }
    return e;
  }

  function entropyMap(data, win = 4096) {
    const lines = ["entropy map (0.0 = zeros/text, 8.0 = compressed or encrypted)"];
    const ramp = " .:-=+*#%@";
    for (let off = 0; off < data.length; off += win * 16) {
      const row = [];
      for (let i = 0; i < win * 16; i += win) row.push(entropy(data.subarray(off + i, off + i + win)));
      const bar = row.map((e) => ramp[Math.min(9, Math.floor(e / 0.9))]).join("");
      const avg = row.reduce((a, b) => a + b, 0) / row.length;
      lines.push(`${hex8(off)} |${bar}| ${avg.toFixed(2)}`);
    }
    return lines;
  }

  function findMagics(data, limit = 2000) {
    const hits = [];
    for (const [m, name] of MAGICS) {
      outer: for (let i = 0; i + m.length <= data.length; i++) {
        if (data[i] !== m[0]) continue;
        for (let k = 1; k < m.length; k++) if (data[i + k] !== m[k]) continue outer;
        hits.push({ name, offset: i });
        if (hits.length >= limit) return { hits, truncated: true };
      }
    }
    return { hits, truncated: false };
  }

  function partitionCandidates(data, limit = 500) {
    const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
    const out = [];
    for (let i = 0; i < data.length - 12; i += 4) {
      const off = dv.getUint32(i, true), size = dv.getUint32(i + 4, true);
      if (off >= 0x10000 && off < data.length && size >= 0x1000 && size < data.length && off + size <= data.length) {
        out.push({ at: i, off, size, crc: dv.getUint32(i + 8, true) });
        if (out.length >= limit) return { records: out, truncated: true };
      }
    }
    return { records: out, truncated: false };
  }

  function analyzeFirmware(data, name = "image") {
    const lines = [`${name}: ${data.length} bytes  crc32=${hex8(crc32(data))}`];
    lines.push(hexdump(data.subarray(0, 256)));
    lines.push(...entropyMap(data));
    const { hits, truncated } = findMagics(data);
    lines.push("", `magic signatures: ${hits.length}${truncated ? " (list truncated)" : ""}`);
    for (const h of hits.slice(0, 300)) {
      lines.push(`  ${h.name.padEnd(14)} @ 0x${hex8(h.offset)}  ${hexdump(data.subarray(h.offset, h.offset + 16), h.offset)}`);
    }
    if (hits.length > 300) lines.push(`  ... ${hits.length - 300} more`);
    const pc = partitionCandidates(data);
    lines.push("", `candidate partition records (offset, size, crc): ${pc.records.length}${pc.truncated ? "+" : ""}`);
    for (const r of pc.records.slice(0, 200)) {
      lines.push(`  0x${hex8(r.at)}: off=0x${hex8(r.off)} size=0x${hex8(r.size)} crc=0x${hex8(r.crc)}`);
    }
    if (pc.records.length > 200) lines.push(`  ... ${pc.records.length - 200} more`);
    return { text: lines.join("\n"), hits, partitions: pc.records };
  }

  // ---------------------------------------------------------------- DVB tuning
  const MODULATIONS = {
    DVBS: ["QPSK"],
    DVBS2: ["QPSK", "8PSK", "16APSK", "32APSK"],
    DVBS2X: ["QPSK", "8PSK", "8APSK-L", "16APSK", "16APSK-L", "32APSK", "32APSK-L", "64APSK", "64APSK-L",
      "128APSK", "256APSK", "256APSK-L", "pi/2-BPSK"],
  };
  const V5_MOD = { auto: "QAM/AUTO", QPSK: "QPSK", "8PSK": "PSK/8", "16APSK": "APSK/16", "32APSK": "APSK/32" };
  const V5_POL = { H: "HORIZONTAL", V: "VERTICAL", L: "LEFT", R: "RIGHT" };
  const V5_ROLLOFF = { auto: "AUTO", "0.35": "35", "0.25": "25", "0.20": "20", "0.15": "15", "0.10": "10", "0.05": "5" };
  const LNBS = { UNIVERSAL: [9750, 10600, 11700], ENHANCED: [9750], STANDARD: [10000], L10700: [10700],
    L10750: [10750], L11300: [11300], DBS: [11250], "C-BAND": [5150] };
  const PLS_MODES = ["ROOT", "GOLD", "COMBO"];

  function lnbFor(rfMHz, lnb) {
    const p = LNBS[lnb] || LNBS.UNIVERSAL;
    return p.length === 3 && rfMHz >= p[2] ? { lof: p[1], tone: true } : { lof: p[0], tone: false };
  }
  const rfToIf = (rf, lof) => (lof < 6000 ? lof - rf : rf - lof);
  const voltageFor = (pol) => (pol === "H" || pol === "L" ? 18 : 13);
  function streamId(isi, pls, mode) {
    if ((isi === "" || isi == null) && (pls === "" || pls == null)) return null;
    return (((PLS_MODES.indexOf(mode) & 3) << 26) >>> 0) + (((+pls || 0) & 0x3ffff) * 256) + ((+isi || 0) & 0xff);
  }

  // o: freq (RF kHz), sr, delsys, mod, fec, pol, rolloff, pilot, inversion, mis, pls, plsMode, diseqc, service
  function tuneConf(o) {
    if (o.mod !== "auto" && !(MODULATIONS[o.delsys] || []).includes(o.mod)) throw new Error(`${o.mod} is not a ${o.delsys} modulation`);
    const head = V5_MOD[o.mod] ? "" : `# requested modulation ${o.mod}: written as QAM/AUTO (demodulator detects it)\n`;
    const lines = [`[${o.service}]`, `\tDELIVERY_SYSTEM = ${o.delsys}`, `\tFREQUENCY = ${o.freq}`,
      `\tSYMBOL_RATE = ${o.sr}`, `\tINNER_FEC = ${o.fec === "auto" ? "AUTO" : o.fec === "none" ? "NONE" : o.fec}`,
      `\tMODULATION = ${V5_MOD[o.mod] || "QAM/AUTO"}`, `\tPOLARIZATION = ${V5_POL[o.pol]}`,
      `\tINVERSION = ${(o.inversion || "auto").toUpperCase()}`];
    if (o.delsys !== "DVBS") lines.push(`\tROLLOFF = ${V5_ROLLOFF[o.rolloff] || "AUTO"}`, `\tPILOT = ${(o.pilot || "auto").toUpperCase()}`);
    const sid = streamId(o.mis, o.pls, o.plsMode);
    if (sid !== null) lines.push(`\tSTREAM_ID = ${sid}`);
    if (o.diseqc !== "" && o.diseqc != null && o.diseqc !== "none") lines.push(`\tSAT_NUMBER = ${o.diseqc}`);
    return head + lines.join("\n") + "\n";
  }

  function tuneCommand(o) {
    const args = ["dvbv5-zap", "-a", "0", "-f", "0", "-l", o.lnb || "UNIVERSAL", "-c", `${o.service}.conf`, "-t", "600"];
    if (o.diseqc !== "" && o.diseqc != null && o.diseqc !== "none") args.push("-S", o.diseqc);
    args.push("-o", "capture.ts", o.service);
    return args.join(" ");
  }

  // ---------------------------------------------------------------- self-test
  function selfTest() {
    const results = [];
    const check = (name, ok) => results.push({ name, ok: !!ok });
    const v = ascii("123456789");
    check("crc32 vector", crc32(v) === 0xcbf43926);
    check("crc16-xmodem vector", crc16xmodem(v) === 0x31c3);
    check("sum16", sum16(Uint8Array.of(1, 2, 0xff)) === 0x0102);
    check("entropy zero block", entropy(new Uint8Array(4096)) === 0);
    const rnd = new Uint8Array(4096);
    for (let i = 0; i < rnd.length; i++) rnd[i] = (Math.random() * 256) | 0;
    check("entropy random block", entropy(rnd) > 7.5);
    for (const [cmd, payload] of [[0x01, new Uint8Array(0)],
      [0x11, Uint8Array.from([0, 0x10, 0, 0, ...new Array(32).fill(0x41)])]]) {
      const f = decodeFrame(encodeFrame(cmd, payload));
      check(`frame round-trip cmd 0x${hex2(cmd)}`, f && f.cmd === cmd && f.payload.length === payload.length &&
        f.payload.every((x, i) => x === payload[i]));
    }
    const bad = encodeFrame(0x01); bad[bad.length - 1] ^= 0xff;
    check("frame rejects bad crc", decodeFrame(bad) === null);
    const blob = new Uint8Array(0x10000).fill(0xff);
    blob.set(ascii("hsqs"), 0x100);
    blob.set([0x27, 0x05, 0x19, 0x56], 0x2000);
    const { hits } = findMagics(blob);
    check("carver finds squashfs", hits.some((h) => h.name.startsWith("squashfs") && h.offset === 0x100));
    check("carver finds uImage", hits.some((h) => h.name === "uImage" && h.offset === 0x2000));
    return results;
  }

  const api = { VERSION, CODENAME, MODULATIONS, LNBS, lnbFor, rfToIf, voltageFor, streamId, crc32, crc16xmodem, sum16, hexdump, parseHex, encodeFrame, decodeFrame,
    entropy, entropyMap, findMagics, partitionCandidates, analyzeFirmware, tuneConf, tuneCommand, selfTest, hex8 };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SkyboxEngine = api;
})(typeof self !== "undefined" ? self : this);
