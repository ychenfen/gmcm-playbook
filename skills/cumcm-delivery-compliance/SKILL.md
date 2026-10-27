---
name: cumcm-delivery-compliance
description: Audit or finish a CUMCM-style paper PDF, AI-use declaration/detail, code appendix, support materials, and final ZIP as one consistent submission package.
argument-hint: "[submission root]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash
---

# CUMCM Delivery Compliance

## When to use

Use when the user asks to submit, package, check compliance, add an AI declaration/detail, or verify a CUMCM/contest paper. Do not use to claim current official compliance without reading the current rules or to invent the team’s AI-use history.

## Inputs / context to gather

1. Confirm `$ARGUMENTS` and locate paper source/PDF, submission PDF, support-material directory/ZIP, result files, core code, and the official rule or user-supplied checklist.
2. Extract the actual rules: identity/privacy, PDF/editability/no-image-only requirements, page/main-text definition, declaration/appendix placement, source-code and AI-detail requirements.
3. Read any existing AI declaration and standalone detail together; establish the truthful scope before editing.

## Procedure

1. Build a line-item compliance table before editing. Separate main text from references/appendix and distinguish paper-embedded declarations from standalone detail PDFs.
2. Repair source files, compile the paper, and copy the accepted source PDF into the final submission path. Make the AI declaration and detail PDF consistent with actual documented use only.
3. Compare core source and result-file copies across source, support material, and submission locations. Ensure the appendix starts with a support-material list when required.
4. Verify the final PDF: `pdfinfo` for page count/encryption, `pdftotext -layout` for title/abstract/declaration/references/appendix order, rendering for visual layout, and `pdfimages` or equivalent for a non-image-only sanity check.
5. Verify the final ZIP: inspect entry names, confirm the AI-detail/code/result members, run `unzip -t`, and use Python `ZipFile.testzip()` when available. For Chinese names, also check `ZipInfo.flag_bits & 0x800`.
6. Report exact paths, gates passed, unverified items, and any historical-vs-current-rule boundaries.

## Efficiency plan

- Inventory final paths first; avoid validating a source PDF while forgetting the submitted copy.
- Use one compliance table and one targeted text search for structural anchors rather than rereading PDFs repeatedly.
- If `qpdf` is unavailable, do not install it solely for the task: use `pdfinfo`, text extraction, rendering, and archive checks.
- Stop before changing any statement about AI use if the team’s real use is unclear.

## Pitfalls and fixes

- Inherited AI-use detail belongs to another paper or conflicts with the declaration -> regenerate from current, truthful evidence; never keep a generic reusable claim.
- Compiler exits successfully but code listings show missing glyphs -> inspect final log and rendered PDF; choose a glyph-capable monospaced font if needed.
- Source artifact changed but submission copy/ZIP did not -> recopy, compare checksums, and rerun final-package checks.
- `unzip -t` passes but Chinese names are not portable -> repack with Python `zipfile` and verify UTF-8 flags.

## Verification checklist

- [ ] Current rules/checklist and final artifact paths confirmed.
- [ ] No prohibited team identity, encryption/restrictions, pages, or image-only PDF issue remains.
- [ ] Main-text/AI declaration/references/appendix placement verified from final submission PDF.
- [ ] AI declaration and standalone detail accurately agree.
- [ ] Core code/results are present and consistent in required appendix/support/ZIP locations.
- [ ] Final PDF was rendered and final ZIP passed membership, CRC, and filename-encoding checks.
