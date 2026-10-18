import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const workspaceDir = path.resolve(process.argv[2]);
const outputDir = path.join(workspaceDir, "five-slide-opening");
const buildDir = path.join(workspaceDir, ".presentation-build");
const skillDir = process.env.SKILL_DIR;
const runtimePython = process.env.RUNTIME_PYTHON;
if (!skillDir || !runtimePython) throw new Error("SKILL_DIR and RUNTIME_PYTHON are required");

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(buildDir, { recursive: true });
const { importRuntimeModule } = await import(pathToFileURL(path.join(skillDir, "container_tools/runtime_helpers.mjs")).href);
const { Presentation, PresentationFile } = await importRuntimeModule("@oai/artifact-tool");
const { resolvePresentationFont, finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
const family = resolvePresentationFont({ availableFonts: ["Aptos Display", "Aptos", "Arial"] });
const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const imageBytes = await fs.readFile(path.join(workspaceDir, "assets", "rave-fieldwork-editorial-background-v1.png"));

const C = { ink: "#17130F", cream: "#F5EFE3", yellow: "#FFCA05", blue: "#1738A3", white: "#FFFFFF", grey: "#6E665D", pale: "#E9E0D2" };
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
  blob: imageBytes, contentType: "image/png", alt: "Internal editorial coffee still life with a yellow path", fit, position,
});
const footer = (slide, number, label, source) => {
  addText(slide, `FIELDWORK / RAVE COFFEE / INTERNAL UNSOLICITED EXERCISE`, { left: 62, top: 680, width: 600, height: 16 }, { fontSize: 9, color: C.grey, bold: true });
  addText(slide, `${label}  •  ${source}`, { left: 62, top: 645, width: 1050, height: 24 }, { fontSize: 10, color: C.grey });
  addText(slide, `0${number} / 05`, { left: 1150, top: 680, width: 70, height: 16 }, { fontSize: 9, color: C.grey, bold: true, alignment: "right" });
};
const eyebrow = (slide, value, dark = false) => addText(slide, value, { left: 62, top: 42, width: 720, height: 20 }, { fontSize: 11, color: dark ? C.yellow : C.blue, bold: true });
const note = (slide, lines) => { slide.speakerNotes.textFrame.setText(lines.join("\n")); };

// 1 — current position
{
  const slide = p.slides.add();
  slide.background.fill = C.cream;
  addImage(slide, { left: 610, top: 0, width: 670, height: 720 });
  addBox(slide, { left: 0, top: 0, width: 760, height: 720 }, C.cream, 96);
  eyebrow(slide, "01 / THE FOUNDER'S CURRENT POSITION");
  addText(slide, "Rave has built the pieces.\nThe growth system is still hidden.", { left: 62, top: 102, width: 690, height: 150 }, { fontSize: 45, bold: true });
  addText(slide, "The public evidence shows range, reach and routes to repeat: an accessible speciality offer, Coffee Club, Subscribe & Save, a quiz, gifts, pods and a national wholesale service.", { left: 62, top: 286, width: 620, height: 102 }, { fontSize: 22 });
  addText(slide, "What it cannot show", { left: 62, top: 432, width: 220, height: 22 }, { fontSize: 12, color: C.blue, bold: true });
  addText(slide, "Which route creates profitable repeat — or where growth currently leaks.", { left: 62, top: 472, width: 540, height: 80 }, { fontSize: 29, bold: true });
  footer(slide, 1, "VERIFIED EXTERNAL + OPEN INPUT", "Rave-owned pages revalidated 17 Oct 2026");
  note(slide, ["Verified external: Rave About, Coffee Club, Subscribe & Save, Quiz and Wholesale pages, accessed 17 Oct 2026.", "Open input: revenue, contribution margin, CAC, repeat, churn and channel mix were not supplied.", "No claim is made about Rave's actual growth rate or profitability."]);
}

