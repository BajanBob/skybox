const assert = require("assert");
const E = require("../www/engine.js");
const fails = E.selfTest().filter((r) => !r.ok);
assert.deepStrictEqual(fails, [], "self-test failures: " + JSON.stringify(fails));
const fr = E.encodeFrame(0x12, E.parseHex("00 00 00 80 00 08"));
assert.strictEqual(E.decodeFrame(fr).cmd, 0x12);
assert.ok(E.tuneConf({service: "ch1", delsys: "DVBS2", freq: "1", sr: "2", fec: "auto", mod: "auto",
  pol: "H", rolloff: "auto", pilot: "auto", mis: "", pls: ""}).includes("ROLLOFF"));
console.log("engine tests passed");
