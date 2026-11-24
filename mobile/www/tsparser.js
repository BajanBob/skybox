/* Skybox Recon mobile: MPEG-TS service / PID / satellite discovery.
 * JavaScript port of skybox_recon/ts_parser.py (PAT, PMT, SDT, NIT). */
(function (root) {
  "use strict";

  const VIDEO = { 0x01: "MPEG-1 Video", 0x02: "MPEG-2 Video", 0x10: "MPEG-4 Visual",
    0x1B: "H.264 / AVC", 0x24: "H.265 / HEVC", 0x33: "H.266 / VVC" };
  const AUDIO_ST = { 0x03: "MPEG-1 Audio Layer II", 0x04: "MPEG-2 Audio Layer II", 0x0F: "MPEG-4 AAC-LC",
    0x11: "MPEG-4 AAC-LC", 0x81: "Dolby Digital (AC-3)", 0x87: "Dolby Digital Plus (E-AC-3)",
    0x2D: "MPEG-H Audio (LC profile)" };
  const AUDIO_DESC = { 0x6A: "Dolby Digital (AC-3)", 0x7A: "Dolby Digital Plus (E-AC-3)",
    0x7B: "DTS Digital Surround", 0x7C: "MPEG-4 AAC-LC" };
  const AUDIO_EXT = { 0x15: "Dolby AC-4", 0x0E: "DTS-HD" };
  const SERVICE_TYPES = { 0x01: "TV (SD)", 0x02: "Radio", 0x0A: "Radio (advanced codec)", 0x0C: "Data",
    0x11: "TV (MPEG-2 HD)", 0x16: "TV (H.264 SD)", 0x19: "TV (H.264 HD)", 0x1C: "TV (H.264 3D)",
    0x1F: "TV (HEVC)", 0x20: "TV (HEVC UHD)" };
  const POL = ["H", "V", "L", "R"], MOD = ["auto", "QPSK", "8PSK", "16QAM"];
  const FEC = { 1: "1/2", 2: "2/3", 3: "3/4", 4: "5/6", 5: "7/8", 6: "8/9", 7: "3/5", 8: "4/5", 9: "9/10", 15: "none" };

  const CRC_T = (() => {
    const t = new Uint32Array(256);
    for (let i = 0; i < 256; i++) {
      let c = i << 24;
      for (let k = 0; k < 8; k++) c = c & 0x80000000 ? ((c << 1) ^ 0x04c11db7) : c << 1;
      t[i] = c >>> 0;
    }
    return t;
  })();
  function crc32mpeg2(b) {
    let c = 0xffffffff;
    for (let i = 0; i < b.length; i++) c = ((c << 8) ^ CRC_T[((c >>> 24) ^ b[i]) & 0xff]) >>> 0;
    return c >>> 0;
  }
  function bcd(b, digits) {
    let v = 0;
    for (let i = 0; i < digits; i++) {
      const n = i % 2 === 0 ? b[i >> 1] >> 4 : b[i >> 1] & 15;
      v = v * 10 + (n < 10 ? n : 0);
    }
    return v;
  }
  function dvbText(b) {
    if (!b.length) return "";
    let enc = "latin1", body = b;
    if (b[0] === 0x15) { enc = "utf-8"; body = b.subarray(1); }
    else if (b[0] === 0x10 && b.length >= 3) { enc = "iso-8859-" + b[2]; body = b.subarray(3); }
    else if (b[0] >= 1 && b[0] <= 0x0b) { enc = "iso-8859-" + (b[0] + 4); body = b.subarray(1); }
    else if (b[0] < 0x20) body = b.subarray(1);
    let s;
    try { s = new TextDecoder(enc).decode(body); } catch (_) { s = new TextDecoder("latin1").decode(body); }
    return s.replace(/[\u0000-\u001f\u0080-\u009f]/g, "").trim();
  }
  function* descs(b) {
    let i = 0;
    while (i + 2 <= b.length) { yield [b[i], b.subarray(i + 2, i + 2 + b[i + 1])]; i += 2 + b[i + 1]; }
  }

  function parse(data, maxPackets = 400000) {
    const r = { packets: 0, syncErrors: 0, ccErrors: 0, crcErrors: 0, tsid: null, onid: null,
      networkName: null, services: {}, deliveries: [], pidCounts: {}, scrambledPids: new Set() };
    const buf = {}, cc = {}, pmtPids = {}, seen = new Set();
    let nitPid = 0x10;

    function section(pid, s) {
      if (s.length < 12 || !(s[1] & 0x80)) return;
      if (crc32mpeg2(s) !== 0) { r.crcErrors++; return; }
      const key = [pid, s[0], s[3], s[4], s[5] & 0x3e, s[6]].join(",");
      if (seen.has(key)) return;
      seen.add(key);
      const end = s.length - 4;
      if (pid === 0 && s[0] === 0) {
        r.tsid = (s[3] << 8) | s[4];
        for (let i = 8; i < end; i += 4) {
          const prog = (s[i] << 8) | s[i + 1], p = ((s[i + 2] & 0x1f) << 8) | s[i + 3];
          if (prog === 0) nitPid = p; else pmtPids[p] = prog;
        }
      } else if (pmtPids[pid] !== undefined && s[0] === 2) {
        const prog = (s[3] << 8) | s[4], svc = svcFor(prog);
        svc.pmtPid = pid; svc.pcrPid = ((s[8] & 0x1f) << 8) | s[9];
        const pinfo = ((s[10] & 15) << 8) | s[11];
        for (const [t] of descs(s.subarray(12, 12 + pinfo))) if (t === 0x09) svc.ca = true;
        svc.components = [];
        let i = 12 + pinfo;
        while (i + 5 <= end) {
          const st = s[i], p = ((s[i + 1] & 0x1f) << 8) | s[i + 2], esl = ((s[i + 3] & 15) << 8) | s[i + 4];
          const ds = [...descs(s.subarray(i + 5, i + 5 + esl))];
          i += 5 + esl;
          let lang = null, type = "data", codec = "stream_type 0x" + st.toString(16).padStart(2, "0");
          for (const [t, d] of ds) {
            if ((t === 0x0a || t === 0x56 || t === 0x59) && d.length >= 3 && !lang) lang = String.fromCharCode(d[0], d[1], d[2]);
            if (t === 0x09) svc.ca = true;
          }
          const ext = ds.find(([t, d]) => t === 0x7f && d.length && AUDIO_EXT[d[0]]);
          const ad = ds.find(([t]) => AUDIO_DESC[t]);
          if (VIDEO[st]) { type = "video"; codec = VIDEO[st]; }
          else if (ext) { type = "audio"; codec = AUDIO_EXT[ext[1][0]]; }
          else if (ad) { type = "audio"; codec = AUDIO_DESC[ad[0]]; }
          else if (AUDIO_ST[st]) { type = "audio"; codec = AUDIO_ST[st]; }
          else if (ds.some(([t]) => t === 0x59)) { type = "subtitle"; codec = "DVB subtitles"; }
          else if (ds.some(([t]) => t === 0x56)) { type = "subtitle"; codec = "Teletext"; }
          svc.components.push({ pid: p, type, codec, lang });
        }
      } else if (pid === 0x11 && s[0] === 0x42) {
        r.onid = (s[8] << 8) | s[9];
        let i = 11;
        while (i + 5 <= end) {
          const sid = (s[i] << 8) | s[i + 1], dl = ((s[i + 3] & 15) << 8) | s[i + 4], svc = svcFor(sid);
          if (s[i + 3] & 0x10) svc.freeCA = true;
          for (const [t, d] of descs(s.subarray(i + 5, i + 5 + dl))) {
            if (t === 0x48 && d.length >= 3) {
              const pl = d[1];
              svc.type = SERVICE_TYPES[d[0]] || "type 0x" + d[0].toString(16);
              svc.provider = dvbText(d.subarray(2, 2 + pl));
              svc.name = dvbText(d.subarray(3 + pl, 3 + pl + (d[2 + pl] || 0)));
            }
          }
          i += 5 + dl;
        }
      } else if (pid === nitPid && (s[0] === 0x40 || s[0] === 0x41)) {
        const ndl = ((s[8] & 15) << 8) | s[9];
        for (const [t, d] of descs(s.subarray(10, 10 + ndl))) if (t === 0x40 && s[0] === 0x40) r.networkName = dvbText(d);
        let i = 10 + ndl;
        const tsl = ((s[i] & 15) << 8) | s[i + 1];
        i += 2;
        const stop = Math.min(i + tsl, end);
        while (i + 6 <= stop) {
          const tsid = (s[i] << 8) | s[i + 1], onid = (s[i + 2] << 8) | s[i + 3], dl = ((s[i + 4] & 15) << 8) | s[i + 5];
          for (const [t, d] of descs(s.subarray(i + 6, i + 6 + dl))) {
            if (t === 0x43 && d.length >= 11) {
              const f = d[6], s2 = !!(f & 4);
              r.deliveries.push({ tsid, onid, freqKHz: bcd(d.subarray(0, 4), 8) * 10,
                orbital: bcd(d.subarray(4, 6), 4) / 10, east: !!(f & 0x80), pol: POL[(f >> 5) & 3],
                system: s2 ? "DVB-S2" : "DVB-S", mod: MOD[f & 3], sr: bcd(d.subarray(7, 11), 7) * 100,
                fec: FEC[d[10] & 15] || "auto" });
            }
          }
          i += 6 + dl;
        }
      }
    }
    function svcFor(id) { return r.services[id] || (r.services[id] = { id, name: null, components: [] }); }

    function drain(pid) {
      const b = buf[pid];
      while (b && b.length >= 3) {
        if (b[0] === 0xff) { delete buf[pid]; return; }
        const total = 3 + (((b[1] & 15) << 8) | b[2]);
        if (b.length < total) return;
        section(pid, Uint8Array.from(b.splice(0, total)));
      }
    }

    let i = 0;
    while (i + 188 <= data.length && r.packets < maxPackets) {
      if (data[i] !== 0x47) { r.syncErrors++; const n = data.indexOf(0x47, i + 1); if (n < 0) break; i = n; continue; }
      const p = data.subarray(i, i + 188);
      i += 188;
      r.packets++;
      const pid = ((p[1] & 0x1f) << 8) | p[2];
      r.pidCounts[pid] = (r.pidCounts[pid] || 0) + 1;
      if (pid === 0x1fff) continue;
      if (p[3] & 0xc0) r.scrambledPids.add(pid);
      const afc = (p[3] >> 4) & 3, c = p[3] & 15;
      if (afc & 1) {
        if (cc[pid] !== undefined && c !== ((cc[pid] + 1) & 15) && c !== cc[pid]) r.ccErrors++;
        cc[pid] = c;
      } else continue;
      let off = 4 + (afc & 2 ? 1 + p[4] : 0);
      if (off >= 188) continue;
      if (!(pid === 0 || pid === 0x11 || pid === nitPid || pmtPids[pid] !== undefined)) continue;
      const pay = p.subarray(off);
      if (p[1] & 0x40) {
        const ptr = pay[0];
        if (buf[pid]) { buf[pid].push(...pay.subarray(1, 1 + ptr)); drain(pid); }
        buf[pid] = Array.from(pay.subarray(1 + ptr));
      } else if (buf[pid]) buf[pid].push(...pay);
      else continue;
      drain(pid);
    }
    const services = Object.values(r.services).filter((s) => s.pmtPid !== undefined).sort((a, b) => a.id - b.id);
    for (const s of services) s.scrambled = !!(s.ca || s.freeCA || s.components.some((c) => r.scrambledPids.has(c.pid)));
    const orbitals = [...new Set(r.deliveries.map((d) => d.orbital.toFixed(1) + "°" + (d.east ? "E" : "W")))].sort();
    const here = r.deliveries.find((d) => d.tsid === r.tsid && (r.onid === null || d.onid === r.onid)) || null;
    return { ...r, services, orbitals, here };
  }

  const api = { parse, crc32mpeg2 };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SkyboxTS = api;
})(typeof self !== "undefined" ? self : this);