// 2 — commercial opportunity
{
  const slide = p.slides.add();
  slide.background.fill = C.ink;
  addImage(slide, { left: 0, top: 0, width: 1280, height: 720 });
  addBox(slide, { left: 0, top: 0, width: 1280, height: 720 }, C.ink, 94);
  eyebrow(slide, "02 / THE CREDIBLE 12-MONTH OPPORTUNITY", true);
  addText(slide, "Make growth compound — without pretending we know the answer yet.", { left: 62, top: 96, width: 1040, height: 90 }, { fontSize: 42, color: C.white, bold: true });
  addText(slide, "QUALIFIED REACH", { left: 70, top: 260, width: 220, height: 30 }, { fontSize: 17, color: C.yellow, bold: true });
  addText(slide, "×", { left: 295, top: 247, width: 45, height: 50 }, { fontSize: 34, color: C.white, bold: true, alignment: "center" });
  addText(slide, "FIRST-ORDER\nCONVERSION", { left: 350, top: 246, width: 230, height: 70 }, { fontSize: 17, color: C.yellow, bold: true, alignment: "center" });
  addText(slide, "×", { left: 590, top: 247, width: 45, height: 50 }, { fontSize: 34, color: C.white, bold: true, alignment: "center" });
  addText(slide, "90-DAY\nREPEAT", { left: 645, top: 246, width: 190, height: 70 }, { fontSize: 17, color: C.yellow, bold: true, alignment: "center" });
  addText(slide, "×", { left: 845, top: 247, width: 45, height: 50 }, { fontSize: 34, color: C.white, bold: true, alignment: "center" });
  addText(slide, "VALUE\nPROGRESSION", { left: 900, top: 246, width: 220, height: 70 }, { fontSize: 17, color: C.yellow, bold: true, alignment: "center" });
  addText(slide, "=  MORE CONTRIBUTION", { left: 78, top: 356, width: 1040, height: 70 }, { fontSize: 49, color: C.white, bold: true });
  addText(slide, "This is a lever model, not a forecast. Replace each term with Rave's baseline; test one lever at a time; scale only what improves contribution after fulfilment and retention.", { left: 78, top: 478, width: 1010, height: 76 }, { fontSize: 21, color: C.white });
  footer(slide, 2, "MODELLED — NO FORECAST", "Requires Rave baseline metrics before £ sizing");
  note(slide, ["Modelled opportunity equation only; no revenue forecast or investment budget.", "Required baselines: qualified sessions by source, first-order conversion, 90-day repeat, contribution per order and fulfilment/service cost.", "Scenario outputs must remain conditional and sensitivity-based."]);
}

// 3 — levers
{
  const slide = p.slides.add();
  slide.background.fill = C.cream;
  eyebrow(slide, "03 / THE GROWTH LEVERS");
  addText(slide, "Four levers. One order of operations.", { left: 62, top: 92, width: 870, height: 72 }, { fontSize: 43, bold: true });
  const items = [
    ["01", "ENTER", "Show up at the moment someone decides supermarket coffee is no longer enough."],
    ["02", "CHOOSE", "Use the quiz and plain-English guidance to remove choice anxiety."],
    ["03", "STAY", "Make freshness, delivery and subscription control consistently trustworthy."],
    ["04", "PROGRESS", "Move people from an everyday anchor to discovery, gifting and rare coffee."],
  ];
  items.forEach((item, i) => {
    const top = 210 + i * 92;
    addText(slide, item[0], { left: 62, top, width: 52, height: 32 }, { fontSize: 17, color: C.blue, bold: true });
    addText(slide, item[1], { left: 138, top, width: 150, height: 32 }, { fontSize: 17, bold: true });
    addText(slide, item[2], { left: 320, top: top - 2, width: 790, height: 58 }, { fontSize: 21 });
  });
  addText(slide, "GATE BEFORE SCALE", { left: 928, top: 55, width: 230, height: 25 }, { fontSize: 10, color: C.blue, bold: true, alignment: "right" });
  addText(slide, "Proof and reliability first.", { left: 888, top: 92, width: 290, height: 64 }, { fontSize: 27, color: C.blue, bold: true, alignment: "right" });
  footer(slide, 3, "INTERPRETATION + HYPOTHESIS", "Mechanisms derived from current offer architecture");
  note(slide, ["Verified external: Rave currently offers quiz, Coffee Club, Subscribe & Save, gifts, pods and wholesale.", "Interpretation: these can form a progression system.", "Hypothesis: progression will improve contribution and repeat; must be tested with Rave cohorts."]);
}

