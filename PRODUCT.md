# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One photographer: the owner, shooting a Nikon Z6III, running the app on their own TrueNAS box at home. It is a personal tool, not a product for other photographers; the published image and deploy guides exist for convenience, not for an audience.

They use it in two situations, roughly equally:

- **During a shoot.** Frames arrive over FTP within seconds of capture. The job is to glance at the latest frame and decide whether the next shot needs to change (focus missed, eyes soft, highlights clipped, shutter too slow).
- **After a shoot.** Reviewing the session in depth, reading the critique, rating and flagging, and handing keepers to an editor.

They use it on a desktop or laptop at a desk, and on a phone or tablet on set next to the camera.

## Product Purpose

Turn every frame the camera uploads into immediate, trustworthy feedback, and make the photographer better over time.

Success, in priority order:

1. **Fix the next shot.** Technical problems are visible fast enough to correct while the scene is still in front of the camera.
2. **Learn from every frame.** Analysis and AI critique explain why a frame works or doesn't, so the photographer improves rather than just sorts.

Fast culling and clean handoff to editors and Immich are supporting capabilities, not the headline.

## Positioning

A live, private feedback loop for one camera. Frames go from the shutter, over FTP, to measured sharpness, exposure and face/eye focus plus a written critique in seconds, on the photographer's own hardware, without ever touching the originals. Cloud galleries and desktop catalogues work after the fact; this works during the shoot and teaches as it goes.

## Operating Context

- Nikon Z6III uploads over FTP to the NAS; an existing sorter files JPEG, RAW and video into folders the app watches read-only.
- Runs as a Docker stack on TrueNAS SCALE on a home LAN. Remote access, when used, goes through Cloudflare Tunnel with Cloudflare Access in front.
- Sits beside Immich (optional, read-only lookups), the FTP sorter, and the photographer's editors. Editors are reached by copying NAS/SMB paths or downloading originals.
- On set: a phone or tablet, glanced at between shots, often one-handed. At a desk: a full screen, keyboard-driven culling (0–5, P, X, U, F, E, arrows, Esc).
- Optional GPU (RTX 3060 / Tesla P40) for Ollama vision models.

## Capabilities and Constraints

- **Originals are sacred.** Photo roots are mounted read-only and never moved, renamed, modified or deleted. Ratings, flags, tags and notes live only in the app database. XMP sidecar export is planned as an explicit opt-in.
- **Live ingest** with file-stability checks, RAW+JPEG pairing into one photo (robust to counter rollover and a second body), full Nikon maker-note metadata, previews and thumbnails.
- **Technical analysis:** sharpness, brightness, highlight/shadow clipping, histograms, dominant colours, YuNet face and eye detection with per-face sharpness. Measured on the JPEG rendering, so it is guidance, not ground truth.
- **AI critique** through pluggable providers: `local` (offline heuristics, default), `ollama` (own GPU, nothing leaves the LAN), `openai` (any compatible vision endpoint), `none`. Returns scene, subject, description, composition and technical notes, issues, suggestions, tags, an aesthetic estimate and confidence. Failures never block ingest.
- **Culling:** 0–5 stars, pick/reject, favourite, needs-edit, exported, tags, notes, bulk edits.
- **Surfaces:** Dashboard (`/`), Library (`/library`), Photo (`/photos/[id]`), System (`/system`). Live updates over SSE.
- **Single user, no login.** Designed for a trusted LAN; `API_TOKEN` guards the backend when exposed.
- **Terminology:** cull, pick / reject, burst ("frame 2/5"), session, RAW / JPEG / NEF, HE / HE★, ⅓ EV, NAS path, SMB path.
- **Roadmap (not built):** portrait-aware critique and suggested next-shot settings; best-of-burst ranking, near-duplicate detection, semantic and natural-language search; research-only camera connectivity through official Nikon paths. No firmware modification, ever.

## Brand Commitments

- Name: **Z6III AI Studio**. Descriptor: "Intelligent Nikon photography workflow."
- Voice: short, calm, practical, photographer-to-photographer. Analysis language is deliberately hedged ("likely", "estimated") because metrics are estimates. Examples in use: "Live ingest from your Z6III, paired, analyzed and ready to cull." / "Shoot with FTP upload enabled — new frames appear here within seconds."
- No logo file exists; the current mark is an icon placeholder.

## Evidence on Hand

- Real content is the owner's own photo library on the NAS; it never leaves the LAN unless a remote AI provider is chosen.
- `make samples` generates synthetic Nikon-style JPEG+NEF captures (with bursts) for development.
- No testimonials, users, benchmarks or press exist, and none should be invented. This is a personal tool.

## Product Principles

1. **Seconds matter.** The latest frame and its verdict come first; anything that slows the during-shoot glance is a regression.
2. **Teach, don't just score.** Every number earns its place by pointing at a cause and a fix the photographer can act on next time.
3. **Honest about certainty.** Measurements and critique are presented as estimates with their confidence, never as verdicts.
4. **Never touch the originals.** The app observes and annotates; it does not alter, move or delete files.
5. **Private by default.** Everything works offline on the owner's hardware; sending a frame off the LAN is always an explicit choice.

## Accessibility & Inclusion

No formal standard has been set. Practical requirements from the operating context: readable at arm's length on a phone in varied light on set, usable one-handed for the during-shoot glance, and fully keyboard-operable at the desk.
