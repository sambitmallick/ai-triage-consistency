// Compact the frozen evidence: per example, only the field that matters and what each version said.
// Run: node triage/compact.js   (reads triage/evidence.json, writes triage/evidence.txt)
const fs = require("fs");
const path = require("path");
const ev = JSON.parse(fs.readFileSync(path.join(__dirname, "evidence.json"), "utf8"));
const say = (a) => (a.ok ? "accepts" : `rejects (${(a.fields || []).join(", ")})`);
const lines = [`${ev.total} different answers out of ${2 * ev.perSchema} generated inputs (seed ${ev.seed}). zod3 = the oracle (before the upgrade), now = the merged build.`];
for (const g of ev.groups) {
  lines.push("", `[${g.count}] ${g.heading}`);
  const field = g.heading.split(": ")[1].split(" ")[0];
  for (const e of g.examples.slice(0, 8)) {
    if (field === "rejected") {
      lines.push(`   zod3 ${say(e.zod3)}  |  now ${say(e.now)}`);
    } else if (e.zod3.ok && e.now.ok) {
      lines.push(`   ${field} = ${JSON.stringify(e.input[field])}  ->  zod3 stores ${JSON.stringify(e.zod3.value[field])}  |  now stores ${JSON.stringify(e.now.value[field])}`);
    } else {
      lines.push(`   ${field} = ${JSON.stringify(e.input[field])}  ->  zod3 ${say(e.zod3)}  |  now ${say(e.now)}`);
    }
  }
}
const text = lines.join("\n").replace(/"__(-?Infinity|NaN)__"/g, "$1") + "\n";
fs.writeFileSync(path.join(__dirname, "evidence.txt"), text);
console.log(text);
