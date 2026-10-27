---
name: competition-model-quality-freeze
description: Resume or freeze a contest-modeling checkout when the user says “继续”, asks for quality verification, or needs paper/submission gates kept separate from local results.
argument-hint: "[project root]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash
---

# Competition Model Quality Freeze

## When to use

Use for a competition-modeling project with existing code, results, handoffs, or a proposed paper/submission. Use it to recover context, verify a checkpoint, or prepare a truthful freeze. Do not use it to claim submission, upload, or final scientific conclusions from an incomplete pilot.

## Inputs / context to gather

1. Confirm `$ARGUMENTS`, its actual working subdirectory, and the boundary between official prompt/attachments/templates and editable implementation.
2. Read the current handoff, modeling log, manifest, requirements coverage, quality/freeze checklist, and result directory before changing code.
3. Inventory the current paper/PDF, figures, generation scripts, test commands, result CSV/JSON, archive, and previous hashes. Classify each as current evidence, historical baseline, or missing.

## Procedure

1. For “继续”, recover the active objective and gates from local artifacts; begin with a read-only status table. State explicitly whether the status is exploratory, locally verified, frozen, packaged, uploaded, or submitted.
2. Preserve official originals and create/identify a recoverable rollback artifact before model changes. Keep exploratory candidates isolated from formal runs.
3. Run the project’s tests, compilation/static checks, and domain assertions. For experiment pipelines, retain inputs, evaluator/version fingerprints, source provenance, and hashes; do not put cache-hit counters into scientific result CSVs.
4. Visually inspect every new or changed figure/PDF for blank output, clipping, missing series, and label overlap. Check numerical text for stale hard-coded values and mojibake.
5. If any code, parameter, input, or dependency changed, run the complete generation chain twice consecutively, compare outputs/hashes, and regenerate formal SHA-256. Treat earlier hashes as historical only.
6. Before paper or final-package work, require the declared experiment coverage and failure/boundary cases. Record negative/no-gain cases rather than reporting only averages.
7. For a ZIP, verify membership and integrity separately from its creation; report recipient sending/official submission only with direct evidence.

## Efficiency plan

- Read the handoff/log/checklist and list result directories first; avoid rediscovering the project through raw source browsing.
- Use staged representative runs to find performance bottlenecks, but label them preflight-only until required coverage completes.
- Cache hashes, test commands, and artifact inventory in the handoff. Stop immediately when a gate cannot be evidenced instead of expanding paper/submission scope.

## Pitfalls and fixes

- Pilot presented as final -> identify missing coverage (cases, cores, questions, sensitivity/exact comparison) and block paper/submission conclusions.
- Old hash reused after a change -> rerun twice and produce new hashes; retain the old result only as a baseline.
- macOS/iCloud compressed or dataless input breaks a helper -> restore local visibility or use a stable extracted copy; do not make unrelated maintenance scripts a quality gate.
- Archive exists or PDF opens -> perform independent ZIP/PDF/render checks; neither proves delivery, upload, or acceptance.

## Verification checklist

- [ ] Current handoff/log/checklist and editable-vs-official boundary inspected.
- [ ] Tests, compilation/static checks, and applicable domain assertions passed.
- [ ] Changed figures/PDF were visually checked; stale values and encoding issues scanned.
- [ ] Full generation chain was rerun twice after relevant changes and current hashes recorded.
- [ ] Required coverage plus failure/boundary cases are explicit.
- [ ] Paper, package, upload, and submission status are reported as separate evidenced gates.
