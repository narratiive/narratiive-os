import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

const workspaceDir = path.resolve(process.argv[2] || ".");
const outputDir = path.join(workspaceDir, "outputs", "prototypes", "rave-sketchbook");
const buildDir = path.join(workspaceDir, ".presentation-build");
const assetDir = path.join(outputDir, "assets");
const skillDir = process.env.SKILL_DIR;
const runtimePython = process.env.RUNTIME_PYTHON;
if (!skillDir || !runtimePython) throw new Error("SKILL_DIR and RUNTIME_PYTHON are required");

await fs.mkdir(buildDir, { recursive: true });
const { importRuntimeModule } = await import(pathToFileURL(path.join(skillDir, "container_tools/runtime_helpers.mjs")).href);
const { Presentation, PresentationFile } = await importRuntimeModule("@oai/artifact-tool");
const { resolvePresentationFont, finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
resolvePresentationFont({ availableFonts: ["Arial"] });
const family = "Arial";
const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });

const C = {
  ink: "#17130F",
  paper: "#FAF5F0",
  yellow: "#FFC700",
  white: "#FFFFFF",
  roast: "#6B351F",
  pale: "#E9E0D2",
  muted: "#726A61",
};
const images = {
  doormat: {
    bytes: await fs.readFile(path.join(assetDir, "doormat-delivery-illustration-v1.png")),
    alt: "Creative illustration of an unbranded yellow coffee pouch being collected from a white doormat in warm morning light",
  },
  audience: {
    bytes: await fs.readFile(path.join(assetDir, "upgrader-audience-illustration-v1.png")),
    alt: "Creative illustration of a home coffee enthusiast making pour-over coffee in a warm lived-in kitchen",
  },
  kitchen: {
    bytes: await fs.readFile(path.join(assetDir, "rave-kitchen-visual-world-v1.png")),
    alt: "Creative visual reference: yellow coffee pouch and white mug in a warm domestic kitchen",
  },
  background: {
    bytes: await fs.readFile(path.join(assetDir, "rave-editorial-background-v1.png")),
    alt: "Internal Rave editorial visual with coffee still life and a yellow path",
  },
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
const addBox = (slide, position, fill, line = "none", width = 0) => slide.shapes.add({
  geometry: "rect",
  position,
  fill,
  line: { fill: line, width },
});
const addImage = (slide, image, position, fit = "cover") => slide.images.add({
  blob: image.bytes,
  contentType: "image/png",
  alt: image.alt,
  fit,
  position,
});
const addRule = (slide, left, top, width, colour = C.ink, height = 2) => addBox(slide, { left, top, width, height }, colour);
const addEyebrow = (slide, section, colour = C.ink) => addText(slide, `SKETCHBOOK / RAVE COFFEE     ${section}`, { left: 58, top: 38, width: 690, height: 19 }, { fontSize: 10, color: colour, bold: true });
const addFooter = (slide, number, evidenceLabel = "SOURCE CREATIVE / INTERNAL") => {
  addText(slide, "INTERNAL / NOT CLIENT APPROVED", { left: 58, top: 684, width: 360, height: 15 }, { fontSize: 9, color: C.muted, bold: true });
  addText(slide, evidenceLabel, { left: 470, top: 684, width: 500, height: 15 }, { fontSize: 9, color: C.muted, bold: true, alignment: "center" });
  addText(slide, `0${number} / 05`, { left: 1150, top: 684, width: 72, height: 15 }, { fontSize: 9, color: C.muted, bold: true, alignment: "right" });
};
const addNotes = (slide, lines) => slide.speakerNotes.textFrame.setText(lines.join("\n"));

// 01 — Creative proposition
{
  const slide = p.slides.add();
  slide.background.fill = C.ink;
  addImage(slide, images.background, { left: 0, top: 0, width: 1280, height: 720 });
  addBox(slide, { left: 0, top: 0, width: 760, height: 720 }, `${C.ink}F2`);
  addEyebrow(slide, "01 / CREATIVE PROPOSITION", C.yellow);
  addText(slide, "SERIOUS\nCOFFEE.", { left: 58, top: 104, width: 610, height: 184 }, { fontSize: 72, color: C.white, bold: true });
  addText(slide, "ZERO\nSNOBBERY.", { left: 58, top: 282, width: 610, height: 184 }, { fontSize: 72, color: C.yellow, bold: true });
  addRule(slide, 60, 496, 108, C.yellow, 7);
  addText(slide, "Excellent coffee, explained like a knowledgeable friend — so a better morning never feels like joining a club.", { left: 58, top: 532, width: 610, height: 104 }, { fontSize: 24, color: C.white, bold: true });
  addFooter(slide, 1, "CAMPAIGN WORLD V3 / CREATIVE NORTH STAR");
  addNotes(slide, [
    "Source: NOS-CAMPAIGNWORLD-RAVE-v3, Creative North Star and emotional job.",
    "The proposition is source creative, not current client approval or a verified market claim.",
    "Photography is internal AI-generated creative illustration; it does not depict Rave products or customers.",
  ]);
}

// 02 — Audience profile
{
  const slide = p.slides.add();
  slide.background.fill = C.paper;
  addImage(slide, images.audience, { left: 710, top: 0, width: 570, height: 720 });
  addBox(slide, { left: 0, top: 0, width: 760, height: 720 }, `${C.paper}F7`);
  addEyebrow(slide, "02 / AUDIENCE PROFILE");
  addText(slide, "THE UPGRADER", { left: 58, top: 98, width: 620, height: 70 }, { fontSize: 49, bold: true });
  addText(slide, "A better morning, not a coffee credential.", { left: 58, top: 174, width: 590, height: 78 }, { fontSize: 30, color: C.roast, bold: true });
  const rows = [
    ["WANTS", "Café-quality coffee at home — without turning it into a hobby."],
    ["HESITATES", "Too much choice, jargon, price doubt and fear of buying the wrong thing."],
    ["MOVES WHEN", "A human voice makes the first choice obvious and the next step low-risk."],
  ];
  rows.forEach((row, i) => {
    const top = 314 + i * 102;
    addText(slide, row[0], { left: 58, top, width: 130, height: 24 }, { fontSize: 11, color: C.roast, bold: true });
    addText(slide, row[1], { left: 190, top: top - 5, width: 466, height: 68 }, { fontSize: 21, bold: true });
    if (i < rows.length - 1) addRule(slide, 190, top + 76, 460, C.pale, 2);
  });
  addBox(slide, { left: 886, top: 570, width: 304, height: 70 }, C.yellow);
  addText(slide, "SOURCE HYPOTHESIS\nVALIDATE WITH REAL CUSTOMERS", { left: 906, top: 587, width: 264, height: 42 }, { fontSize: 12, bold: true, alignment: "center" });
  addFooter(slide, 2, "SOURCE HYPOTHESIS / VALIDATION REQUIRED");
  addNotes(slide, [
    "Source: NOS-CAMPAIGNWORLD-RAVE-v3 audience section.",
    "The Upgrader is a source hypothesis, not a verified Rave customer segment. Age, behaviours and barriers require first-party validation.",
    "Portrait is internal AI-generated creative illustration and does not depict a real Rave customer.",
  ]);
}

// 03 — Visual world and art direction
{
  const slide = p.slides.add();
  slide.background.fill = C.ink;
  addImage(slide, images.kitchen, { left: 0, top: 0, width: 1280, height: 460 });
  addBox(slide, { left: 0, top: 0, width: 1280, height: 94 }, `${C.ink}D9`);
  addEyebrow(slide, "03 / VISUAL WORLD + ART DIRECTION", C.yellow);
  addText(slide, "MORNING, NOT THEATRE.", { left: 58, top: 104, width: 720, height: 74 }, { fontSize: 48, color: C.white, bold: true });
  addBox(slide, { left: 0, top: 460, width: 1280, height: 260 }, C.ink);
  addText(slide, "LIVED-IN", { left: 58, top: 506, width: 190, height: 24 }, { fontSize: 12, color: C.yellow, bold: true });
  addText(slide, "Domestic kitchens. Natural light. A real morning already in progress.", { left: 58, top: 542, width: 340, height: 76 }, { fontSize: 20, color: C.white, bold: true });
  addText(slide, "LEGIBLE", { left: 462, top: 506, width: 190, height: 24 }, { fontSize: 12, color: C.yellow, bold: true });
  addText(slide, "One hero element. Product clear. Yellow present in every asset.", { left: 462, top: 542, width: 326, height: 76 }, { fontSize: 20, color: C.white, bold: true });
  addText(slide, "NEVER", { left: 850, top: 506, width: 190, height: 24 }, { fontSize: 12, color: C.yellow, bold: true });
  addText(slide, "Hessian. Coffee cherries. Latte art. Moody roastery. Barista theatre.", { left: 850, top: 542, width: 350, height: 76 }, { fontSize: 20, color: C.white, bold: true });
  addBox(slide, { left: 972, top: 378, width: 54, height: 54 }, C.yellow, C.white, 2);
  addBox(slide, { left: 1036, top: 378, width: 54, height: 54 }, C.paper, C.white, 2);
  addBox(slide, { left: 1100, top: 378, width: 54, height: 54 }, C.ink, C.white, 2);
  addBox(slide, { left: 1164, top: 378, width: 54, height: 54 }, C.roast, C.white, 2);
  addFooter(slide, 3, "CAMPAIGN WORLD V3 / CREATIVE ILLUSTRATION");
  addNotes(slide, [
    "Source: NOS-CAMPAIGNWORLD-RAVE-v3 visual world, colour, composition and anti-reference guidance.",
    "The image is an internal AI-generated art-direction reference, not client photography or a representation of current Rave packaging.",
    "Rave Yellow #FFC700 is preserved as the recurring brand signal.",
  ]);
}

// 04 — Campaign territory
{
  const slide = p.slides.add();
  slide.background.fill = C.yellow;
  addEyebrow(slide, "04 / CAMPAIGN TERRITORY");
  addText(slide, "THE ANTI-SNOB", { left: 58, top: 92, width: 740, height: 66 }, { fontSize: 50, bold: true });
  addText(slide, "Make category theatre visible — then make Rave's directness feel like relief.", { left: 58, top: 164, width: 736, height: 72 }, { fontSize: 26, bold: true });
  addBox(slide, { left: 58, top: 286, width: 742, height: 294 }, C.ink, C.white, 3);
  addText(slide, "TASTING NOTES:\nTHEATRE.", { left: 92, top: 322, width: 660, height: 102 }, { fontSize: 43, color: C.white, bold: true });
  addText(slide, "ROAST DATE:\nEVERYTHING.", { left: 92, top: 444, width: 660, height: 102 }, { fontSize: 43, color: C.yellow, bold: true });
  addText(slide, "THE REPEATABLE CONSTRUCTION", { left: 858, top: 286, width: 300, height: 22 }, { fontSize: 11, color: C.roast, bold: true });
  addText(slide, "1. Name the convention.\n\n2. Cut through it.\n\n3. Replace it with one useful truth.", { left: 858, top: 334, width: 326, height: 176 }, { fontSize: 23, bold: true });
  addRule(slide, 858, 538, 82, C.roast, 6);
  addText(slide, "Distinctive by voice. Useful by design.", { left: 858, top: 563, width: 324, height: 54 }, { fontSize: 20, color: C.roast, bold: true });
  addFooter(slide, 4, "SOURCE CREATIVE / CREATIVE ILLUSTRATION");
  addNotes(slide, [
    "Source: NOS-CAMPAIGNWORLD-RAVE-v3, Territory 1: The Anti-Snob and Asset 05 type-card direction.",
    "Campaign language is an internal creative proposition, not a substantiated comparative product claim.",
    "Before external use, copy requires product, legal and brand review against current Rave evidence.",
  ]);
}

// 05 — Campaign executions and applications
{
  const slide = p.slides.add();
  slide.background.fill = C.paper;
  addEyebrow(slide, "05 / EXECUTIONS + APPLICATIONS");
  addText(slide, "ONE WORLD. THREE WAYS IN.", { left: 58, top: 86, width: 960, height: 66 }, { fontSize: 46, bold: true });
  addText(slide, "Type creates recognition. Delivery makes freshness tangible. Guidance removes the first-choice barrier.", { left: 58, top: 152, width: 1010, height: 60 }, { fontSize: 23, color: C.roast, bold: true });

  // Social type card
  addText(slide, "ORGANIC SOCIAL", { left: 58, top: 246, width: 250, height: 18 }, { fontSize: 10, color: C.muted, bold: true });
  addBox(slide, { left: 58, top: 276, width: 300, height: 300 }, C.yellow, C.white, 4);
  addText(slide, "NO TASTING\nNOTES.\n\nJUST GREAT\nCOFFEE.", { left: 84, top: 310, width: 248, height: 240 }, { fontSize: 31, bold: true, alignment: "center", verticalAlignment: "middle" });

  // Paid-social delivery execution
  addText(slide, "PAID SOCIAL", { left: 390, top: 246, width: 250, height: 18 }, { fontSize: 10, color: C.muted, bold: true });
  addImage(slide, images.doormat, { left: 390, top: 276, width: 300, height: 300 });
  addBox(slide, { left: 406, top: 458, width: 268, height: 98 }, `${C.ink}E8`);
  addText(slide, "ROASTED TUESDAY 7AM.\nAT YOUR DOOR THURSDAY.", { left: 422, top: 476, width: 236, height: 60 }, { fontSize: 17, color: C.white, bold: true, alignment: "center" });

  // Quiz entry execution
  addText(slide, "QUIZ ENTRY", { left: 722, top: 246, width: 250, height: 18 }, { fontSize: 10, color: C.muted, bold: true });
  addBox(slide, { left: 722, top: 276, width: 500, height: 300 }, C.white, C.ink, 3);
  addBox(slide, { left: 722, top: 276, width: 210, height: 300 }, C.yellow);
  addText(slide, "NOT SURE\nWHERE TO\nSTART?", { left: 746, top: 326, width: 162, height: 164 }, { fontSize: 30, bold: true, alignment: "center", verticalAlignment: "middle" });
  addText(slide, "TAKE THE QUIZ.", { left: 964, top: 330, width: 220, height: 74 }, { fontSize: 30, bold: true });
  addText(slide, "A low-pressure first step into better coffee.", { left: 964, top: 420, width: 214, height: 58 }, { fontSize: 18, color: C.roast, bold: true });
  addBox(slide, { left: 964, top: 510, width: 184, height: 38 }, C.ink);
  addText(slide, "FIND MY COFFEE  →", { left: 976, top: 520, width: 160, height: 18 }, { fontSize: 11, color: C.white, bold: true, alignment: "center" });

  addText(slide, "Illustrative timestamp — replace only with verified operations data.", { left: 390, top: 594, width: 300, height: 28 }, { fontSize: 9, color: C.muted, italic: true, alignment: "center" });
  addText(slide, "Prototype interaction — verify current quiz journey before use.", { left: 722, top: 594, width: 500, height: 28 }, { fontSize: 9, color: C.muted, italic: true, alignment: "center" });
  addFooter(slide, 5, "CREATIVE ILLUSTRATION / NOT LIVE MEDIA");
  addNotes(slide, [
    "Source: NOS-CAMPAIGNWORLD-RAVE-v3, Assets 03, 05 and 12 plus channel applications.",
    "All three executions are internal creative illustrations. They are not published, activated, approved or performance-tested.",
    "The delivery timestamp is illustrative and must be replaced with verified operational data. The quiz CTA must be checked against Rave's current live journey before external use.",
  ]);
}

for (let i = 0; i < p.slides.count; i += 1) {
  const png = await p.export({ slide: p.slides.getItem(i), format: "png", scale: 1 });
  await fs.writeFile(path.join(buildDir, `slide-${String(i + 1).padStart(2, "0")}.png`), Buffer.from(await png.arrayBuffer()));
}

const candidatePath = path.join(buildDir, "candidate.pptx");
await (await PresentationFile.exportPptx(p)).save(candidatePath);
const finalPath = path.join(outputDir, "INTERNAL-Rave-SKETCHBOOK-canonical-prototype-v2.pptx");
const receiptPath = path.join(buildDir, "presentation-validation-v2.json");
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

const sourceBytes = await fs.readFile(finalPath);
const privateValidation = JSON.parse(await fs.readFile(receiptPath, "utf8"));
await fs.writeFile(path.join(outputDir, "render-receipt-v2.json"), JSON.stringify({
  artefact: "Rave SKETCHBOOK canonical template prototype",
  version: "1.0.0-candidate",
  source_presentation: path.basename(finalPath),
  source_presentation_sha256: createHash("sha256").update(sourceBytes).digest("hex"),
  private_validation_receipt: ".presentation-build/presentation-validation-v2.json (not committed)",
  validation: {
    package_integrity: privateValidation.packageIntegrity.finding_count === 0 ? "pass" : "fail",
    layout_geometry: privateValidation.presentationLayout.finding_count === 0 ? "pass" : "fail",
    heading_fit: privateValidation.presentationLayout.finding_count === 0 ? "pass" : "fail",
    font_policy: privateValidation.fontSelection.passed ? "pass" : "fail",
    observed_font: family,
  },
  slide_count: 5,
  editable: true,
  internal_only: true,
  client_approved: false,
  live_media_activation: false,
  generated_visuals: Object.keys(images),
}, null, 2) + "\n");

console.log(JSON.stringify({ finalPath, receiptPath, buildDir }, null, 2));
