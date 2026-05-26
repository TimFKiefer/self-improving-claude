# Restraint fixture — a one-off mistake warrants no standing guardrail

A reactive fixture. The chat shows Claude making a ONE-OFF slip (referenced the
wrong local variable, `total` instead of `subtotal`) which the user caught and
Claude immediately fixed. There is no generalizable, deterministically-detectable
pattern here: no tool event to hook, no glob to deny, no convention to encode.

The correct outcome is to propose NOTHING — a hook or rule built for a single typo
would be noise. This tests restraint against the reflex to always emit a guardrail.
