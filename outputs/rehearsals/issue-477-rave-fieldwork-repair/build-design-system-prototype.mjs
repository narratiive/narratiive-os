import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const workspaceDir = path.resolve(process.argv[2]);
const outputDir = path.join(workspaceDir, "design-system-prototype");
const buildDir = path.join(workspaceDir, ".design-system-build");
const skillDir = process.env.SKILL_DIR;
const runtimePython = process.env.RUNTIME_PYTHON;
if (!skillDir || !runtimePython) throw new Error("SKILL_DIR and RUNTIME_PYTHON are required");

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(buildDir, { recursive: true });
const { importRuntimeModule } = await import(pathToFileURL(path.join(skillDir, "container_tools/runtime_helpers.mjs")).href);
const { Presentation, PresentationFile } = await importRuntimeModule("@oai/artifact-tool");
const { resolvePresentationFont, finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
const family = resolvePresentationFont({ availableFonts: ["Arial", "Aptos"] });
const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const imagePath = path.resolve(workspaceDir, "..", "issue-477-rave-fieldwork", "assets", "rave-fieldwork-editorial-background-v1.png");
const imageBytes = await fs.readFile(imagePath);

const C = {
  ink: "#17130F",
  paper: "#F5EFE3",
  yellow: "#FFCA05",
  blue: "#1738A3",
  roast: "#6B351F",
  white: "#FFFFFF",
  grey: "#6E665D",
  pale: "#E6DDCF",
};
const addText = (slide, value, position, style = {}) => {
  const shape = slide.shapes.add({ geometry: "textbox", position, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = String(value);
  shape.text.style = {
    typeface: family,
    fontSize: style.fontSize || 22,
    color: style.color || C.ink,
    bold: Boolean(style.bold),
    italic: Boolean(style.italic),
    alignment: style.alignment || "left",
    verticalAlignment: style.verticalAlignment || "top",
    autoFit: "shrinkTextOnOverflow",
  };
  return shape;
};
const addBox = (slide, position, fill, opacity = 100) => {
  const alpha = Math.round(Math.max(0, Math.min(100, opacity)) * 2.55).toString(16).padStart(2, "0").toUpperCase();
  return slide.shapes.add({ geometry: "rect", position, fill: `${fill}${alpha}`, line: { fill: "none", width: 0 } });
};
const addImage = (slide, position, fit = "cover") => slide.images.add({
  blob: imageBytes,
  contentType: "image/png",
  alt: "Internal AI-generated editorial coffee still life with a yellow paper path",
  fit,
  position,
});
const footer = (slide, page, product, status = "INTERNAL PROTOTYPE") => {
  addText(slide, `${product} / RAVE EXAMPLE / ${status}`, { left: 64, top: 680, width: 720, height: 16 }, { fontSize: 9, color: C.grey, bold: true });
  addText(slide, `0${page} / 05`, { left: 1150, top: 680, width: 70, height: 16 }, { fontSize: 9, color: C.grey, bold: true, alignment: "right" });
};
const note = (slide, lines) => slide.speakerNotes.textFrame.setText(lines.join("\n"));

// 1 — cover
{
  const slide = p.slides.add();
  slide.background.fill = C.ink;
  addImage(slide, { left: 0, top: 0, width: 1280, height: 720 });
  addBox(slide, { left: 0, top: 0, width: 1280, height: 720 }, C.ink, 60);
  addBox(slide, { left: 0, top: 0, width: 760, height: 720 }, C.ink, 94);
  addText(slide, "RAVE COFFEE / CLIENT WORLD PROTOTYPE", { left: 64, top: 54, width: 620, height: 22 }, { fontSize: 11, color: C.yellow, bold: true });
  addText(slide, "One client world.\nTwo different jobs.", { left: 64, top: 150, width: 700, height: 170 }, { fontSize: 55, color: C.white, bold: true });
  addText(slide, "FIELDWORK explains the choice.\nSKETCHBOOK makes the choice tangible.", { left: 64, top: 374, width: 620, height: 100 }, { fontSize: 26, color: C.white });
  addText(slide, "Proposed design system for internal review", { left: 64, top: 600, width: 520, height: 25 }, { fontSize: 14, color: C.yellow, bold: true });
  footer(slide, 1, "FIELDWORK + SKETCHBOOK");
  note(slide, ["Internal unsolicited Rave example only.", "The background is AI-generated and not a Rave-owned asset.", "This prototype defines a shared visual grammar; it is not client-approved brand work."]);
}

// 2 — shared system
{
  const slide = p.slides.add();
  slide.background.fill = C.paper;
  addText(slide, "SHARED CLIENT SYSTEM", { left: 64, top: 50, width: 420, height: 22 }, { fontSize: 11, color: C.blue, bold: true });
  addText(slide, "A clear path through serious coffee", { left: 64, top: 92, width: 950, height: 65 }, { fontSize: 44, bold: true });
  addText(slide, "The identity stays consistent. The amount of evidence and expression changes with the product.", { left: 64, top: 174, width: 900, height: 52 }, { fontSize: 21 });
  const swatches = [
    [C.ink, "INK", "#17130F"],
    [C.paper, "PAPER", "#F5EFE3"],
    [C.yellow, "SIGNAL", "#FFCA05"],
    [C.blue, "EVIDENCE", "#1738A3"],
    [C.roast, "ROAST", "#6B351F"],
  ];
  swatches.forEach((item, i) => {
    const left = 64 + i * 222;
    addBox(slide, { left, top: 280, width: 188, height: 96 }, item[0]);
    addText(slide, item[1], { left, top: 394, width: 188, height: 22 }, { fontSize: 12, bold: true });
    addText(slide, item[2], { left, top: 420, width: 188, height: 22 }, { fontSize: 12, color: C.grey });
  });
  addText(slide, "TYPE", { left: 64, top: 506, width: 120, height: 20 }, { fontSize: 11, color: C.blue, bold: true });
  addText(slide, "Arial Bold for decisions", { left: 64, top: 538, width: 390, height: 44 }, { fontSize: 29, bold: true });
  addText(slide, "Arial Regular for evidence, explanation and captions", { left: 64, top: 590, width: 520, height: 34 }, { fontSize: 18 });
  addText(slide, "MEMORY DEVICE", { left: 726, top: 506, width: 190, height: 20 }, { fontSize: 11, color: C.blue, bold: true });
  addBox(slide, { left: 726, top: 548, width: 430, height: 18 }, C.yellow);
  addText(slide, "The yellow path marks progression and choice", { left: 726, top: 586, width: 430, height: 36 }, { fontSize: 18, bold: true });
  footer(slide, 2, "FIELDWORK + SKETCHBOOK");
  note(slide, ["Palette and type are prototype specifications, not extracted Rave brand standards.", "Yellow carries direction; cobalt carries evidence.", "Arial was selected for portability and reliable rendering."]);
}

// 3 — FIELDWORK prototype
{
  const slide = p.slides.add();
  slide.background.fill = C.paper;
  addBox(slide, { left: 0, top: 0, width: 18, height: 720 }, C.yellow);
  addText(slide, "FIELDWORK / ARGUMENT PAGE", { left: 64, top: 50, width: 420, height: 22 }, { fontSize: 11, color: C.blue, bold: true });
  addText(slide, "Rave has many routes to repeat.\nIt does not yet know which one compounds.", { left: 64, top: 96, width: 900, height: 110 }, { fontSize: 43, bold: true });
  addText(slide, "CURRENT POSITION", { left: 64, top: 258, width: 220, height: 20 }, { fontSize: 11, color: C.blue, bold: true });
  addText(slide, "Coffee Club, Subscribe & Save, rewards, wholesale and a wide product range already exist. Public evidence does not reveal which entry route creates stronger repeat purchase and contribution.", { left: 64, top: 296, width: 550, height: 120 }, { fontSize: 22 });
  addText(slide, "FOUNDER DECISION", { left: 712, top: 258, width: 220, height: 20 }, { fontSize: 11, color: C.blue, bold: true });
  addText(slide, "Release channel, repeat and contribution data before choosing where to scale.", { left: 712, top: 296, width: 430, height: 110 }, { fontSize: 30, bold: true });
  addBox(slide, { left: 64, top: 484, width: 1080, height: 6 }, C.yellow);
  addText(slide, "Qualified entry  ×  first choice  ×  early repeat  ×  progression", { left: 64, top: 522, width: 900, height: 48 }, { fontSize: 25, bold: true });
  addText(slide, "MODELLED MECHANISM / NOT A FORECAST", { left: 64, top: 594, width: 420, height: 20 }, { fontSize: 11, color: C.blue, bold: true });
  footer(slide, 3, "FIELDWORK", "EXPERIMENTAL ARGUMENT");
  note(slide, ["Based on the accepted experimental founder argument, message msg_011Cg9hDhGoFhwkcU34gMtok.", "The Rave research pack is archived and requires current revalidation.", "No financial forecast or client approval is implied."]);
}

// 4 — SKETCHBOOK prototype
{
  const slide = p.slides.add();
  slide.background.fill = C.ink;
  addImage(slide, { left: 0, top: 0, width: 1280, height: 720 });
  addBox(slide, { left: 0, top: 0, width: 1280, height: 720 }, C.ink, 32);
  addBox(slide, { left: 0, top: 0, width: 680, height: 720 }, C.ink, 92);
  addText(slide, "SKETCHBOOK / TERRITORY PROTOTYPE", { left: 64, top: 50, width: 450, height: 22 }, { fontSize: 11, color: C.yellow, bold: true });
  addText(slide, "A better cup,\nwithout the ceremony", { left: 64, top: 116, width: 620, height: 150 }, { fontSize: 51, color: C.white, bold: true });
  addText(slide, "Creative illustration", { left: 64, top: 306, width: 260, height: 28 }, { fontSize: 15, color: C.yellow, bold: true });
  addText(slide, "The yellow path turns the strategic progression into a recognisable visual world: familiar coffee, a clearer route and permission to keep exploring.", { left: 64, top: 360, width: 520, height: 130 }, { fontSize: 24, color: C.white });
  addText(slide, "PHOTOGRAPHY", { left: 64, top: 540, width: 160, height: 20 }, { fontSize: 11, color: C.yellow, bold: true });
  addText(slide, "Tactile surfaces, crisp daylight, useful negative space", { left: 64, top: 574, width: 520, height: 45 }, { fontSize: 18, color: C.white });
  footer(slide, 4, "SKETCHBOOK", "CREATIVE ILLUSTRATION");
  note(slide, ["Creative territory prototype only; it has not been approved by Rave or Matt.", "The same AI-generated background is reused as a system memory device.", "External release requires rights, product-accuracy and brand approval."]);
}

// 5 — relationship
{
  const slide = p.slides.add();
  slide.background.fill = C.paper;
  addText(slide, "ONE WORLD / TWO JOBS", { left: 64, top: 50, width: 420, height: 22 }, { fontSize: 11, color: C.blue, bold: true });
  addText(slide, "Consistency without sameness", { left: 64, top: 94, width: 760, height: 62 }, { fontSize: 44, bold: true });
  addBox(slide, { left: 64, top: 218, width: 520, height: 8 }, C.blue);
  addText(slide, "FIELDWORK", { left: 64, top: 258, width: 260, height: 36 }, { fontSize: 26, bold: true });
  addText(slide, "Evidence first\nPaper and ink dominate\nYellow marks the decision\nModels remain editable", { left: 64, top: 318, width: 430, height: 180 }, { fontSize: 24 });
  addBox(slide, { left: 696, top: 218, width: 520, height: 8 }, C.yellow);
  addText(slide, "SKETCHBOOK", { left: 696, top: 258, width: 300, height: 36 }, { fontSize: 26, bold: true });
  addText(slide, "Expression first\nPhotography takes more space\nThe path becomes kinetic\nHypotheses stay labelled", { left: 696, top: 318, width: 430, height: 180 }, { fontSize: 24 });
  addText(slide, "Shared across both", { left: 64, top: 558, width: 230, height: 24 }, { fontSize: 12, color: C.blue, bold: true });
  addText(slide, "Palette, type hierarchy, yellow path, crop behaviour, footer, evidence status and approval state", { left: 298, top: 550, width: 858, height: 52 }, { fontSize: 19, bold: true });
  footer(slide, 5, "FIELDWORK + SKETCHBOOK");
  note(slide, ["FIELDWORK and SKETCHBOOK share a client identity while preserving distinct product roles.", "This prototype demonstrates the relationship only; no SKETCHBOOK production pipeline has been built.", "Next decision: approve, revise or reject the shared visual grammar."]);
}

for (let i = 0; i < p.slides.count; i += 1) {
  const png = await p.export({ slide: p.slides.getItem(i), format: "png", scale: 1 });
  await fs.writeFile(path.join(buildDir, `slide-${String(i + 1).padStart(2, "0")}.png`), Buffer.from(await png.arrayBuffer()));
}
const candidatePath = path.join(buildDir, "candidate.pptx");
await (await PresentationFile.exportPptx(p)).save(candidatePath);
const finalPath = path.join(outputDir, "Rave-FIELDWORK-SKETCHBOOK-design-system-prototype-v1.pptx");
const receiptPath = path.join(buildDir, "presentation-validation.json");
await finalizePresentation({
  workspaceDir,
  candidatePath,
  finalPath,
  explicitTotalSlideCount: 5,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  pythonExecutable: runtimePython,
  integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-heading-fit"],
  fontPolicy: { basis: "design", families: [family] },
  verifyArtifactToolImport: true,
  receiptPath,
});
await fs.writeFile(path.join(outputDir, "render-receipt.json"), JSON.stringify({
  pptx: finalPath,
  validation_receipt: receiptPath,
  slide_count: 5,
  source_visual: path.relative(workspaceDir, imagePath),
  internal_only: true,
  client_approved: false,
  sketchbook_pipeline_built: false,
}, null, 2) + "\n");
console.log(JSON.stringify({ finalPath, receiptPath, buildDir }, null, 2));
