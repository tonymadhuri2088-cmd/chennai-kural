# Summary

**Chennai Kural: Your Voice. A Better Chennai.**
Cognizant AI Lab x IIIT Raichur Agentic AI Hackathon 2026. Unofficial prototype, not affiliated with CMWSSB.
Team: Abhinav Reddy and Tony Madhuri.

## The problem

When a Chennai citizen reports a broken water pipe or a blocked sewer, they rarely know who owns the problem,
how long the Citizen's Charter gives for the repair, or what to do when the time runs out. Complaints get stuck
without anyone noticing, and a worker can mark a job "done" while the problem is still there.

## What we built

A working complaint portal with a web app and a Flutter app.

- **Citizens** sign up, log in with a code, file a complaint, and track it. A router sorts the complaint and
  shows the citizen a message with their complaint ID and a timeline: each officer level, its time limit,
  and where the complaint is now.
- **Officers** see the complaints assigned to them. When a time limit passes, the complaint moves up
  automatically (Depot, Deputy Area Engineer, Area Engineer, Superintendent Engineer, District Head Office)
  and the officers get a notice.
- **Field workers** accept complaints and finish them. A job closes only when the **citizen** confirms with a
  one-time code, so "done" cannot be claimed by one person alone. A citizen who says "not fixed" sends the
  complaint to the ward office and then to the District Head Office.

## Where the agents are

The router is a **Neuro-SAN agent network** (`registries/complaintrouter.hocon`): one LLM coordinator and five
specialist agents (intake, charter lookup, router, escalation, reply). The coordinator calls them in a fixed
order, passes each result on, and returns the reply agent's text. Each agent is a Python tool that reads
`data/charter.json`, so deadlines, owners and escalation days are never invented. A local model (llama3.1 via
Ollama) may only choose a complaint's type, and its answer is checked against the charter before use. If it is
unavailable or wrong, a keyword classifier takes over, and uncertain complaints are flagged for a human.

The live portal runs the same five tools in-process, so registration never depends on an LLM being up. It does
not yet call the network itself; that is the next step. `architecture.md` explains this in detail.

## What we measured

`python examples/evaluate_router.py` runs 45 complaints we wrote and labelled ourselves (all 15 charter types,
7 urgent cases, 4 Tamil and 4 Hindi). This is a small, non-independent test. It shows behaviour on these
examples, not on real complaints.

Keyword classifier (the fallback, no model):

| Measure | Result |
|---|---|
| Complaint type correct | 24.4% (11/45) |
| Plain wording / everyday wording | 41.7% (10/24) / 7.7% (1/13) |
| Tamil / Hindi | 0/4 / 0/4 |
| Urgent cases caught (recall) | 57.1% (4/7) |
| Urgent flags that were right (precision) | 100% (4/4) |
| Sent to a human for review | 73.3% (33/45) |
| Wrong type and **not** flagged for review | 2.2% (1/45) |
| Time per complaint | mean 0.2 ms |

How to read this: the keyword fallback is weak and English-only, which is exactly why a model is used for
classification. But it fails safely: when it does not recognise a complaint it says "unclassified" and sends it
to a human, and only 1 of 45 complaints was both wrong and unflagged. That one was a worker cleaning a septic
tank by hand, which should have been urgent and was not. We have **not** measured the LLM classifier: Ollama was
not available where we built this. `--llm` measures it and refuses to report LLM numbers if the model was not
actually used.

Other checks: 303 automated tests pass (no model or internet needed), and a browser-engine test of the real
registration and tracking pages passed 15 of 15 checks.

## Limits (we want to be upfront)

- The LLM classifier and a live `ns run` of the agent network were not exercised in our build environment.
- The charter copy comes from a development mirror, and it does not say whether escalation days are cumulative
  or per level. We treat them as per level; CMWSSB should confirm.
- Demo only: no HTTPS, sessions and codes held in memory, personal data stored in plain text (use invented
  data only), SMS needs a provider account, and the Flutter app was not compiled in our build environment.

## Next steps

1. Make the portal call the Neuro-SAN network, keeping the in-process pipeline as fallback.
2. Measure the LLM classifier and grow the test set with independently labelled complaints.
3. Add Tamil and Hindi understanding to the classifier.
4. Confirm charter values and the escalation rule with CMWSSB.

## Run it

See `README.md` ("Quick start for judges"). Python 3.12 or 3.13, `pip install -r requirements.txt`,
`python portal/server.py`.
