import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const specPath = path.resolve(process.argv[2] || "");
const outputDir = path.resolve(process.argv[3] || "");
const skillDir = path.resolve(process.env.SKILL_DIR || "");
const runtimeNodeModules = process.env.RUNTIME_NODE_MODULES || "";
const runtimePython = process.env.RUNTIME_PYTHON || "python3";
if (!specPath || !outputDir || !skillDir || !runtimeNodeModules) throw new Error("spec, output, SKILL_DIR and RUNTIME_NODE_MODULES are required");
const spec = JSON.parse(await fs.readFile(specPath, "utf8"));
await fs.mkdir(outputDir, { recursive: true });
const { importRuntimeModule } = await import(pathToFileURL(path.join(skillDir, "container_tools/runtime_helpers.mjs")).href);
const { Presentation, PresentationFile } = await importRuntimeModule("@oai/artifact-tool");
const { resolvePresentationFont, finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
const family = resolvePresentationFont({ availableFonts: ["Aptos", "Arial", "Helvetica"] });
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const assetDir = path.join(repoRoot, "assets", "presentation", "katkin");
const heroImage = path.join(assetDir, "hero-cat.png");
const scienceImage = path.join(assetDir, "nutrition-science.png");
const isKatkin = /katkin/i.test(`${spec.client_id || ""} ${spec.title || ""}`);
const haveImages = isKatkin && await fs.access(heroImage).then(() => true).catch(() => false) && await fs.access(scienceImage).then(() => true).catch(() => false);
const heroBytes = haveImages ? await fs.readFile(heroImage) : null;
const scienceBytes = haveImages ? await fs.readFile(scienceImage) : null;
const C = { ink: "#15121B", plum: "#261A31", purple: "#5A2E78", coral: "#FF654F", blush: "#F8D8D2", cream: "#F6F0E8", white: "#FFFDFC", grey: "#8A8291", lilac: "#C8B7E8", line: "#D9CFD5" };
const clean = value => String(value || "").replace(/[\u2013\u2014]/g, " - ").replace(/\s+/g, " ").trim();
const short = (value, limit) => { const x = clean(value); if (x.length <= limit) return x; const cut = x.slice(0, limit).lastIndexOf(" "); return `${x.slice(0, cut > 24 ? cut : limit - 1)}…`; };
const safeName = value => clean(value).normalize("NFKD").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "Client";
const outputBase = `${safeName(spec.client_id || spec.title)}-Growth-Blueprint-v${Number(spec.source_blueprint_version || 1)}`;
const disclosure = clean((spec.notes || [])[0]) || "INTERNAL REVIEW DRAFT - HUMAN APPROVAL REQUIRED";

function box(slide, position, fill, geometry = "rect", line = fill) { return slide.shapes.add({ geometry, position, fill, line: { fill: line, width: line === fill ? 0 : 1 } }); }
function rule(slide, left, top, width, fill = C.line) { return box(slide, { left, top, width, height: 2 }, fill); }
function text(slide, value, position, style = {}) {
  const shape = slide.shapes.add({ geometry: "textbox", position, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = clean(value);
  shape.text.style = { typeface: style.typeface || family, fontSize: style.fontSize || 20, color: style.color || C.ink, bold: Boolean(style.bold), italic: Boolean(style.italic), autoFit: "shrinkTextOnOverflow", alignment: style.alignment || "left", verticalAlignment: style.verticalAlignment || "top" };
  return shape;
}
function photo(slide, source, position, alt) { return slide.images.add({ blob: source, contentType: "image/png", alt, fit: "cover", position }); }
function notes(slide, s) { slide.speakerNotes.textFrame.setText(`${(s.source_notes || []).join("\n")}\nEvidence refs (internal only): ${(s.evidence_refs || []).join(", ") || "none supplied"}\n${disclosure}`); }
function footer(slide, s, dark = false) {
  text(slide, "NARRATIIVE", { left: 68, top: 678, width: 180, height: 15 }, { fontSize: 9, color: dark ? C.lilac : C.grey, bold: true });
  text(slide, `${String(s.slide_no).padStart(2, "0")} / ${String(spec.slides.length).padStart(2, "0")}`, { left: 1120, top: 678, width: 92, height: 15 }, { fontSize: 9, color: dark ? C.lilac : C.grey, alignment: "right" });
}
function act(index) { if (index <= 2) return "ACT 1 / THE DECISION"; if (index <= 5) return "ACT 2 / THE PROOF GAP"; if (index <= 8) return "ACT 3 / THE GROWTH AUDIENCE"; if (index <= 12) return "ACT 4 / THE STRATEGIC ANSWER"; if (index <= 15) return "ACT 5 / THE GROWTH SYSTEM"; return "ACT 6 / THE FIRST 90 DAYS"; }
function header(slide, s, index) {
  text(slide, act(index), { left: 68, top: 35, width: 600, height: 15 }, { fontSize: 9, color: C.coral, bold: true });
  text(slide, s.title, { left: 68, top: 72, width: 1100, height: 58 }, { fontSize: 31, color: C.ink, bold: true });
  rule(slide, 68, 147, 1144);
}
function consequence(slide, s, dark = false) {
  text(slide, "COMMERCIAL CONSEQUENCE", { left: 68, top: 608, width: 220, height: 14 }, { fontSize: 9, color: C.coral, bold: true });
  text(slide, short(s.takeaway, 180), { left: 275, top: 602, width: 840, height: 38 }, { fontSize: 16, color: dark ? C.white : C.ink, bold: true });
}

function cover(slide, s) {
  slide.background.fill = C.ink;
  if (haveImages) photo(slide, heroBytes, { left: 0, top: 0, width: 1280, height: 720 }, "Black cat portrait with negative space");
  box(slide, { left: 0, top: 0, width: 800, height: 720 }, "#15121BDD");
  box(slide, { left: 0, top: 0, width: 14, height: 720 }, C.coral);
  text(slide, "NARRATIIVE", { left: 82, top: 66, width: 240, height: 26 }, { fontSize: 15, color: C.white, bold: true });
  text(slide, "GROWTH BLUEPRINT / 2026", { left: 82, top: 105, width: 360, height: 20 }, { fontSize: 10, color: C.lilac, bold: true });
  text(slide, isKatkin ? "KatKin" : s.title, { left: 82, top: 248, width: 600, height: 84 }, { fontSize: 68, color: C.white, bold: true });
  text(slide, isKatkin ? "The science cats deserve" : short(s.takeaway, 80), { left: 84, top: 350, width: 640, height: 46 }, { fontSize: 28, color: C.coral, bold: true });
  text(slide, "From category claim to category authority", { left: 84, top: 420, width: 620, height: 32 }, { fontSize: 18, color: C.white });
  text(slide, disclosure, { left: 84, top: 642, width: 680, height: 18 }, { fontSize: 9, color: C.lilac, bold: true });
  notes(slide, s);
}
function thesis(slide, s, index) {
  slide.background.fill = C.cream; header(slide, s, index);
  text(slide, short(s.body, 360), { left: 68, top: 188, width: 730, height: 240 }, { fontSize: 29, color: C.ink, bold: true });
  box(slide, { left: 875, top: 190, width: 280, height: 280 }, C.plum, "ellipse");
  text(slide, "PROOF", { left: 923, top: 254, width: 185, height: 35 }, { fontSize: 24, color: C.white, bold: true, alignment: "center" });
  rule(slide, 942, 313, 145, C.coral);
  text(slide, "A claim competitors cannot copy in one ad cycle", { left: 917, top: 345, width: 198, height: 82 }, { fontSize: 17, color: C.lilac, bold: true, alignment: "center" });
  consequence(slide, s); footer(slide, s); notes(slide, s);
}
function forces(slide, s, index) {
  slide.background.fill = C.cream; header(slide, s, index);
  const items = [["SAMENESS", "Shared functional language"], ["DISCOVERY", "Organic and AI search shift"], ["ECONOMICS", "Paid creative pressure"], ["MANDATE", "Build a loved brand"]];
  [[78, 210], [78, 370], [862, 210], [862, 370]].forEach(([left, top], i) => {
    box(slide, { left, top, width: 332, height: 124 }, i % 2 ? C.blush : C.white, "roundRect");
    text(slide, items[i][0], { left: left + 22, top: top + 18, width: 286, height: 16 }, { fontSize: 10, color: C.coral, bold: true });
    text(slide, items[i][1], { left: left + 22, top: top + 49, width: 286, height: 48 }, { fontSize: 18, color: C.ink, bold: true });
  });
  box(slide, { left: 482, top: 250, width: 316, height: 205 }, C.ink, "roundRect");
  text(slide, "THE PRESSURE", { left: 520, top: 286, width: 240, height: 16 }, { fontSize: 10, color: C.coral, bold: true, alignment: "center" });
  text(slide, short(s.body, 155), { left: 520, top: 326, width: 240, height: 95 }, { fontSize: 20, color: C.white, bold: true, alignment: "center" });
  consequence(slide, s); footer(slide, s); notes(slide, s);
}
function proof(slide, s, index) {
  slide.background.fill = C.cream; header(slide, s, index);
  if (haveImages) photo(slide, scienceBytes, { left: 68, top: 180, width: 570, height: 360 }, "Nutrition science visual");
  box(slide, { left: 636, top: 180, width: 576, height: 360 }, C.plum);
  text(slide, "THE HARD PART IS ALREADY DONE", { left: 684, top: 218, width: 430, height: 18 }, { fontSize: 10, color: C.coral, bold: true });
  text(slide, short(s.body, 245), { left: 684, top: 264, width: 430, height: 176 }, { fontSize: 25, color: C.white, bold: true });
  text(slide, "Independent research changes the basis of competition.", { left: 684, top: 468, width: 430, height: 42 }, { fontSize: 16, color: C.lilac });
  consequence(slide, s); footer(slide, s); notes(slide, s);
}
function tension(slide, s, index) {
  slide.background.fill = C.cream; header(slide, s, index);
  text(slide, "WHAT OWNERS SEE", { left: 82, top: 204, width: 360, height: 18 }, { fontSize: 10, color: C.grey, bold: true });
  text(slide, "Confident claims", { left: 82, top: 252, width: 420, height: 58 }, { fontSize: 35, color: C.ink, bold: true });
  text(slide, "Fresh. Real meat. Vet formulated.", { left: 82, top: 330, width: 420, height: 55 }, { fontSize: 21, color: C.grey });
  box(slide, { left: 558, top: 222, width: 164, height: 164 }, C.coral, "ellipse");
  text(slide, "THE\nGAP", { left: 588, top: 267, width: 104, height: 72 }, { fontSize: 25, color: C.white, bold: true, alignment: "center" });
  text(slide, "WHAT KATKIN CAN PROVE", { left: 792, top: 204, width: 380, height: 18 }, { fontSize: 10, color: C.coral, bold: true });
  text(slide, "Independent science", { left: 792, top: 252, width: 420, height: 58 }, { fontSize: 35, color: C.purple, bold: true });
  text(slide, short(s.body, 175), { left: 792, top: 330, width: 390, height: 100 }, { fontSize: 18, color: C.ink });
  consequence(slide, s); footer(slide, s); notes(slide, s);
}
function audience(slide, s, index) {
  slide.background.fill = C.cream; header(slide, s, index);
  const labels = index % 2 ? ["Committed DTC", "Retail converts", "Mainstream owners"] : ["Motivation", "Barrier", "Trigger"];
  const statements = index % 2 ? ["Keep belief. Reduce churn.", "Earn confidence without a quiz.", "Make proof legible at a glance."] : ["Confidence in doing right by the cat", "Premium price and change anxiety", "Independent proof at the decision moment"];
  [C.plum, C.purple, C.coral].forEach((color, i) => {
    const left = 76 + i * 386;
    box(slide, { left, top: 215, width: 342, height: 250 }, color, "roundRect");
    text(slide, `0${i + 1}`, { left: left + 24, top: 238, width: 48, height: 25 }, { fontSize: 12, color: C.lilac, bold: true });
    text(slide, labels[i], { left: left + 24, top: 286, width: 290, height: 45 }, { fontSize: 24, color: C.white, bold: true });
    text(slide, statements[i], { left: left + 24, top: 360, width: 286, height: 70 }, { fontSize: 17, color: C.white, bold: true });
  });
  consequence(slide, s); footer(slide, s); notes(slide, s);
}
function decisions(slide, s, index) {
  slide.background.fill = C.ink;
  text(slide, act(index), { left: 68, top: 35, width: 520, height: 16 }, { fontSize: 9, color: C.coral, bold: true });
  text(slide, s.title, { left: 68, top: 75, width: 1080, height: 55 }, { fontSize: 31, color: C.white, bold: true });
  const labels = ["POSITION", "BENEFIT", "PLATFORM", "EXPRESSION"];
  const copy = ["Proof, not promise", "Confidence without self-audit", "The science cats deserve", "Visible without personalisation"];
  labels.forEach((label, i) => {
    const top = 185 + i * 95;
    text(slide, label, { left: 80, top: top + 8, width: 150, height: 18 }, { fontSize: 10, color: C.coral, bold: true });
    rule(slide, 245, top + 17, 52, C.purple);
    text(slide, copy[i], { left: 330, top, width: 770, height: 42 }, { fontSize: 25, color: i === index % 4 ? C.coral : C.white, bold: true });
  });
  consequence(slide, s, true); footer(slide, s, true); notes(slide, s);
}
function narrative(slide, s, index) {
  slide.background.fill = C.cream; header(slide, s, index);
  const steps = [["1", "TENSION", "The category asks owners to trust claims"], ["2", "SHIFT", "KatKin makes proof the starting point"], ["3", "RESOLUTION", "Independent science carries the decision"]];
  steps.forEach((item, i) => {
    const left = 74 + i * 390;
    box(slide, { left, top: 220, width: 336, height: 230 }, i === 1 ? C.coral : C.white, "roundRect");
    text(slide, item[0], { left: left + 22, top: 242, width: 40, height: 28 }, { fontSize: 18, color: i === 1 ? C.white : C.coral, bold: true });
    text(slide, item[1], { left: left + 22, top: 292, width: 280, height: 18 }, { fontSize: 10, color: i === 1 ? C.white : C.grey, bold: true });
    text(slide, item[2], { left: left + 22, top: 336, width: 285, height: 74 }, { fontSize: 20, color: i === 1 ? C.white : C.ink, bold: true });
  });
  text(slide, "THE SCIENCE CATS DESERVE", { left: 285, top: 492, width: 710, height: 44 }, { fontSize: 29, color: C.purple, bold: true, alignment: "center" });
  consequence(slide, s); footer(slide, s); notes(slide, s);
}
function mechanisms(slide, s, index) {
  slide.background.fill = C.cream; header(slide, s, index);
  [["EARNED", "A citable point of view"], ["RETAIL", "Premium proof at shelf"], ["CRM", "Segmented confidence"], ["INVESTOR", "Earlier leading signals"]].forEach((item, i) => {
    const left = 74 + i * 288;
    box(slide, { left, top: 220, width: 252, height: 250 }, i === 0 ? C.plum : C.white, "roundRect");
    box(slide, { left: left + 24, top: 244, width: 34, height: 34 }, i === 0 ? C.coral : C.blush, "ellipse");
    text(slide, item[0], { left: left + 24, top: 306, width: 204, height: 18 }, { fontSize: 10, color: i === 0 ? C.coral : C.grey, bold: true });
    text(slide, item[1], { left: left + 24, top: 350, width: 204, height: 75 }, { fontSize: 20, color: i === 0 ? C.white : C.ink, bold: true });
  });
  consequence(slide, s); footer(slide, s); notes(slide, s);
}
function channels(slide, s, index) {
  slide.background.fill = C.cream; header(slide, s, index);
  [["DTC QUIZ", "Discovery and education", "Personalised"], ["CRM", "Trust and retention", "First party"], ["RETAIL", "Conversion", "Unaided"], ["EARNED / SEARCH", "Scale discovery", "Citable"], ["PAID SOCIAL", "Volume", "Rebalanced"]].forEach((row, i) => {
    const top = 192 + i * 72;
    if (i === 2) box(slide, { left: 68, top: top - 8, width: 1144, height: 62 }, C.blush, "roundRect");
    text(slide, row[0], { left: 86, top, width: 210, height: 18 }, { fontSize: 10, color: i === 2 ? C.coral : C.grey, bold: true });
    text(slide, row[1], { left: 326, top: top - 4, width: 510, height: 28 }, { fontSize: 19, color: C.ink, bold: true });
    text(slide, row[2], { left: 940, top, width: 220, height: 18 }, { fontSize: 11, color: C.purple, bold: true, alignment: "right" });
    if (i < 4) rule(slide, 68, top + 45, 1144);
  });
  consequence(slide, s); footer(slide, s); notes(slide, s);
}
function plan(slide, s, index) {
  slide.background.fill = C.cream; header(slide, s, index);
  [["DAYS 1-30", "Foundation", "Founder pressure-test\nClaims and evidence audit"], ["DAYS 31-60", "Launch", "Retail translation test\nCRM segmentation pilot"], ["DAYS 61-90", "Scale", "Read leading signals\nShift spend only when proven"]].forEach((phase, i) => {
    const left = 72 + i * 386;
    box(slide, { left, top: 205, width: 340, height: 305 }, [C.plum, C.purple, C.coral][i], "roundRect");
    text(slide, phase[0], { left: left + 24, top: 232, width: 292, height: 18 }, { fontSize: 10, color: C.white, bold: true });
    text(slide, phase[1], { left: left + 24, top: 282, width: 292, height: 44 }, { fontSize: 27, color: C.white, bold: true });
    text(slide, phase[2], { left: left + 24, top: 355, width: 292, height: 88 }, { fontSize: 18, color: C.white });
  });
  consequence(slide, s); footer(slide, s); notes(slide, s);
}
function closing(slide, s) {
  slide.background.fill = C.ink;
  if (haveImages) photo(slide, heroBytes, { left: 760, top: 0, width: 520, height: 720 }, "Black cat portrait");
  box(slide, { left: 0, top: 0, width: 860, height: 720 }, "#15121BEE");
  text(slide, "THE MANDATE", { left: 76, top: 72, width: 280, height: 18 }, { fontSize: 10, color: C.coral, bold: true });
  text(slide, "Own the proof.", { left: 76, top: 186, width: 620, height: 74 }, { fontSize: 56, color: C.white, bold: true });
  text(slide, "Make it easy to feel.", { left: 76, top: 272, width: 640, height: 74 }, { fontSize: 50, color: C.coral, bold: true });
  text(slide, "Then earn the right to scale.", { left: 76, top: 368, width: 620, height: 55 }, { fontSize: 30, color: C.lilac, bold: true });
  text(slide, "IMMEDIATE NEXT STEP", { left: 76, top: 510, width: 240, height: 18 }, { fontSize: 10, color: C.coral, bold: true });
  text(slide, "Founder pressure-test and retail translation test", { left: 76, top: 544, width: 590, height: 56 }, { fontSize: 21, color: C.white, bold: true });
  footer(slide, s, true); notes(slide, s);
}
function render(slide, s, index) {
  if (index === 1) return cover(slide, s);
  if (index === spec.slides.length) return closing(slide, s);
  if (index === 2) return thesis(slide, s, index);
  if (index === 3) return forces(slide, s, index);
  if (index === 4) return proof(slide, s, index);
  if (index === 5) return tension(slide, s, index);
  if ([6, 7, 8].includes(index)) return audience(slide, s, index);
  if ([9, 10].includes(index)) return decisions(slide, s, index);
  if ([11, 12].includes(index)) return narrative(slide, s, index);
  if (index === 13) return mechanisms(slide, s, index);
  if ([14, 15].includes(index)) return channels(slide, s, index);
  if (index === 16) return plan(slide, s, index);
  return thesis(slide, s, index);
}

for (let i = 0; i < spec.slides.length; i += 1) { const slide = presentation.slides.add(); render(slide, spec.slides[i], i + 1); }
const buildDir = path.join(outputDir, ".build"); await fs.mkdir(buildDir, { recursive: true });
const candidatePath = path.join(buildDir, "candidate.pptx"); await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const finalPath = path.join(outputDir, `${outputBase}.pptx`);
const workspaceDir = path.dirname(outputDir); const reportPath = path.join(workspaceDir, `${path.basename(outputDir)}.validation.json`);
await finalizePresentation({ workspaceDir, candidatePath, finalPath, pythonExecutable: runtimePython, integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"), layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"), layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-heading-fit"], requiredNativeTableOwnerSlides: [], fontPolicy: { basis: "design", families: [family] }, verifyArtifactToolImport: true, receiptPath: reportPath });
const previewDir = path.join(outputDir, ".rendered-slides"); await fs.mkdir(previewDir, { recursive: true });
for (let i = 0; i < presentation.slides.count; i += 1) { const preview = await presentation.export({ slide: presentation.slides.getItem(i), format: "png", scale: 1 }); await fs.writeFile(path.join(previewDir, `slide-${i + 1}.png`), Buffer.from(await preview.arrayBuffer())); }
const pdfPath = path.join(outputDir, `${outputBase}.pdf`);
const receipt = { pptx: finalPath, pdf: pdfPath, validation: reportPath, slideCount: spec.slides.length, brandVisuals: haveImages };
await fs.writeFile(path.join(outputDir, "presentation-specification.json"), JSON.stringify(spec, null, 2) + "\n");
await fs.writeFile(path.join(outputDir, "render-receipt.json"), JSON.stringify(receipt, null, 2) + "\n");
console.log(JSON.stringify(receipt, null, 2));
