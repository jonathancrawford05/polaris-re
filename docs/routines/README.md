# Polaris RE — Claude Code Routines

## Daily Development Loop

```
  02:00 ET          09:00 ET         ~09:30 ET         You (async)
  ┌─────────┐      ┌──────────┐     ┌───────────┐     ┌──────────┐
  │ Nightly │─────▶│ Daily    │────▶│ PR Review │────▶│ Review & │
  │ QA      │      │ Dev      │     │           │     │ Merge    │
  └─────────┘      └──────────┘     └───────────┘     └──────────┘
       │                │                 │                  │
       ▼                ▼                 ▼                  ▼
  PRODUCT_         DEV_SESSION_      PR approved        Next nightly
  DIRECTION        LOG + PR          or changes         sees merged
  + QA_FINDINGS    (draft)           requested          work
```

## Routines

| Routine | Trigger | Purpose | Daily runs |
|---------|---------|---------|------------|
| `nightly-qa` | Scheduled 02:00 ET | Regression + reasonability + product direction | 1 |
| `daily-dev` | Scheduled 09:00 ET | Implement one item from PRODUCT_DIRECTION | 1 |
| `pr-review` | GitHub `pull_request.opened` (feat/auto-*) | Code review + approve/reject | 1 |
| `qa-on-pr` | GitHub `pull_request.opened` (all) | Golden regression tests | 1-3 |
| `qa-on-demand` | API POST | Ad-hoc investigation | 0-2 |
| **Total** | | | **4-8** |

Max plan cap: 15/day. Comfortable headroom.

## Information Flow

- **Nightly → Daily Dev:** `PRODUCT_DIRECTION_{date}.md` provides
  the prioritised backlog. `CONTINUATION_*.md` files carry
  multi-session feature state.
- **Daily Dev → PR Review:** Draft PR triggers the review routine.
  `DEV_SESSION_LOG` in the PR provides review context.
- **PR Review → You:** PR is either marked ready-for-review (approved)
  or left in draft with changes requested.
- **You → Nightly:** Merged PRs are detected by the nightly routine,
  which marks items as DONE in the next PRODUCT_DIRECTION.

## Multi-Session Features

Large features (>1 session) are decomposed into independently
mergeable slices using the CONTINUATION file pattern. See
`daily_dev.md` for decomposition patterns and the substandard
rating worked example.

## Routine Prompt Files

- [`nightly_qa.md`](nightly_qa.md) — not yet saved here; prompt is
  in the routine UI at claude.ai/code/routines
- [`daily_dev.md`](daily_dev.md) — daily development routine
- [`pr_review.md`](pr_review.md) — automated PR review
