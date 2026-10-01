# Voicebox technical evaluation — 21 August 2026

Status: conditionally suitable for an optional, local pilot

Upstream reviewed: `jamiepine/voicebox` at commit
`51f49dea198384b4eb6087b72c17057c6eb1c1cd` (`main`, 27 July 2026)

## Recommendation

Voicebox is technically credible enough for a consented, non-critical Narratiive
pilot, but not mature enough to become a hard dependency of Tony, OpenClaw, n8n,
or the core workflow runtime. Use the separate, disabled-by-default adapter in
`runtime.voicebox_service`, run Voicebox on loopback, select and benchmark one
engine on Matt's exact hardware, and retain a manual quality and approval gate.

This evaluation did not download multi-gigabyte model weights or perform a
controlled MOS/speaker-similarity listening study. Quality conclusions are based
on the inspected implementation, model families, upstream documentation, and
issue evidence. A Narratiive adoption decision therefore requires an acoustic
pilot using consented recordings and representative scripts.

## Maintenance and maturity

- The project is young (created 25 January 2026), popular (approximately 51,000
  stars and 6,300 forks at review time), and actively accepting changes.
- The reviewed `main` had recent merged work through 27 July and the repository
  was pushed on 9 August. The latest packaged release remained `v0.5.0`, published
  25 April, so `main` and the installable release differ materially.
- The project had 492 open issues and 154 open pull requests at review time. That
  demonstrates activity, but also a large triage and reliability burden.
- Current reports cover model downloads, GPU detection, Apple Silicon crashes,
  CPU memory growth, clipping/sample handling, truncation, and language-specific
  quality. Treat platform and engine combinations as separate support targets.

Verdict: actively maintained, fast-moving, and pre-1.0; pin a tested release or
commit and do not follow `latest` automatically in production.

## Architecture and automation surface

Voicebox is a Tauri desktop application with React/Vite front ends and a Python
FastAPI service. The backend has domain routers, services, SQLAlchemy/SQLite
persistence, a serial asynchronous generation queue, SSE status, model-specific
backend adapters, audio effects, local Whisper transcription, REST endpoints,
and a FastMCP server mounted at `/mcp`.

Useful automation contracts include:

- `GET /health` and model status/download routes;
- voice profile create/list/sample/import/export routes;
- `POST /speak` for profile-name/id resolution;
- `POST /generate`, generation history/status, and audio download;
- MCP tools for speak, transcribe, captures, and profile discovery.

The surface is suitable for local automation. It is not an OpenAI-compatible TTS
API, its generation response is asynchronous, and upstream contracts are not yet
versioned as a stable public API. Narratiive should keep its adapter narrow and
covered by contract tests.

## Model stack and expected quality

| Engine | Role in a Narratiive pilot | Main caution |
| --- | --- | --- |
| Qwen3-TTS 1.7B / 0.6B | Best first candidate for multilingual zero-shot cloning and instruction control | Heavy model/load path; test pronunciation, similarity, and latency |
| Chatterbox Multilingual | Candidate when language coverage matters most | More variable language reports and dependency complexity |
| Chatterbox Turbo | Faster English output and expressive tags | Tags are engine-specific; not a general delivery-control contract |
| LuxTTS | Lightweight English cloning candidate | Narrower language scope; benchmark its quality against Qwen |
| TADA 1B / 3B | Long-form experimental candidate | Young stack and relatively heavy variants |
| Kokoro 82M | Fast preset voices and CPU-friendly fallback | Preset synthesis, not the preferred clone-quality test |
| Qwen CustomVoice | Curated preset voices with instruction control | Not cloning a Narratiive-owned reference voice |

Voicebox adds smart chunking and crossfade for long text, but long-form prosody
can still vary at boundaries. A pilot should compare short copy, names/numbers,
emotional delivery, a 2–5 minute narrative, and repeated takes. Acceptance should
measure intelligibility, speaker similarity, unwanted artefacts, consistency,
editing time, generation speed, and failure rate rather than relying on a demo.

## Hardware and runtime

- Upstream recommends an 8 GB or larger GPU for best performance and documents
  CPU generation as much slower.
