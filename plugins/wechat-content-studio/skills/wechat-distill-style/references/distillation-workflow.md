# Distillation Workflow

## Candidate set

Aim for multiple representative articles rather than one visually striking sample. Cover more than one article type when possible. Record title, source URL or local file, article type, accessibility, and why it belongs in the set.

Present the candidate set to the user and wait for confirmation before candidate generation. The CLI records confirmation with `--confirmed-by-user`.

## Import

Use `sample import` for URLs, captured HTML, or text. A URL without a local payload records accessibility but does not invent evidence. Use `--payload-file` when HTML or text has been captured separately. Let content hashing and URL normalization handle duplicates.

## Analysis

Use `sample analyze` on the confirmed IDs. It extracts writing evidence from readable body text and layout evidence only from body HTML with usable inline styles. It removes known WeChat peripheral UI before statistics.

Generate a candidate only when `--candidate-id`, `--candidate-name`, and an appropriate root are known. Project candidates belong under `<project>/styles/local`; imports candidates belong in the workspace import area. Validate the output afterward.

## Maturity

`provisional` is the default for limited evidence. `established` requires all of:

- at least eight usable samples;
- at least three article types;
- both writing and layout evidence;
- no unresolved conflicts;
- explicit established-review acknowledgement.

Quantity alone never satisfies the gate.
