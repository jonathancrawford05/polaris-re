"""Performance-harness tests (``analytics/perf_harness.py``).

These run the projection engine to exercise the deterministic-first perf probe,
so they are tagged ``perf`` **and** ``slow`` — the fast matrix (``make test`` /
CI ``-m "not slow"``) and the Docker job skip them; a dedicated ``perf`` selector
(``make perf`` / ``-m perf``) runs them. They assert the *deterministic* metrics
are reproducible and the timing *arithmetic* (best-of-k = min) holds — never an
absolute wall-clock threshold (the maintainer design rule). All fixtures pin
``valuation_date`` explicitly (ADR-074).
"""
