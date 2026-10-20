# The substrate boundary

Classify each consequential action by the path that performs it. A system may
use more than one path, so describe the verified surface action by action.

## 1. The action goes through revl

The action is part of a revl component and runs through revl's checked runtime.
For example, a component sends mail through a declared `emission[mail]`
operation, and the runtime checks the declared capability and any applicable
compensation. You may say this path is inside the guarantees revl enforces.
That does not verify arbitrary host code behind an `extern`; that boundary
remains trusted and enumerable under G8 ([vision](vision.md)).

## 2. A host gateway performs it and revl records a supported effect

A gateway may perform an action and return a record only through an effect path
the tree already defines. A revl-understood record means either a declared
emission with its `compensate` path, or a `witnessed[C]` operation whose runtime
witness and inverse are registered. For example, the standard filesystem
`write` witness records the path and preimage so the runtime can restore it on
abort ([witnessed filesystem operations](witnessed-fs.md); see
`docs/witnessed-fs.md` and the declaration in [capabilities](capabilities.md)).

This is not a promise of a general signed-record format: the repository defines
no such envelope. The host gateway remains trusted to report its work honestly;
revl checks the declaration and record behavior its runtime understands, not
the truth of an arbitrary host-supplied log line.

## 3. The work is a proposal only

An agent may draft a command, tool call, or component for review without
performing it. For example, a proposed file deletion has no filesystem effect
until a later step executes it through path 1 or 2. You may say the action was
proposed or checked as text; you may not say it was executed or governed by
revl's effect guarantees.

## 4. The action is outside the verified surface

A host may call a browser, shell, or other tool directly, without passing the
action through revl and without producing a supported effect record. That action
is outside the verified surface. Name the excluded action and its boundary; a
system with such a path must not claim that every consequential action passes
through revl's typed, capability-checked runtime.

When reporting a mixed system, state which actions use paths 1 and 2, which are
proposals under path 3, and which remain outside under path 4. A record narrows
what revl can verify; it does not turn an unmediated host action into a revl
action ([the consumer-boundary analysis](design/549-aios-consumer-boundary.md)).
