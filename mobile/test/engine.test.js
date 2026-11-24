const assert = require("assert");
const E = require("../www/engine.js");
const fails = E.selfTest().filter((r) => !r.ok);
assert.deepStrictEqual(fails, [], "self-test failures: " + JSON.stringify(fails));
const fr = E.encodeFrame(0x12, E.parseHex("00 00 00 80 00 08"));
assert.strictEqual(E.decodeFrame(fr).cmd, 0x12);
assert.ok(E.tuneConf({service: "ch1", delsys: "DVBS2", freq: "1", sr: "2", fec: "auto", mod: "auto",
  pol: "H", rolloff: "auto", pilot: "auto", mis: "", pls: ""}).includes("ROLLOFF"));
console.log("engine tests passed");

// Beryl: TS parser and dvbv5 names
const T = require("../www/tsparser.js");
const fs = require("fs");
const r = T.parse(new Uint8Array(fs.readFileSync(__dirname + "/demo.ts")));
assert.strictEqual(r.services.length, 2);
assert.deepStrictEqual(r.orbitals, ["28.2°E"]);
assert.strictEqual(r.here.freqKHz, 11778000);
assert.strictEqual(r.services[0].components[0].codec, "H.265 / HEVC");
assert.ok(r.services[1].scrambled);
assert.ok(E.tuneConf({freq: "1", sr: "1", delsys: "DVBS2", mod: "8PSK", fec: "auto", pol: "H", rolloff: "auto",
  pilot: "auto", inversion: "auto", mis: "", pls: "", plsMode: "ROOT", diseqc: "none", service: "x"}).includes("PSK/8"));
assert.throws(() => E.tuneConf({freq: "1", sr: "1", delsys: "DVBS", mod: "8PSK", pol: "H", service: "x"}));
console.log("ts parser tests passed");
