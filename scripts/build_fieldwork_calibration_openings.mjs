import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const repository = path.resolve(process.argv[2] || ".");
const skillDir = process.env.SKILL_DIR;
const runtimePython = process.env.RUNTIME_PYTHON;
if (!skillDir || !runtimePython) throw new Error("SKILL_DIR and RUNTIME_PYTHON are required");

const { importRuntimeModule } = await import(pathToFileURL(path.join(skillDir, "container_tools/runtime_helpers.mjs")).href);
const { Presentation, PresentationFile } = await importRuntimeModule("@oai/artifact-tool");
const { resolvePresentationFont, finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
const font = resolvePresentationFont({ availableFonts: ["Aptos Display", "Aptos", "Arial"] });

const cases = [
  {
    id: "rave",
    name: "Rave Coffee",
    file: "FIELDWORK-Rave-five-slide-opening-candidate-v1",
    palette: { ink: "#17130F", paper: "#F5EFE3", signal: "#FFCA05", evidence: "#1738A3", quiet: "#6E665D", white: "#FFFFFF" },
    image: "outputs/rehearsals/issue-477-rave-fieldwork/assets/rave-fieldwork-editorial-background-v1.png",
    current: ["Breadth is proven.", "Progression is not."],
    currentBody: "Rave already has the products, subscriptions, education and service infrastructure. What public evidence cannot show is which entry route turns a new buyer into valuable repeat.",
    opportunity: "Make one customer progression visible — then prove it compounds.",
    equation: ["QUALIFIED ENTRY", "FIRST CHOICE", "90-DAY REPEAT", "PROGRESSION"],
    levers: [
      ["Enter", "Reach people at the moment supermarket coffee stops feeling good enough."],
      ["Choose", "Remove jargon and choice anxiety from the first decision."],
      ["Stay", "Make freshness, delivery and control reliably worth repeating."],
      ["Progress", "Guide the customer from an everyday anchor into discovery."],
    ],
    audienceTitle: "The capable home-coffee upgrader",
    audienceBody: "A plausible audience at a useful commercial moment — but not yet a confirmed Rave segment.",
    audienceDecision: "Validate against CRM cohorts, purchase sequence and customer interviews before campaign design.",
    direction: "PROVE THE PATH.",
    directionBody: "Test one guided route from first choice to repeat to discovery before adding offers, changing positioning or scaling acquisition.",
    sources: {
      1: ["R2", "R3", "R4"], 2: ["R2", "R3", "R6", "R7", "R10"], 3: ["R9", "R10"], 4: ["R5", "R9"], 5: ["R6", "R7", "R9", "R10"],
    },
  },
  {
    id: "katkin",
    name: "KatKin",
    file: "FIELDWORK-KatKin-five-slide-opening-candidate-v1",
    palette: { ink: "#181619", paper: "#FFF4EA", signal: "#FF5B4D", evidence: "#6546D7", quiet: "#6A6267", white: "#FFFFFF" },
    image: "assets/presentation/katkin/hero-cat.png",
    current: ["Science is the difference.", "The journey does not yet prove it."],
    currentBody: "KatKin has capital, scale claims, fresh-food conviction and scientific ambition. Public evidence does not reveal acquisition economics, transition completion or retained-feeder value.",
    opportunity: "Turn science into a decision system customers can use.",
    equation: ["QUALIFIED TRIAL", "TRANSITION", "EARLY CONFIDENCE", "RETENTION"],
    levers: [
      ["Qualify", "Help the right cat parent decide whether fresh feeding fits."],
      ["Transition", "Make the switch explicit, supported and measurable."],
      ["Recognise", "Show owners what useful early progress looks like."],
      ["Retain", "Use evidence and guidance to sustain committed feeding."],
    ],
    audienceTitle: "The committed cat parent at the trial decision",
    audienceBody: "Not the broadest pet audience: the owner willing to change behaviour, but needing confidence that the change is justified and manageable.",
    audienceDecision: "Validate transition friction, reasons for cancellation and retained value before further acquisition spend.",
    direction: "MAKE SCIENCE USABLE.",
    directionBody: "Build and test a customer-facing decision system across trial, transition and early feeding before expanding brand or acquisition investment.",
    sources: {
      1: ["K1", "K2", "K3"], 2: ["K3", "K4", "K5", "K9"], 3: ["K8", "K9"], 4: ["K6", "K8"], 5: ["K3", "K4", "K8", "K9"],
    },
  },
  {
    id: "yardstick",
    name: "The Yardstick Agency",
    file: "FIELDWORK-Yardstick-five-slide-opening-candidate-v1",
    palette: { ink: "#13263A", paper: "#F3F0E8", signal: "#F2B138", evidence: "#28736B", quiet: "#5A6872", white: "#FFFFFF" },
    image: null,
    current: ["Category depth is obvious.", "The buying route is not."],
    currentBody: "Yardstick has a specialist team, recurring content, project services and visible authority. The public offer still reads as a menu for the whole advice profession.",
    opportunity: "Own the moments when an advice firm has to change.",
    equation: ["CHANGE-POINT DEMAND", "DIAGNOSIS", "SERVICE SEQUENCE", "RETAINED PROOF"],
    levers: [
      ["Name", "Define the firm change points where specialist help becomes urgent."],
      ["Diagnose", "Turn broad interest into a specific commercial problem."],
      ["Route", "Sequence the right services instead of presenting a menu."],
      ["Retain", "Use recurring content as evidence of momentum and value."],
    ],
    audienceTitle: "Established advice firms at a change point",
    audienceBody: "A best-fit hypothesis: firms facing succession, capacity, digital or client-selection decisions — not a confirmed pipeline segment.",
    audienceDecision: "Test the hypothesis against enquiry reasons, win rate, service sequence and account value.",
    direction: "LEAD WITH DIAGNOSIS.",
    directionBody: "Reorganise the public offer around named change points and make a diagnostic the primary entry mechanism before wider messaging or campaign work.",
    sources: {
      1: ["Y1", "Y2", "Y3"], 2: ["Y5", "Y6", "Y9"], 3: ["Y8", "Y9"], 4: ["Y6", "Y8"], 5: ["Y2", "Y5", "Y8", "Y9"],
    },
  },
];

const addText = (slide, value, position, style = {}) => {
  const shape = slide.shapes.add({ geometry: "textbox", position, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = String(value);
  shape.text.style = {
    typeface: font,
    fontSize: style.fontSize || 22,
    color: style.color,
    bold: Boolean(style.bold),
    italic: Boolean(style.italic),
    alignment: style.alignment || "left",
    verticalAlignment: style.verticalAlignment || "top",
    autoFit: "shrinkTextOnOverflow",
  };
  return shape;
};
const box = (slide, position, fill, opacity = 100) => {
  const alpha = Math.round(Math.max(0, Math.min(100, opacity)) * 2.55).toString(16).padStart(2, "0").toUpperCase();
  return slide.shapes.add({ geometry: "rect", position, fill: `${fill}${alpha}`, line: { fill: "none", width: 0 } });
};

for (const cfg of cases) {
  const caseDir = path.join(repository, "outputs", "calibrations", "fieldwork-three-business", cfg.id);
  const outputDir = path.join(caseDir, "five-slide-opening");
  const buildDir = path.join(caseDir, ".presentation-build");
  await fs.mkdir(outputDir, { recursive: true });
  await fs.mkdir(buildDir, { recursive: true });
  const argumentEnvelope = JSON.parse(await fs.readFile(path.join(caseDir, "founder-argument.json"), "utf8"));
  const quality = JSON.parse(await fs.readFile(path.join(caseDir, "quality-result.json"), "utf8"));
  const receipt = JSON.parse(await fs.readFile(path.join(caseDir, "execution-receipt.json"), "utf8"));
  const research = JSON.parse(await fs.readFile(path.join(caseDir, "research-case.json"), "utf8"));
  if (!quality.passed || receipt.approval_status !== "pending") throw new Error(`${cfg.id}: accepted argument awaiting approval required`);
  const sourceMap = Object.fromEntries(research.evidence_records.map((record) => [record.evidence_id, record]));
  const sourceNotes = (slideNumber) => cfg.sources[slideNumber].map((id) => {
    const record = sourceMap[id];
    return `${id} [${record.classification}]: ${record.content} Sources: ${(record.source_refs || []).join(", ")}`;
  });
  const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  const C = cfg.palette;
  let imageBytes = null;
  if (cfg.image) imageBytes = await fs.readFile(path.join(repository, cfg.image));
  const image = (slide, position) => slide.images.add({ blob: imageBytes, contentType: "image/png", alt: `${cfg.name} internal calibration editorial image`, fit: "cover", position });
  const footer = (slide, page, status) => {
    addText(slide, `FIELDWORK / ${cfg.name.toUpperCase()} / INTERNAL CALIBRATION`, { left: 62, top: 678, width: 760, height: 17 }, { fontSize: 9, color: C.quiet, bold: true });
    addText(slide, status, { left: 835, top: 678, width: 300, height: 17 }, { fontSize: 9, color: C.quiet, bold: true, alignment: "right" });
    addText(slide, `0${page} / 05`, { left: 1158, top: 678, width: 62, height: 17 }, { fontSize: 9, color: C.quiet, bold: true, alignment: "right" });
  };
  const eyebrow = (slide, text, dark = false) => addText(slide, text, { left: 62, top: 42, width: 720, height: 22 }, { fontSize: 11, color: dark ? C.signal : C.evidence, bold: true });
  const notes = (slide, page) => slide.speakerNotes.textFrame.setText([
    `Internal unsolicited calibration. Not client-approved. Provider message: ${receipt.provider_message_id}.`,
    "Evidence references:",
    ...sourceNotes(page),
    "No external action or presentation handoff was triggered by the commissioning workflow.",
  ].join("\n"));

  // 1 — current position
  {
    const slide = p.slides.add(); slide.background.fill = C.paper;
    if (imageBytes) { image(slide, { left: 690, top: 0, width: 590, height: 720 }); box(slide, { left: 0, top: 0, width: 820, height: 720 }, C.paper, 96); }
    else { box(slide, { left: 1015, top: 0, width: 265, height: 720 }, C.signal); box(slide, { left: 1085, top: 0, width: 12, height: 720 }, C.ink); }
    eyebrow(slide, "01 / THE FOUNDER'S CURRENT POSITION");
    addText(slide, cfg.current[0], { left: 62, top: 112, width: 780, height: 70 }, { fontSize: 47, color: C.ink, bold: true });
    addText(slide, cfg.current[1], { left: 62, top: 184, width: 780, height: 70 }, { fontSize: 47, color: C.evidence, bold: true });
    addText(slide, cfg.currentBody, { left: 62, top: 316, width: 650, height: 128 }, { fontSize: 23, color: C.ink });
    addText(slide, "FOUNDER DECISION", { left: 62, top: 500, width: 240, height: 22 }, { fontSize: 11, color: C.evidence, bold: true });
    addText(slide, argumentEnvelope.founder_argument.argument_moves[0].founder_decision, { left: 62, top: 536, width: 690, height: 78 }, { fontSize: 22, color: C.ink, bold: true });
    footer(slide, 1, "PUBLIC EVIDENCE + OPEN FIRST-PARTY INPUTS"); notes(slide, 1);
  }

  // 2 — opportunity
  {
    const slide = p.slides.add(); slide.background.fill = C.ink;
    if (imageBytes) { image(slide, { left: 0, top: 0, width: 1280, height: 720 }); box(slide, { left: 0, top: 0, width: 1280, height: 720 }, C.ink, 92); }
    eyebrow(slide, "02 / THE COMMERCIAL OPPORTUNITY", true);
    addText(slide, cfg.opportunity, { left: 62, top: 98, width: 1080, height: 105 }, { fontSize: 42, color: C.white, bold: true });
    const widths = [245, 245, 245, 245];
    cfg.equation.forEach((value, index) => {
      const left = 66 + index * 286;
      addText(slide, value, { left, top: 278, width: widths[index], height: 58 }, { fontSize: 17, color: C.signal, bold: true, alignment: "center", verticalAlignment: "middle" });
      if (index < 3) addText(slide, "×", { left: left + 248, top: 283, width: 38, height: 38 }, { fontSize: 30, color: C.white, bold: true, alignment: "center" });
    });
    box(slide, { left: 66, top: 380, width: 1080, height: 7 }, C.signal);
    addText(slide, "A measurable growth relationship — not a financial forecast.", { left: 66, top: 430, width: 1000, height: 58 }, { fontSize: 30, color: C.white, bold: true });
    addText(slide, "Replace every term with first-party baselines; test the sequence; scale only what improves durable customer value.", { left: 66, top: 520, width: 980, height: 62 }, { fontSize: 21, color: C.white });
    footer(slide, 2, "MODELLED MECHANISM / NO £ FORECAST"); notes(slide, 2);
  }

  // 3 — levers
  {
    const slide = p.slides.add(); slide.background.fill = C.paper;
    eyebrow(slide, "03 / THE GROWTH LEVERS");
    addText(slide, "Four levers. One order of operations.", { left: 62, top: 92, width: 920, height: 66 }, { fontSize: 43, color: C.ink, bold: true });
    cfg.levers.forEach((item, index) => {
      const top = 210 + index * 98;
      addText(slide, `0${index + 1}`, { left: 62, top, width: 54, height: 34 }, { fontSize: 17, color: C.evidence, bold: true });
      addText(slide, item[0].toUpperCase(), { left: 142, top, width: 175, height: 34 }, { fontSize: 17, color: C.ink, bold: true });
      addText(slide, item[1], { left: 330, top: top - 4, width: 820, height: 60 }, { fontSize: 21, color: C.ink });
    });
    footer(slide, 3, "ASSUMPTION-LED / VALIDATE BEFORE SCALE"); notes(slide, 3);
  }

  // 4 — audience
  {
    const slide = p.slides.add(); slide.background.fill = C.signal;
    eyebrow(slide, "04 / THE AUDIENCE OPPORTUNITY");
    addText(slide, cfg.audienceTitle, { left: 62, top: 104, width: 1080, height: 94 }, { fontSize: 47, color: C.ink, bold: true });
    addText(slide, cfg.audienceBody, { left: 62, top: 250, width: 820, height: 118 }, { fontSize: 29, color: C.ink, bold: true });
    box(slide, { left: 62, top: 428, width: 1080, height: 3 }, C.ink);
    addText(slide, "EVIDENCE REQUIRED", { left: 62, top: 468, width: 250, height: 22 }, { fontSize: 11, color: C.evidence, bold: true });
    addText(slide, cfg.audienceDecision, { left: 62, top: 510, width: 1010, height: 72 }, { fontSize: 23, color: C.ink });
    footer(slide, 4, "AUDIENCE HYPOTHESIS / NOT A VERIFIED SEGMENT"); notes(slide, 4);
  }

  // 5 — direction
  {
    const slide = p.slides.add(); slide.background.fill = C.paper;
    if (imageBytes) { image(slide, { left: 745, top: 0, width: 535, height: 720 }); box(slide, { left: 0, top: 0, width: 880, height: 720 }, C.paper, 96); }
    else { box(slide, { left: 0, top: 0, width: 24, height: 720 }, C.signal); box(slide, { left: 1110, top: 0, width: 170, height: 720 }, C.evidence); }
    eyebrow(slide, "05 / THE STRATEGIC DIRECTION");
    addText(slide, cfg.direction, { left: 62, top: 114, width: 890, height: 90 }, { fontSize: 61, color: C.ink, bold: true });
    addText(slide, cfg.directionBody, { left: 62, top: 246, width: 760, height: 128 }, { fontSize: 30, color: C.evidence, bold: true });
    addText(slide, "THE TRADE-OFF", { left: 62, top: 446, width: 210, height: 22 }, { fontSize: 11, color: C.evidence, bold: true });
    addText(slide, argumentEnvelope.founder_argument.strategic_recommendation.tradeoffs, { left: 62, top: 482, width: 770, height: 86 }, { fontSize: 20, color: C.ink });
    addText(slide, "MATT APPROVAL REQUIRED BEFORE FULL FIELDWORK PRODUCTION", { left: 62, top: 616, width: 720, height: 22 }, { fontSize: 12, color: C.evidence, bold: true });
    footer(slide, 5, "CANDIDATE DIRECTION / HUMAN GATE"); notes(slide, 5);
  }

  for (let index = 0; index < p.slides.count; index += 1) {
    const png = await p.export({ slide: p.slides.getItem(index), format: "png", scale: 1 });
    await fs.writeFile(path.join(buildDir, `slide-${String(index + 1).padStart(2, "0")}.png`), Buffer.from(await png.arrayBuffer()));
  }
  const candidatePath = path.join(buildDir, `${cfg.file}-draft.pptx`);
  await (await PresentationFile.exportPptx(p)).save(candidatePath);
  const finalPath = path.join(outputDir, `${cfg.file}.pptx`);
  const validationPath = path.join(buildDir, "presentation-validation.json");
  await finalizePresentation({
    workspaceDir: caseDir,
    candidatePath,
    finalPath,
    explicitTotalSlideCount: 5,
    requiredNativeTableOwnerSlides: [],
    requiredNativeChartOwnerSlides: [],
    pythonExecutable: runtimePython,
    integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"),
    layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"),
    layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-heading-fit"],
    fontPolicy: { basis: "design", families: [font] },
    verifyArtifactToolImport: true,
    receiptPath: validationPath,
  });
  await fs.writeFile(path.join(outputDir, "render-receipt.json"), JSON.stringify({
    pptx: finalPath,
    validation_receipt: validationPath,
    slide_count: 5,
    founder_argument_artifact: path.join(caseDir, "founder-argument.json"),
    provider_message_id: receipt.provider_message_id,
    internal_only: true,
    client_approved: false,
    production_default_changed: false,
  }, null, 2) + "\n");
}

console.log(JSON.stringify({ presentations: cases.map((cfg) => cfg.file), font }, null, 2));
