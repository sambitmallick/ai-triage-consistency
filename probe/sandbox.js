// HARNESS-OWNED. Runs ONE agent-written probe, in its own process, under Node's permission model
// (read-only files, no child processes, no workers). The probe gets these names, nothing else to import:
//   zod3, zod            the two libraries
//   oracle.parseSignup / oracle.parseConfig   the schemas as they were before the upgrade (zod 3)
//   main.parseSignup   / main.parseConfig     the merged build (zod 4)
//   print(...)           output (this is what the harness compares against the claim)
// The probe source arrives on stdin.
const zod3 = require("zod3"), zod = require("zod");
const oracle = require("../oracle/zod3"), main = require("../dist/src");
let out = "";
const show = (v) => (typeof v === "string" ? v : JSON.stringify(v, (k, x) => (typeof x === "number" && !Number.isFinite(x) ? String(x) : x)));
const print = (...a) => { out += a.map(show).join(" ") + "\n"; };
let src = "";
process.stdin.on("data", (c) => (src += c));
process.stdin.on("end", () => {
  try {
    new Function("zod3", "zod", "oracle", "main", "print", src)(zod3, zod, oracle, main, print);
  } catch (e) {
    out += `PROBE ERROR: ${e && e.message}\n`;
  }
  process.stdout.write(out.slice(0, 4000));
});
