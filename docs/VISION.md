# Vision: Skills That Sharpen Themselves

> A skill should not wait for a human to notice it's mediocre. It should know its own target, measure itself against it, and close the gap on its own — overnight, while we sleep.

## The North Star

We are building toward a world where a Claude Code skill improves like a research system, not like a document. You hand it a clear target and a way to measure distance from that target, and it runs an autonomous loop: change itself, test, score, keep what helped, discard what hurt. Every morning the skill is measurably better than the night before — and you can prove it, because the proof is a number that went up.

The name of this project is a promise. "Self-improving" is not a metaphor. It is a loop we intend to actually run.

## Why we refuse the status quo

Today, refining a skill is a slow, manual, lossy craft. You watch Claude do something wrong, you open the `SKILL.md`, you hand-edit a sentence, you hope. The feedback is anecdotal, the iteration is serial, and the gains are forgotten between sessions. It can take weeks to earn a reliable "version 2," and there's no guarantee version 2 is actually better — just different.

That ceiling is artificial. The bottleneck isn't intelligence; it's that nobody wired the skill to a scoreboard and let it play against itself.

## The core loop

The engine of the vision is a single, ruthless cycle borrowed from autonomous research:

1. **Change** — make exactly one edit to the skill's instructions.
2. **Test** — run the eval suite.
3. **Score** — compute a number.
4. **Ratchet** — if the score rose, commit the change and keep it. If it fell, `git reset` and try something else.

Git is the ratchet. It guarantees the system can only move forward: every kept change is a proven improvement, and every regression is erased before it can compound. The loop needs no supervision, asks no permission, and stops only when interrupted or when the score is perfect.

This is what turns improvement from an act of taste into an act of search.

## Two frontiers

A skill can fail in two distinct ways, and our vision must conquer both.

**Frontier 1 — Activation.** A skill that never fires is worthless, no matter how good its output. Claude decides whether to invoke a skill by reading its description; a vague description gets ignored. So the first axis of self-improvement is trigger accuracy: tune the skill's framing until it activates exactly when it should, and never when it shouldn't.

**Frontier 2 — Output quality.** Once a skill fires, the work has to be right. This is the harder, deeper frontier — and the one the core loop is built for. It optimizes the *process instructions* themselves until the output reliably satisfies the target.

A fully self-improving skill closes both. Wrong trigger or wrong output — either is a defect the loop should be able to drive to zero.

## The engine runs on binary truth, not taste

The loop is only as powerful as its metric, and here lies the discipline that separates systems that work from systems that stall: **the target must be measurable as true or false.**

A machine cannot optimize "is this writing compelling?" It can optimize "does the output contain zero em-dashes?", "is the word count under 300?", "does the final line end with a declaration rather than a question?" Subjective criteria feel ambitious but leave the loop blind. Binary assertions are humble, and that humility is exactly what makes them automatable.

So our vision treats every quality goal as a translation problem: take the fuzzy intent ("sounds professional," "ends strong") and decompose it into a battery of pass/fail checks. The art is in the decomposition. The automation is free once it's done.

## Evals are the fitness function

A self-improving skill is meaningless without something to improve *toward*. That something is the eval suite: a set of representative inputs, each paired with its battery of binary assertions. This suite is the skill's contract with reality — it defines what "good" means, and the loop optimizes against nothing else.

Two consequences follow:

- **The eval suite is the most important artifact in the system.** A weak suite produces a skill that scores 100% and still disappoints. Investing in the assertions *is* investing in the skill.
- **Authoring the suite should itself be assisted.** We don't write hundreds of assertions by hand; we ask Claude to draft them from the skill's own instructions, then curate. The fitness function is bootstrapped from the thing it measures.

## The night shift

The deepest shift in this vision is temporal. Improvement stops being something a human does in a focused hour and becomes something a system does continuously, unattended, through the night. You define the target before bed; the loop searches the space of edits while you sleep; you wake to a better skill and a log explaining every step it took to get there.

Progress decouples from human attention. That is the whole point.

## Where the loop stops, the human begins

We hold no illusion that the loop is omnipotent. It is a precision instrument with a sharply defined edge.

**What it conquers completely:** structure, formatting, length limits, forbidden patterns and phrases — anything reducible to a check.

**What it cannot touch:** whether the writing actually moves someone, whether the tone is right, whether the underlying facts are woven together with genuine insight. These are not pass/fail. The loop will happily produce structurally perfect, emotionally dead output and report a perfect score.

This is not a flaw to be patched — it is the boundary that defines the human's role. The loop owns the mechanical and the measurable so that the human is freed to own the creative and the qualitative. Taste, judgment, and meaning stay with us; we use side-by-side review, human feedback, and A/B comparison for the axes no assertion can capture. A perfect eval score is therefore a *floor*, not a ceiling — it certifies that nothing is broken, and hands the interesting questions back to a person.

## What success looks like

We will know the vision is real when:

- A new skill ships with its eval suite from day one, the way code ships with tests.
- "Make this skill better" is a command you can run, not a project you have to staff.
- Every improvement is provable — a committed diff tied to a score that went up.
- Humans spend their skill-building hours on taste and targets, never on the grind of manual iteration.

The skill that improves itself is the skill that compounds. That compounding is what we're here to build.

---

*Lineage: this vision adapts Andrej Karpathy's "auto-research" loop — define a metric, let the system edit and test itself in a git-gated cycle — to the specific problem of making Claude Code skills self-optimizing.*
