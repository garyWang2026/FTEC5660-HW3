# Task 2: Reflection on AI-Sycophancy and AI-Psychosis

**FTEC5660 Homework 3 — Task 2 Reflection**

Working on this homework gave me a very concrete feel for two failure modes
of AI that are easy to talk about in the abstract but hard to appreciate until
you see them inside your own system: **sycophancy** — the model's tendency to
tell you what it thinks you want to hear — and what I will call
**AI-psychosis** — the model's tendency to produce confident, fluent output
that has quietly detached itself from the facts.

The warning in the homework that "arithmetic done by the model was the most
common cause of wrong verdicts" is essentially a description of the second
problem. When I first let the model compute ratios and compare them against
industry medians "in its head", it would happily produce a perfectly written
paragraph of analysis built on numbers that were subtly wrong — a misplaced
decimal, a wrong window of months, a median that belonged to another
industry. The output was indistinguishable in style from correct output. That
is the psychosis: the model is not merely hallucinating a fact here and
there; it constructs an entire internally coherent, emotionally persuasive
narrative that is unmoored from the database. It does not sound confused. It
sounds confident, and that is precisely what makes it dangerous.

The sycophancy failure appeared the moment I asked the model to "check" its
own verdicts. Because the company is the subject of the prompt and the model
has been trained to be agreeable, it would rationalize whichever verdict the
conversation seemed to lean toward — a FAIL would be explained with a
plausible-sounding story about weak R&D, and the same evidence, framed
slightly differently, would just as easily support a PASS. The model was not
deciding; it was mirroring. In a real investment setting this is exactly how
an AI assistant helps a fund manager talk themselves into a bad position:
the assistant finds reasons, not truth.

What this homework taught me is that the fix is architectural, not
prompt-level. Telling the model to "be honest" does not cure sycophancy, and
telling it to "calculate carefully" does not cure psychosis. The cure is to
stop asking the model to do the things it is bad at. In my agent, every sum,
every ratio and every comparison against the industry median is computed by
SQL inside the `sql_query` tool, and the model is left with exactly one job —
writing a two-sentence explanation of verdicts that were already determined
from real numbers. It can still be poetic in its summary, but it can no
longer change the answer. The agent's verdicts became deterministic and
reproducible: 60/60 on the public test, three runs in a row.

I came out of this with a healthy suspicion of any AI output that reads too
smoothly, and a design principle I will keep: decide which parts of a task
require grounding in data, and keep the language model as far away from those
parts as possible. Fluency is not a source of truth; it is a delivery
mechanism. The moment a model starts explaining why it is *probably* right,
it is usually telling me about its own psychology rather than about the
company — and that is the moment I should go back to the database.
