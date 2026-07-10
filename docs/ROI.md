# Operations Dashboard — value & ROI

*A transparent value case. Every figure is an estimate built from stated
assumptions — swap in the real numbers and the model updates. Ranges are used
deliberately; the point is the order of magnitude and the payback, not false
precision.*

---

## Headline

| | |
|---|---|
| **Hard savings** | **~$20k–45k / year** (manual reporting + tooling) |
| **Running cost** | **≈ $0 / month** (scheduled job + static hosting on existing infra) |
| **Payback** | **< 1 year on a single team** — then near-pure saving |
| **Multiplier** | Scales to every other Yo-Chi team/state at **near-zero marginal cost** |

---

## Where the savings come from

### 1. Manual reporting labour *(clearest hard saving)*

Replaces the hand-compiled, 6-system, 23-venue compliance report distributed
Mon/Wed/Fri — now fully automated (zero touch).

| Assumption | Estimate (edit me) |
|---|---|
| Time to compile one report | 2–3 hrs |
| Reports per week | 3 (Mon/Wed/Fri) |
| Hours/week | 6–9 |
| Hours/year | ~300–450 |
| Loaded hourly rate (AUD) | $50–70 |
| **Annual labour saved** | **~$15k–30k** |

### 2. Tooling / licence spend it lets you cut

A direct step toward retiring Power BI for ops reporting.

| Assumption | Estimate (edit me) |
|---|---|
| Power BI seats displaced | (your number) |
| Cost per seat (AUD/mo) | ~$16–30 |
| Other per-venue reporting spend | (your number) |
| **Annual tooling saved** | **~$2k–12k+** |

### 3. Upside not counted in the headline *(real, but not claimed)*

- **Faster issue detection** — daily visibility vs 3×/week means labour overruns,
  food-safety lapses and compliance gaps are caught earlier. Labour is a top cost
  line; even a 0.5% improvement across NSW is material. *(Not included above —
  it's genuine but too situational to bank.)*
- **Data-quality wins already delivered** — surfaced the Restoke labour
  mis-attribution and the Xero budget-basis mismatch, both worth fixing regardless.
- **Trust** — every number traces to DataSights on-screen; no black box.

---

## Running cost

Effectively **$0/month**: a scheduled GitHub Actions job (free tier) + static
hosting, on infrastructure already owned. No per-seat licence, no server to run.
So the savings above are close to **net**.

## The multiplier: other teams

Other Yo-Chi teams have already asked for this. Because it's **config-driven**
(one codebase, one config per team), each additional team is a small setup — not
a rebuild. The per-team economics repeat every time:

> One team ≈ $20k–45k/yr saved. Five teams on the same codebase ≈ **6-figure**
> annual saving, still at ≈$0 running cost.

---

## What it replaces / delivers (Phase 1, live today)

- Live compliance across Sales, Google Reviews, Celsi food-safety, Chi Central
  (policy / comms / training) and Labour %, for 23 NSW venues.
- Auto-refreshes to the latest complete day, every morning, unattended.
- Every figure traceable to its DataSights source on the page.
- Built on existing tooling (GitHub / Python / DataSights) — owned outright.

---

## What it's worth to build (pricing reference)

| Lens | Range (AUD) |
|---|---|
| Agency build of an equivalent live, multi-source, automated dashboard | $20k–40k+ |
| Freelance/contract build | $8k–20k |
| **Value-based** (captures ~year-one savings) | $20k–45k |

**Suggested structure for a *progress* payment (Phase 1 delivered, Phase 2 + rollout to come):**

- **Phase 1 progress payment now:** ~$5k–12k.
- **Then either** a completion fee on Phase 2, **or** a **retainer of ~$500–1,500/mo**
  covering maintenance, new metrics, and standing up additional teams. The retainer
  ties recurring revenue to recurring value and is the sustainable model.

---

## The one-line case

> *"It replaces $20k–45k/year of manual reporting and Power BI cost on a single
> team, runs for effectively nothing, scales to every other team at a fraction of
> that, and pays for itself inside year one."*

---

## Honest caveats (so the numbers survive scrutiny)

- These are **estimates from stated assumptions** — replace with your real
  reporting hours, rates and licence counts.
- This is a strong **Phase 1 MVP**, not a hardened enterprise product: the Sales
  *budget* comparison and Restoke *checklists* are pending upstream data, and it
  should sit behind a company login before wide distribution.
- Recurring value assumes it stays maintained — which is what the retainer funds.
