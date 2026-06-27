# Actuarial Glossary — Polaris RE

Reference for developers who are not credentialed actuaries. Consult before implementing any business logic.

---

## Core Concepts

**Attained Age** — The insured's current age, as opposed to issue age (age when the policy was issued). Mortality rates are typically looked up by attained age.

**Age Nearest Birthday (ANB)** — Age calculated as the age at the nearest birthday. If someone is 45 years and 4 months old, their ANB is 45. Most Canadian and some US tables use ANB.

**Age Last Birthday (ALB)** — Age calculated as the age at the last birthday. Same person above would be ALB = 45. Most US regulatory tables use ALB.

**Select Period** — The period after underwriting during which newly insured lives have lower mortality rates than the general insured population (because they just passed a medical exam). Typically 15–25 years for individual life.

**Select and Ultimate Table** — A two-dimensional mortality table where rates depend on both attained age *and* duration since selection (i.e., since the policy was issued). After the select period, rates become "ultimate" — dependent on attained age only.

**Ultimate Table** — The mortality rates that apply after the select period ends. Also used as a simple approximation when select rates aren't available.

---

## Mortality

**q_x** — The probability that a life aged exactly x dies before reaching age x+1. The fundamental unit of a mortality table. Read as "q of x."

**l_x** — The number of survivors in a standard mortality table at age x, starting from a radix (typically 100,000 at age 0). `l_{x+1} = l_x × (1 - q_x)`.

**In-Force Factor (lx in code)** — The expected fraction of the original cohort still alive and in-force at time t. At t=0, lx = 1.0. Decrements from both mortality (q) and lapse (w) are applied each period.

**Mortality Improvement** — The secular trend of declining mortality rates over time. Applied as multiplicative factors to base table rates. Key scales:
- **Scale AA** (SOA) — age-only, single factor per age, applied as `q * (1 - AA_factor)^years`
- **MP-2020** (SOA) — 2D table indexed by age and calendar year (2015–2031); factors vary by both dimensions; rates held constant at 2031 values for years beyond
- **CPM-B** (CIA) — Canadian age-only scale; applied as `q * (1 - CPM_factor)^years`

**A/E Ratio** — Actual-to-Expected ratio. If 100 deaths were expected based on the table but 87 occurred, A/E = 87%. A key metric in experience studies.

**CIA 2014** — The 2014 Canadian Institute of Actuaries Individual Life Mortality Study table. The standard Canadian industry base table for individual life insurance.

**SOA VBT 2015** — The 2015 Society of Actuaries Valuation Basic Table. The standard US individual life reinsurance pricing table. Select and ultimate.

**2001 CSO** — Commissioner's Standard Ordinary 2001 table. The US regulatory minimum mortality basis for CRVM/CARVM reserves. Being replaced by 2017 CSO.

---

## Morbidity

**Morbidity** — The rate of illness or disability in a population. Distinct from mortality (death). Used for CI and DI product pricing.

**Incidence Rate** — The probability of a new disability or critical illness event in a given period. Analogous to q_x for mortality.

**Termination Rate** — For disabled lives, the probability of exiting the disabled state (recovery + disability mortality combined). Only applicable to DI products.

**Multi-State Model** — A projection model tracking transitions between states. For DI: Active → Disabled (via incidence), Disabled → Recovered/Dead (via termination). Two parallel lx arrays (`lx_active`, `lx_disabled`) are maintained.

**Single-Decrement Model** — A simpler model where claims are a one-time event. For CI: policies transition Active → Claim → Terminated. No recovery state.

---

## Insurance Product Types

**Term Life** — Life insurance providing a death benefit for a fixed term (e.g., 10, 20, 30 years). No cash value. Lapses heavily in early durations. The most common individual life reinsurance product.

**Whole Life** — Permanent life insurance with guaranteed death benefit and cash value accumulation. Participating (par) policies pay dividends. Significantly higher reserves than term.

**Universal Life (UL)** — Flexible premium permanent insurance. Policyholder accumulates an account value that earns interest. Cost of insurance (COI) charges are deducted monthly. Key mechanics:
- **Account Value (AV):** The policyholder's accumulated fund. `AV_{t+1} = (AV_t + premium - expense) * (1 + credited_rate/12) - COI`
- **Cost of Insurance (COI):** Monthly mortality charge based on NAR. `COI = NAR * q / (1 + i/12)` where NAR = max(face - AV, 0)
- **Credited Rate:** Interest rate applied to the account value each month. Set by the insurer (subject to a minimum guarantee).
- **Forced Lapse:** When AV drops to zero (due to insufficient premium or high COI), the policy lapses automatically.
- **Surrender Charge:** A penalty deducted from AV upon policy surrender, typically declining over 10+ years.

**Disability Income (DI)** — Replaces income if the insured becomes disabled. Requires morbidity tables (incidence, termination, duration of disability) rather than mortality tables.

