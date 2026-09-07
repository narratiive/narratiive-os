import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const specPath = path.resolve(process.argv[2] || "");
const outputDir = path.resolve(process.argv[3] || "");
const skillDir = path.resolve(process.env.SKILL_DIR || "");
const runtimePython = process.env.RUNTIME_PYTHON || "python3";
const runtimeNodeModules = process.env.RUNTIME_NODE_MODULES || "";
if (!specPath || !outputDir || !skillDir || !runtimeNodeModules) throw new Error("spec, output, SKILL_DIR and RUNTIME_NODE_MODULES are required");
const spec = JSON.parse(await fs.readFile(specPath, "utf8"));
await fs.mkdir(outputDir, { recursive: true });
const { importRuntimeModule } = await import(pathToFileURL(path.join(skillDir, "container_tools/runtime_helpers.mjs")).href);
const { Presentation, PresentationFile } = await importRuntimeModule("@oai/artifact-tool");
const { resolvePresentationFont, finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
const family = resolvePresentationFont({ availableFonts: ["Aptos", "Arial", "Helvetica"] });
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const C = { ink: "#1E1C2A", muted: "#6D6875", cream: "#F7F4EF", accent: "#E55934", violet: "#433E5B", soft: "#E8E2F0", white: "#FFFFFF", line: "#D8D2C8" };
const safeText = value => String(value || "").replace(/[\u2013\u2014]/g, "-");
function textbox(slide, text, position, style = {}) {
  const shape = slide.shapes.add({ geometry: "textbox", position, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = safeText(text);
  shape.text.style = { typeface: family, fontSize: style.fontSize || 20, color: style.color || C.ink, bold: Boolean(style.bold), italic: Boolean(style.italic), autoFit: "shrinkTextOnOverflow", alignment: style.alignment || "left" };
  return shape;
}
function rect(slide, position, fill, radius = false) {
  return slide.shapes.add({ geometry: radius ? "roundRect" : "rect", position, fill, line: { fill: fill, width: 0 } });
}
function addFooter(slide, specSlide) {
  textbox(slide, "NARRATIIVE  /  GROWTH BLUEPRINT", { left: 72, top: 684, width: 420, height: 18 }, { fontSize: 11, color: C.muted, bold: true });
  textbox(slide, `${String(specSlide.slide_no).padStart(2, "0")}  /  30`, { left: 1128, top: 684, width: 80, height: 18 }, { fontSize: 11, color: C.muted, alignment: "right" });
}
for (const specSlide of spec.slides) {
  const slide = presentation.slides.add();
  slide.background.fill = specSlide.slide_no === 1 ? C.violet : C.cream;
  if (specSlide.slide_no === 1) {
    rect(slide, { left: 0, top: 0, width: 1280, height: 720 }, C.violet);
    rect(slide, { left: 72, top: 92, width: 18, height: 200 }, C.accent);
    textbox(slide, "NARRATIIVE", { left: 112, top: 96, width: 420, height: 32 }, { fontSize: 18, color: C.white, bold: true });
    textbox(slide, spec.title, { left: 112, top: 180, width: 920, height: 120 }, { fontSize: 48, color: C.white, bold: true });
    textbox(slide, "SAFE INTERNAL STRATEGIC PILOT - NOT COMMISSIONED - NO CONTACT", { left: 112, top: 360, width: 760, height: 30 }, { fontSize: 17, color: "#DDD8E8", bold: true });
    textbox(slide, "A structured Growth Blueprint translated into an editable client-review artefact. Strategic source remains immutable; release requires Matt approval.", { left: 112, top: 510, width: 760, height: 70 }, { fontSize: 22, color: C.white });
    textbox(slide, "01  /  30", { left: 112, top: 660, width: 100, height: 18 }, { fontSize: 11, color: "#DDD8E8", bold: true });
    slide.speakerNotes.textFrame.setText(`${specSlide.source_notes.join("\\n")}\\nInternal pilot disclosure: Rave Coffee did not commission this work.`);
    continue;
  }
  const isStatement = specSlide.layout_type === "statement";
  textbox(slide, "GROWTH BLUEPRINT", { left: 72, top: 42, width: 300, height: 22 }, { fontSize: 12, color: C.accent, bold: true });
  textbox(slide, specSlide.title, { left: 72, top: 78, width: 1100, height: 58 }, { fontSize: 34, color: C.ink, bold: true });
  rect(slide, { left: 72, top: 148, width: 1136, height: 3 }, C.line);
  if (isStatement) {
    textbox(slide, specSlide.takeaway, { left: 110, top: 220, width: 1040, height: 100 }, { fontSize: 36, color: C.violet, bold: true });
    rect(slide, { left: 110, top: 370, width: 8, height: 135 }, C.accent);
    textbox(slide, specSlide.body, { left: 140, top: 370, width: 970, height: 145 }, { fontSize: 22, color: C.ink });
  } else {
    textbox(slide, specSlide.takeaway, { left: 72, top: 190, width: 500, height: 110 }, { fontSize: 30, color: C.violet, bold: true });
    rect(slide, { left: 660, top: 184, width: 548, height: 150 }, C.soft, true);
    textbox(slide, "EVIDENCE / SOURCE REFS", { left: 692, top: 208, width: 450, height: 20 }, { fontSize: 12, color: C.accent, bold: true });
    textbox(slide, `${safeText(specSlide.body).slice(0, 155)}...`, { left: 692, top: 240, width: 470, height: 78 }, { fontSize: 18, color: C.ink });
    textbox(slide, "IMPLICATION", { left: 72, top: 370, width: 250, height: 20 }, { fontSize: 12, color: C.accent, bold: true });
    textbox(slide, specSlide.body, { left: 72, top: 400, width: 760, height: 100 }, { fontSize: 22, color: C.ink });
    rect(slide, { left: 872, top: 390, width: 336, height: 110 }, C.violet, true);
    textbox(slide, specSlide.visual_treatment.toUpperCase(), { left: 902, top: 412, width: 275, height: 20 }, { fontSize: 12, color: "#DDD8E8", bold: true });
    textbox(slide, specSlide.evidence_refs.length ? specSlide.evidence_refs.slice(0, 2).join("\\n") : "Evidence gap retained", { left: 902, top: 444, width: 275, height: 42 }, { fontSize: 14, color: C.white });
  }
  textbox(slide, `SO WHAT?  ${specSlide.takeaway}`, { left: 72, top: 570, width: 1020, height: 46 }, { fontSize: 17, color: C.violet, bold: true });
  addFooter(slide, specSlide);
  slide.speakerNotes.textFrame.setText(`${specSlide.source_notes.join("\\n")}\\nEvidence refs: ${specSlide.evidence_refs.join(", ") || "none supplied"}`);
}
const candidatePath = path.join(outputDir, ".candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const finalPath = path.join(outputDir, "Rave-Growth-Blueprint-SAFE-Pilot.pptx");
const workspaceDir = path.dirname(outputDir);
const reportPath = path.join(workspaceDir, `${path.basename(outputDir)}.validation.json`);
const result = await finalizePresentation({
  workspaceDir,
  candidatePath,
  finalPath,
  pythonExecutable: runtimePython,
  integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-heading-fit"],
  requiredNativeTableOwnerSlides: [],
  fontPolicy: { basis: "design", families: [family] },
  verifyArtifactToolImport: true,
  receiptPath: reportPath,
});
const previewDir = path.join(outputDir, ".rendered-slides");
await fs.mkdir(previewDir, { recursive: true });
for (let index = 0; index < presentation.slides.count; index += 1) {
  const preview = await presentation.export({ slide: presentation.slides.getItem(index), format: "png", scale: 1 });
  await fs.writeFile(path.join(previewDir, `slide-${index + 1}.png`), Buffer.from(await preview.arrayBuffer()));
}
const pdfPath = path.join(outputDir, "Rave-Growth-Blueprint-SAFE-Pilot.pdf");
await fs.writeFile(path.join(outputDir, "presentation-specification.json"), JSON.stringify(spec, null, 2) + "\n");
console.log(JSON.stringify({ pptx: finalPath, pdf: pdfPath, validation: result, slideCount: spec.slides.length }, null, 2));