// 4 — audience
{
  const slide = p.slides.add();
  slide.background.fill = C.yellow;
  eyebrow(slide, "04 / THE AUDIENCE OPPORTUNITY");
  addText(slide, "The Upgrader is the priority hypothesis — not a finished persona.", { left: 62, top: 92, width: 1040, height: 92 }, { fontSize: 42, bold: true });
  addText(slide, "THE MOMENT", { left: 64, top: 246, width: 220, height: 22 }, { fontSize: 11, color: C.blue, bold: true });
  addText(slide, "“My everyday coffee is no longer good enough.”", { left: 64, top: 283, width: 540, height: 92 }, { fontSize: 32, bold: true });
  addText(slide, "THE BARRIER", { left: 676, top: 246, width: 220, height: 22 }, { fontSize: 11, color: C.blue, bold: true });
  addText(slide, "Too much choice. Too much jargon. Too much risk of getting it wrong.", { left: 676, top: 283, width: 500, height: 100 }, { fontSize: 29, bold: true });
  addText(slide, "WHY RAVE MAY WIN", { left: 64, top: 446, width: 220, height: 22 }, { fontSize: 11, color: C.blue, bold: true });
  addText(slide, "Accessible prices, an irreverent voice, human help and a product range that can grow with the customer.", { left: 64, top: 482, width: 1010, height: 78 }, { fontSize: 24 });
  footer(slide, 4, "HYPOTHESIS — VALIDATE", "Directionally supported by public review language and Rave's own offer");
  note(slide, ["This is a priority hypothesis, not a verified segment size or customer truth.", "Directionally supported by archived public review language and current Rave-owned offer architecture.", "Validate with CRM cohorts, search/acquisition source, quiz behaviour, purchase sequence and primary customer interviews."]);
}

// 5 — strategic direction
{
  const slide = p.slides.add();
  slide.background.fill = C.cream;
  addImage(slide, { left: 0, top: 0, width: 1280, height: 720 });
  addBox(slide, { left: 0, top: 0, width: 1280, height: 720 }, C.cream, 62);
  addBox(slide, { left: 0, top: 0, width: 870, height: 720 }, C.cream, 96);
  eyebrow(slide, "05 / THE STRATEGIC DIRECTION");
  addText(slide, "OWN THE UPGRADE.", { left: 62, top: 96, width: 930, height: 92 }, { fontSize: 64, bold: true });
  addText(slide, "Make serious coffee easy to enter, easy to choose — and worth staying for.", { left: 62, top: 200, width: 780, height: 104 }, { fontSize: 34, color: C.blue, bold: true });
  const choices = [
    ["POSITION", "The easiest credible route into better coffee."],
    ["JOURNEY", "One progression: everyday anchor → discovery → frontier."],
    ["PROOF", "Freshness, delivery and value made visible — then measured."],
  ];
  choices.forEach((item, i) => {
    const top = 354 + i * 78;
    addText(slide, item[0], { left: 66, top, width: 150, height: 22 }, { fontSize: 11, color: C.blue, bold: true });
    addText(slide, item[1], { left: 230, top: top - 5, width: 570, height: 44 }, { fontSize: 22, bold: true });
  });
  footer(slide, 5, "PROPOSED DIRECTION — NOT CLIENT APPROVED", "Founder review required before full FIELDWORK production");
  note(slide, ["Proposed strategic direction for internal review only.", "It builds from currently revalidated Rave-owned claims and a frozen archived research pack; it is not a client-approved position.", "Next gate: Matt reviews the argument and requests evidence upgrades before any full presentation."]);
}

for (let i = 0; i < p.slides.count; i += 1) {
  const png = await p.export({ slide: p.slides.getItem(i), format: "png", scale: 1 });
  await fs.writeFile(path.join(buildDir, `slide-${String(i + 1).padStart(2, "0")}.png`), Buffer.from(await png.arrayBuffer()));
}
const candidatePath = path.join(buildDir, "candidate.pptx");
await (await PresentationFile.exportPptx(p)).save(candidatePath);
const finalPath = path.join(outputDir, "FIELDWORK-Rave-five-slide-opening-v3.pptx");
const receiptPath = path.join(buildDir, "presentation-validation-v3.json");
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
  generated_visual: "assets/rave-fieldwork-editorial-background-v1.png",
  internal_only: true,
  client_approved: false,
}, null, 2) + "\n");
console.log(JSON.stringify({ finalPath, receiptPath, buildDir }, null, 2));