**Critical Illness (CI)** — Pays a lump sum upon diagnosis of a specified illness (cancer, heart attack, stroke, etc.). Combined mortality and morbidity modelling.

---

## Actuarial Mathematics

**Net Amount at Risk (NAR)** — The amount the insurer is "at risk" for if a death occurs: `NAR = Face Amount - Reserve`. In a YRT treaty, the reinsurer's exposure is based on NAR, not face amount.

**Present Value (PV)** — The value today of a future cash flow, discounted at an assumed interest rate. `PV = CF_t × v^t` where `v = 1/(1+i)`.

**Actuarial Present Value (APV)** — Present value weighted by the probability that the cash flow occurs. For a death benefit: `APV = Σ lx_t × q_t × benefit × v^t`.

**Net Premium** — The premium calculated purely on the basis of mortality and interest, with no expense loading. `Net Premium = APV(benefits) / APV(annuity)`.

**Gross Premium** — The actual premium charged, including expense loadings and profit margin.

**Reserve** — The liability the insurer must hold to pay future benefits. Calculated as `APV(future benefits) - APV(future net premiums)` on a prospective basis, or equivalently accumulated from past premiums and claims. Reserves grow with policy duration for whole life; term reserves peak mid-term and return to zero at expiry.

**Reserve Recursion** — A formula expressing the reserve at time t+1 in terms of the reserve at time t: `(V_t + P_t) × (1+i)^(1/12) = q_t × b_t + (1-q_t) × V_{t+1}`. Used to compute reserves efficiently in a projection.

**Discount Factor (v)** — `v = 1/(1+i)` where i is the interest rate per period.

**Annuity Value (ä_x)** — The APV of a series of $1 payments while the life aged x survives. Appears in the denominator of the net premium formula.

---

## Reinsurance

**Cession / Cession Percentage** — The proportion of a policy that is transferred (ceded) to the reinsurer. E.g., 50% cession means the reinsurer takes on 50% of the risk.

**Cedant** — The primary insurer that is transferring risk to the reinsurer.

**Treaty** — The contract between cedant and reinsurer defining the terms of risk transfer.

**YRT (Yearly Renewable Term)** — The most common individual life reinsurance structure. The reinsurer charges a premium based on NAR each year (or month), renewing annually at rates specified in the treaty rate schedule. The cedant retains the reserve; only mortality risk is transferred.

**Coinsurance** — A proportional reinsurance structure where the reinsurer takes a share of all cash flows including reserves. Transfers both mortality risk and investment/lapse risk.

**Modified Coinsurance (Modco)** — Like coinsurance, but the cedant retains the assets backing ceded reserves. The reinsurer receives a modco adjustment (interest on the ceded reserve balance) to compensate.

**Quota Share** — A simple proportional structure where the reinsurer takes a fixed percentage of premium and pays the same percentage of claims. Essentially a simplified coinsurance without reserve transfer.

**Stop Loss** — An aggregate reinsurance structure where the reinsurer pays claims above an attachment point (and up to an exhaustion point). Less common in individual life, more common in group and health.

**Retention Limit** — The maximum face amount per policy that the cedant retains. Any excess is automatically ceded. E.g., a $1M retention limit means the reinsurer covers all face amount above $1M on any single policy.

**Automatic vs. Facultative** — Automatic reinsurance applies to all qualifying policies under a treaty. Facultative reinsurance is negotiated policy-by-policy for unusual risks (e.g., large face amounts, substandard lives).

---

## Financial Metrics

**IRR (Internal Rate of Return)** — The discount rate at which the net present value of all projected cash flows equals zero. The primary profitability metric for reinsurance deal pricing. A deal is attractive if IRR exceeds the cost of capital.

**Break-Even Duration** — The number of years until the cumulative present value of profits turns positive. Important for capital planning.

**Profit Margin** — PV of profits divided by PV of premiums. Indicates the profitability per dollar of premium written.

**Loss Ratio** — Claims paid divided by premiums earned. A common operational metric. A loss ratio above ~70-80% typically indicates an unprofitable book.

**Combined Ratio** — Loss ratio + expense ratio. Above 100% means the book is unprofitable on an underwriting basis (excluding investment income).

---

## Risk Quantification

**Value at Risk (VaR)** — The worst-case loss at a given confidence level. VaR_95 is the 5th percentile of the PV profit distribution — there is a 5% probability of outcomes worse than this. In Polaris RE, computed from the Monte Carlo distribution of PV profits.

**Conditional Value at Risk (CVaR)** — Also called Expected Shortfall. The average loss in the tail beyond VaR. CVaR_95 = mean of PV profits in the worst 5% of scenarios. Always worse than (or equal to) VaR. A more complete measure of tail risk.