- The dependency set is substantial: Python 3.12 for source development,
  PyTorch/Transformers, model-specific packages, audio libraries, FFmpeg, and
  Hugging Face downloads. Some packages are installed from Git repositories or
  with dependency resolution bypassed, increasing reproducibility risk.
- NVIDIA CUDA, AMD ROCm, Intel XPU/DirectML, Apple MLX/Metal/MPS, and CPU paths
  exist, but support quality differs. The default Docker service is CPU-limited
  to four cores and 8 GB RAM; that is a safety limit, not evidence of good
  generation performance.
- Qwen3-TTS 1.7B model files alone are roughly 4.5 GB upstream. Cache, alternate
  engines, Whisper, and generated audio require additional disk space.

For Matt's Mac, prefer the supported Apple Silicon desktop/MLX path if applicable
and test one engine at a time. Do not promise real-time or unattended long-form
generation until the exact machine passes soak tests.

## Licensing

The Voicebox application source is MIT licensed. This permits commercial use and
modification with preservation of the copyright and licence notice.

That licence does not cover every downloaded model, weight, dataset implication,
Python/Rust/JavaScript dependency, reference recording, or generated person's
publicity/privacy rights. For example, the reviewed Qwen3-TTS 1.7B model card is
Apache-2.0 and Chatterbox publishes MIT terms, but every selected engine/version
must be checked and recorded separately before client or commercial use.

## Privacy and security

Local operation is privacy-positive: reference audio, profiles, transcripts,
model caches, SQLite state, and generated files can stay on the machine. It is
not automatically private if Voicebox Cloud sync is enabled, a remote backend is
used, model downloads contact third-party hosts, or its port is exposed.

The material security issue is that Voicebox REST and MCP routes have no
authentication. They include profile, recording, transcription, generation,
download, and destructive routes. `X-Voicebox-Client-Id` is preference routing,
not proof of identity. Keep the server loopback-only. Remote use needs TLS,
authentication, firewall policy, request/body limits, logging controls, and a
review of the proxy configuration.

Cloned voice and reference audio should be treated as sensitive biometric and
identity data. Consent must identify the speaker, permitted purpose, channels,
duration, operators, storage, revocation/deletion process, and whether synthetic
speech must be disclosed. Do not infer permission from possession of a sample.

## Fit with Narratiive OS

| Narratiive component | Fit | Boundary |
| --- | --- | --- |
| Core workflow runtime | Optional downstream production tool only | Voice generation cannot change workflow state or approval |
| Tony | No direct coupling in this change | A future capability must enter through Tony's authenticated public boundary |
| OpenClaw | Voicebox exposes useful MCP tools | Do not add them globally until identity, consent, and approval routing are designed |
| n8n | REST is easy to call and poll | n8n must not treat HTTP success as asset approval or delivery permission |
| Artefact/lineage stores | Compatible in principle | A future production workflow must record source text, profile/engine, generation ID, checksum, parents, and approval |
| Client isolation | Not supplied by Voicebox's single local data store | Use separate Voicebox instances/data roots or an approved isolation design for multi-client production |

The included adapter reads environment configuration at runtime, fails closed
when disabled, defaults to loopback, rejects unsafe remote HTTP, requires a
proxy-enforced bearer token for remote HTTPS, bounds timeouts and downloads, and
leaves persistence/delivery to the governed caller. It changes no Tony,
OpenClaw, n8n, provider-routing, workflow, schema, canon, or client-facing
contract.

## Pilot exit criteria

Promote Voicebox beyond an optional pilot only after:

1. explicit speaker consent and a retention/deletion procedure exist;
2. the chosen release, engine, model identity/licence, and machine are pinned;
3. representative audio passes documented human quality review;
4. repeated and long-form generations pass latency, memory, crash-recovery, and
   disk-capacity tests;
5. network exposure is demonstrably loopback-only or protected by an approved
   authenticated proxy;
6. any automation records workspace/client scope, lineage, immutable output
   checksum, and the exact human release approval;
7. a non-Voicebox fallback exists for critical communications.
