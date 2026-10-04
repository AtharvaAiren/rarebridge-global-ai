Evaluation pack — source/rule audit, NOT clinical validation.
heldout-cases.json  9 frozen cases (E1-E9), written before any app answers.
                    Never load into the app, search, retrieval or prompts.
rubric.json         5 criteria; auto-scored parts + manual parts.
run_eval.py         --engine-audit  : rule-engine check (6 cases, all pass)
                    --template      : blank answers file for real runs
                    --answers FILE [--manual FILE] : score real answers
timing-template.csv Manual vs app brief-drafting timing. Rotate task order.
                    Measures time to DRAFT a collaboration brief only; not
                    expert approval, permissions, study launch or treatment.
No results are included: fill them only from actual runs. Tiny pilot; always
report denominators. The negation check in scoring is a heuristic; read any
flagged sentence yourself.

REAL TIMING PILOT
Open /impact-pilot.html on the frontend host (or local Vite server). This is a
standalone measurement page, outside the patient workflow; it needs no backend.
Read submission/IMPACT_CASE.txt first. Give both methods the same frozen source
pack, exact task, fictional cohort constraints, and integrated app snapshot.
The page links the published protocol and official STARR/ENDD study pages as
starting sources. Save/identify their actual versions; links are not a frozen
pack. A preprint version is not interchangeable with the published paper.

Use anonymous participant/reviewer codes, never patient data. Prefer two people:
one manual -> app, one app -> manual. Record domain familiarity and training.
Complete required run fields, then Start when the task is received. Pause active
work for unrelated interruptions only; elapsed wall time always keeps running.
Use one pilot tab per browser. Keep the tab open: closing/reloading does not
automatically pause active work.
Source reading, corrections and artifact review belong inside the timed task.
After a real reviewer checks all six completion criteria, enter reviewer and
artifact references and Finish. Record failures/incomplete runs with a reason.
These controls record human review; they do not validate artifact quality.

Logs persist on this browser where available. Export all runs to CSV and JSON
after each participant; running/failed/incomplete attempts remain included.
There are no shipped timing results. An eligible ratio needs exactly one manual
and one app attempt for a matched participant/task cycle; both must be complete,
6/6 checked, have reviewer/artifact references and opposite first/second order.
The recorded first run must finish before the second run starts.
Participant, cycle, source pack, app snapshot, task, fictional constraints and
familiarity must match. Duplicate method attempts in a cycle are excluded from
pairing; use a new cycle for repeats and report every attempt. AI/training fields
are retained for scrutiny but are not enforced as matching criteria: disclose
unequal instruction or experience and any resulting limitation.

The display reports manual wall time / app wall time with raw times, quality and
pair/run/participant denominators. Active work is exported separately. A ratio
of 10 or more is only an observed brief-preparation result for this small pilot.
It does not establish 10x acceleration of expert feasibility review, study
launch, treatment research or a clinical milestone. Report failures, small N,
practice effects, quality differences and lack of blinded review where relevant.
