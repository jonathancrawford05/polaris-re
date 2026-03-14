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

**Mortality Improvement** — The secular trend of declining mortality rates over time. Applied as multiplicative factors to base table rates. Key scales: SOA Scale AA (older), MP-2020 (more recent), CPM Improvement Scale B (Canadian).

**A/E Ratio** — Actual-to-Expected ratio. If 100 deaths were expected based on the table but 87 occurred, A/E = 87%. A key metric in experience studies.

**CIA 2014** — The 2014 Canadian Institute of Actuaries Individual Life Mortality Study table. The standard Canadian industry base table for individual life insurance.

**SOA VBT 2015** — The 2015 Society of Actuaries Valuation Basic Table. The standard US individual life reinsurance pricing table. Select and ultimate.

**2001 CSO** — Commissioner's Standard Ordinary 2001 table. The US regulatory minimum mortality basis for CRVM/CARVM reserves. Being replaced by 2017 CSO.

---

## Insurance Product Types

**Term Life** — Life insurance providing a death benefit for a fixed term (e.g., 10, 20, 30 years). No cash value. Lapses heavily in early durations. The most common individual life reinsurance product.

**Whole Life** — Permanent life insurance with guaranteed death benefit and cash value accumulation. Participating (par) policies pay dividends. Significantly higher reserves than term.

**Universal Life (UL)** — Flexible premium permanent insurance. Policyholder accumulates an account value that earns interest. Cost of insurance (COI) charges are deducted monthly. More complex to model than term or whole life.

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

**IFRS 17** — The international financial reporting standard for insurance contracts, effective 2023. Requires a building-block approach (BBA) with explicit risk adjustment and contractual service margin (CSM). The CSM represents unearned profit and is released over the coverage period. This is the primary accounting framework for Munich Re.