**Monte Carlo Simulation** — Random sampling from assumption distributions to build an empirical distribution of outcomes. Polaris RE samples mortality multipliers (LogNormal), lapse multipliers (LogNormal), and interest rate shifts (Normal) to produce N scenarios of PV profits and IRRs.

**LogNormal Distribution** — Used for assumption multipliers because it is strictly positive (cannot produce negative mortality or lapse rates) and has mean ≈ 1 for small sigma. `multiplier ~ LogNormal(mu=0, sigma)` gives `E[multiplier] = exp(sigma^2 / 2) ≈ 1`.

---

## Financial Metrics and Reporting

**IFRS 17** — The international financial reporting standard for insurance contracts, effective 2023. Requires a building-block approach (BBA) with explicit risk adjustment and contractual service margin (CSM). The CSM represents unearned profit and is released over the coverage period. This is the primary accounting framework for Munich Re.

---

## Regulatory Capital

**Required Capital** — The amount of capital a regulator requires the (re)insurer to hold against a block of business, computed at each projection month. In Polaris RE it is a positive, time-varying schedule; it is NOT discounted at the hurdle rate (the time-value adjustment lives in return-on-capital). Each jurisdiction defines its own formula.

**Return on Capital (RoC)** — PV of profits divided by PV of the required-capital stock, at the hurdle rate. The primary decision metric for reinsurance deal pricing on a capital basis: a deal is attractive when RoC exceeds the cost of capital (8–12% for life reinsurance). Distinct from the *solvency ratio* below — RoC measures profitability per dollar of capital held; the solvency ratio measures whether the company holds enough capital.

**LICAT (Life Insurance Capital Adequacy Test)** — OSFI's Canadian regulatory capital standard. Built from C-1 (asset default), C-2 (insurance risk — mortality + lapse + morbidity), and C-3 (interest-rate) components. The **LICAT total ratio** is available capital ÷ required capital.

**US RBC (Risk-Based Capital)** — The NAIC's US standard. Aggregates the C-0…C-4 components by the **covariance square root** (asset and insurance risk are imperfectly correlated, so they do not simply sum). The covariance result is the **Company Action Level (CAL)**; the **Authorized Control Level (ACL)** is half the CAL. The **RBC ratio** is Total Adjusted Capital (TAC) ÷ ACL — the number a US regulator reads (e.g. 300% = a healthy position).

**Solvency II SCR (Solvency Capital Requirement)** — The EU standard. A modular standard-formula requirement: life-underwriting sub-modules (mortality / lapse / catastrophe), market, and counterparty risk are aggregated through correlation matrices into the Basic SCR, with operational risk added outside the matrix. The **EU solvency ratio** is eligible **own funds** ÷ SCR.

**Capital Ratio (solvency ratio)** — The unified Polaris RE surface (`CapitalSchedule.capital_ratio(available_capital)`) for the three jurisdiction ratios above: `available_capital ÷ denominator₀`, evaluated at issue (projection month 0), expressed as a multiple. The numerator (available capital / TAC / own funds) is uniform; the *denominator* is the jurisdictional difference — required capital for LICAT, ACL for RBC, SCR for Solvency II. Surfaced on `ProfitResultWithCapital.capital_ratio` when `ProfitTester.run_with_capital` is given an `available_capital` numerator.

## Asset / ALM

**Book Yield** — The gross effective-annual internal rate of return that equates an asset portfolio's carrying (book) value to its projected coupon + principal cash flows. In Polaris RE (`AssetPortfolio.book_yield()`) it is a single scalar held flat over the horizon, and — when supplied — it drives the Modco interest in place of a hand-set credited rate (the rate the backing assets actually earn).

**Macaulay Duration** — The present-value-weighted average time (in years) to a stream's cash flows. For a zero-coupon instrument it equals the time to maturity; coupon-paying instruments are shorter because intermediate coupons pull the average in.

**Modified Duration** — The first-order price sensitivity `-(1/P) dP/dy` — the approximate percentage change in value per unit change in yield. Under the effective-annual yield convention it is `Macaulay ÷ (1 + y)`. The hedgeable measure: matching asset and liability modified durations immunises surplus against small parallel yield moves.

**Convexity** — The second-order price sensitivity `(1/P) d²P/dy²` (in years²). Captures the curvature modified duration misses; longer and more dispersed cash flows have higher convexity.

**Duration Gap** — The difference between the modified duration of the assets backing a block and that of the liability they fund (`asset − liability`, in years). A positive gap means the assets re-price faster than the liability as yields move (longer assets); a negative gap the reverse. The **dollar-duration gap** scales each side by its value (`modified duration × value`) and differences them, giving the net change in surplus per unit change in yield — the quantity an ALM hedge targets. In Polaris RE both sides are measured at one common flat valuation yield (`analytics/alm.py::duration_gap`), isolating the timing mismatch from any yield-basis difference.
