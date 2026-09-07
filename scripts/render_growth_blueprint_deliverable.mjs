import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

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
const C = { ink: "#17130F", ivory: "#F4F0E8", muted: "#8B8173", amber: "#F2B500", rust: "#C85A32", sage: "#A8B5A0", smoke: "#DED7CA", white: "#FFFDF7", dark: "#0F0D0B" };
const clean = value => String(value || "").replace(/[\u2013\u2014]/g, "-").replace(/\s+/g, " ").trim();
const short = (value, limit) => { const x = clean(value); if (x.length <= limit) return x; const cut = x.slice(0, limit).lastIndexOf(" "); return `${x.slice(0, cut > 20 ? cut : limit - 1)}…`; };
function text(slide, value, position, style = {}) {
  const shape = slide.shapes.add({ geometry: "textbox", position, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = clean(value);
  shape.text.style = { typeface: style.typeface || family, fontSize: style.fontSize || 20, color: style.color || C.ink, bold: Boolean(style.bold), italic: Boolean(style.italic), autoFit: "shrinkTextOnOverflow", alignment: style.alignment || "left" };
  return shape;
}
function box(slide, position, fill, radius = false, line = "none") { return slide.shapes.add({ geometry: radius ? "roundRect" : "rect", position, fill, line: { fill: line === "none" ? fill : line, width: line === "none" ? 0 : 1 } }); }
function footer(slide, s) { text(slide, "NARRATIIVE  /  GROWTH BLUEPRINT", { left: 72, top: 677, width: 430, height: 18 }, { fontSize: 10, color: C.muted, bold: true }); text(slide, `${String(s.slide_no).padStart(2, "0")}  /  ${String(spec.slides.length).padStart(2, "0")}`, { left: 1120, top: 677, width: 88, height: 18 }, { fontSize: 10, color: C.muted, alignment: "right" }); }
function header(slide, s, act = "") { text(slide, act || "THE NARRATIIVE GROWTH BLUEPRINT", { left: 72, top: 34, width: 650, height: 18 }, { fontSize: 11, color: C.rust, bold: true }); text(slide, s.title, { left: 72, top: 72, width: 1120, height: 58 }, { fontSize: 33, color: C.ink, bold: true }); box(slide, { left: 72, top: 146, width: 1136, height: 2 }, C.smoke); }
function cards(slide, s, count = 3) { const gap = 20, left = 72, top = 230, width = (1136 - gap * (count - 1)) / count; const chunks = [short(s.takeaway, 120), short(s.body, 110), "What this means next"]; for (let i = 0; i < count; i += 1) { const x = left + i * (width + gap); box(slide, { left: x, top, width, height: 260 }, i === 0 ? C.dark : i === 1 ? C.smoke : C.sage, true); text(slide, i === 0 ? "THE SIGNAL" : i === 1 ? "THE READING" : "THE MOVE", { left: x + 24, top: top + 24, width: width - 48, height: 18 }, { fontSize: 10, color: i === 0 ? C.amber : C.rust, bold: true }); text(slide, chunks[i], { left: x + 24, top: top + 64, width: width - 48, height: 170 }, { fontSize: i === 0 ? 21 : 19, color: i === 0 ? C.white : C.ink, bold: i === 0 }); } }
function render(slide, s, index) {
  const arch = s.layout_type || s.visual_treatment;
  const act = index < 7 ? "ACT 1  /  THE CASE FOR CHANGE" : index < 13 ? "ACT 2  /  THE DIAGNOSIS" : index < 17 ? "ACT 3  /  THE CHOICE" : "ACT 4  /  THE MOVE";
  if (index === 1) {
    slide.background.fill = C.dark; box(slide, { left: 0, top: 0, width: 14, height: 720 }, C.amber); text(slide, "NARRATIIVE", { left: 88, top: 74, width: 360, height: 34 }, { fontSize: 18, color: C.white, bold: true }); text(slide, "S T R A T E G Y   ·   N A R R A T I V E   ·   G R O W T H", { left: 90, top: 115, width: 540, height: 20 }, { fontSize: 10, color: C.muted, bold: true }); text(slide, s.title, { left: 88, top: 265, width: 980, height: 90 }, { fontSize: 62, color: C.white, bold: false }); box(slide, { left: 90, top: 390, width: 58, height: 4 }, C.amber); text(slide, "THE NARRATIIVE GROWTH BLUEPRINT", { left: 90, top: 430, width: 700, height: 28 }, { fontSize: 18, color: C.amber, bold: true }); text(slide, "Strategic clarity for scalable growth.", { left: 90, top: 470, width: 650, height: 34 }, { fontSize: 22, color: "#BDB4A5", italic: true }); text(slide, "SAFE INTERNAL STRATEGIC PILOT - NOT COMMISSIONED - NO CONTACT", { left: 90, top: 650, width: 720, height: 18 }, { fontSize: 10, color: C.muted, bold: true }); slide.speakerNotes.textFrame.setText(`${(s.source_notes || []).join("\\n")}\\nInternal pilot disclosure: Rave Coffee did not commission this work.`); return; }
  slide.background.fill = C.ivory; header(slide, s, act);
  if (arch === "thesis" || arch === "provocation" || arch === "closing") { text(slide, short(s.takeaway, 125), { left: 100, top: 230, width: 1010, height: 155 }, { fontSize: 32, color: C.dark, bold: true }); box(slide, { left: 100, top: 425, width: 10, height: 105 }, C.amber); text(slide, short(s.body, 180), { left: 136, top: 425, width: 940, height: 92 }, { fontSize: 20, color: C.ink }); }
  else if (["market_forces", "comparison", "competitive_landscape", "demand_pools", "channel_roles", "message_architecture"].includes(arch)) cards(slide, s, 3);
  else if (["positioning_map", "journey", "flywheel", "prioritisation"].includes(arch)) { text(slide, s.takeaway, { left: 72, top: 205, width: 460, height: 130 }, { fontSize: 29, color: C.dark, bold: true }); box(slide, { left: 620, top: 200, width: 588, height: 300 }, C.dark, true); text(slide, arch === "positioning_map" ? "OWNABLE TERRITORY" : arch.toUpperCase(), { left: 660, top: 235, width: 500, height: 20 }, { fontSize: 11, color: C.amber, bold: true }); text(slide, s.body, { left: 660, top: 282, width: 500, height: 170 }, { fontSize: 22, color: C.white, bold: true }); }
  else { text(slide, short(s.takeaway, 90), { left: 72, top: 205, width: 540, height: 120 }, { fontSize: 22, color: C.dark, bold: true }); box(slide, { left: 72, top: 380, width: 1136, height: 155 }, C.smoke, true); text(slide, arch.replace(/_/g, " ").toUpperCase(), { left: 102, top: 408, width: 400, height: 18 }, { fontSize: 10, color: C.rust, bold: true }); text(slide, short(s.body, 180), { left: 102, top: 443, width: 1020, height: 62 }, { fontSize: 22, color: C.ink }); }
  footer(slide, s); slide.speakerNotes.textFrame.setText(`${(s.source_notes || []).join("\\n")}\\nEvidence refs (internal only): ${(s.evidence_refs || []).join(", ") || "none supplied"}`);
}
for (let i = 0; i < spec.slides.length; i += 1) { const s = spec.slides[i]; const slide = presentation.slides.add(); render(slide, s, i + 1); }
const candidatePath = path.join(outputDir, ".candidate.pptx"); await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const finalPath = path.join(outputDir, "Rave-Growth-Blueprint-SAFE-Pilot.pptx");
const workspaceDir = path.dirname(outputDir); const reportPath = path.join(workspaceDir, `${path.basename(outputDir)}.validation.json`);
const result = await finalizePresentation({ workspaceDir, candidatePath, finalPath, pythonExecutable: runtimePython, integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"), layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"), layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-heading-fit"], requiredNativeTableOwnerSlides: [], fontPolicy: { basis: "design", families: [family] }, verifyArtifactToolImport: true, receiptPath: reportPath });
const previewDir = path.join(outputDir, ".rendered-slides"); await fs.mkdir(previewDir, { recursive: true });
for (let i = 0; i < presentation.slides.count; i += 1) { const preview = await presentation.export({ slide: presentation.slides.getItem(i), format: "png", scale: 1 }); await fs.writeFile(path.join(previewDir, `slide-${i + 1}.png`), Buffer.from(await preview.arrayBuffer())); }
const pdfPath = path.join(outputDir, "Rave-Growth-Blueprint-SAFE-Pilot.pdf"); await fs.writeFile(path.join(outputDir, "presentation-specification.json"), JSON.stringify(spec, null, 2) + "\n"); console.log(JSON.stringify({ pptx: finalPath, pdf: pdfPath, validation: result, slideCount: spec.slides.length }, null, 2));
