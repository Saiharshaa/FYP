# Verifier reliability: `verify-pilot-q15b`

Corpus `pilot-q15b`: 400 candidates on 40 problems, 273 correct (base rate 68.2%). Generator qwen2.5-coder-1.5b-instruct-q4km; verifier `qwen2.5-coder-1.5b-instruct-q4km` (**self-verification**).

Accept = verdict CORRECT. FAR = share of incorrect code accepted; FRR = share of correct code rejected; no verdict counts as reject. 95% CIs: bootstrap over problems (2000 resamples).

Verdict parsers: **v1** is the pre-registered run-time parser (`VERDICT: X`, else a leading bare word); **v2** also accepts a LaTeX `\boxed{CORRECT}` answer. Rows marked v2 appear only where v2 changes a verdict.

| Strategy | n | Accuracy | FAR (false accept) | FRR (false reject) | MCC | No verdict | Out tok | Latency |
|---|---|---|---|---|---|---|---|---|
| direct [v1] single call, seeds [0] | 400 | 68.2% [56.0%, 79.2%] | 100.0% [100.0%, 100.0%] | 0.0% [0.0%, 0.0%] | 0.000 [0.000, 0.000] | 0.0% | 7 | 6.7s |
| direct-swapped [v1] single call, seeds [0] | 400 | 63.7% [52.2%, 75.2%] | 100.0% [100.0%, 100.0%] | 6.6% [0.4%, 15.7%] | -0.148 [-0.240, -0.035] | 0.0% | 7 | 7.2s |
| reason [v1] single call, seeds [0] | 400 | 56.2% [45.5%, 66.0%] | 93.7% [88.1%, 97.9%] | 20.5% [11.1%, 32.4%] | -0.180 [-0.302, -0.055] | 11.2% | 403 | 32.7s |
| reason [v2] single call, seeds [0] | 400 | 57.2% [46.0%, 67.2%] | 95.3% [90.2%, 98.8%] | 18.3% [9.3%, 30.6%] | -0.182 [-0.300, -0.055] | 9.2% | 403 | 32.7s |
| baseline: always accept | 400 | 68.2% | 100.0% | 0.0% | 0.000 | – | – | – |
| baseline: always reject | 400 | 31.8% | 0.0% | 100.0% | 0.000 | – | – | – |

Parser check: 1200 logged calls; re-parsing with v1 reproduces the logged verdict for all but 0; v2 changes direct: 0, direct-swapped: 0, reason: 8 calls.

## direct [v1]

False-accept rate by failure category (incorrect code only):

| Category | n calls | Accepted | FAR |
|---|---|---|---|
| error | 17 | 17 | 100.0% |
| slow | 3 | 3 | 100.0% |
| timeout | 6 | 6 | 100.0% |
| wrong_output | 101 | 101 | 100.0% |

By sampling temperature of the candidate:

| T | n | Accuracy | FAR | FRR | MCC |
|---|---|---|---|---|---|
| 0.2 | 200 | 70.5% | 100.0% | 0.0% | 0.000 |
| 0.8 | 200 | 66.0% | 100.0% | 0.0% | 0.000 |

FAR by whether the model's own code block parsed (sanitize repairs syntax errors):

- parses=True: 127/127 accepted (100.0%)

Across seeds (mean ± sd): accuracy 68.2% ± 0.0%; far 100.0% ± 0.0%; frr 0.0% ± 0.0%; mcc 0.000 ± 0.000
With no-verdict calls excluded (0 dropped): accuracy 68.2%, FAR 100.0%, FRR 0.0%, MCC 0.000.
Cost: 400 calls, mean 429 in / 7 out tokens, 0 truncated at max_tokens.

## direct-swapped [v1]

False-accept rate by failure category (incorrect code only):

| Category | n calls | Accepted | FAR |
|---|---|---|---|
| error | 17 | 17 | 100.0% |
| slow | 3 | 3 | 100.0% |
| timeout | 6 | 6 | 100.0% |
| wrong_output | 101 | 101 | 100.0% |

By sampling temperature of the candidate:

| T | n | Accuracy | FAR | FRR | MCC |
|---|---|---|---|---|---|
| 0.2 | 200 | 67.0% | 100.0% | 5.0% | -0.123 |
| 0.8 | 200 | 60.5% | 100.0% | 8.3% | -0.173 |

FAR by whether the model's own code block parsed (sanitize repairs syntax errors):

- parses=True: 127/127 accepted (100.0%)

Across seeds (mean ± sd): accuracy 63.7% ± 0.0%; far 100.0% ± 0.0%; frr 6.6% ± 0.0%; mcc -0.148 ± 0.000
With no-verdict calls excluded (0 dropped): accuracy 63.7%, FAR 100.0%, FRR 6.6%, MCC -0.148.
Cost: 400 calls, mean 429 in / 7 out tokens, 0 truncated at max_tokens.

## reason [v1]

False-accept rate by failure category (incorrect code only):

| Category | n calls | Accepted | FAR |
|---|---|---|---|
| error | 17 | 16 | 94.1% |
| slow | 3 | 3 | 100.0% |
| timeout | 6 | 6 | 100.0% |
| wrong_output | 101 | 94 | 93.1% |

By sampling temperature of the candidate:

| T | n | Accuracy | FAR | FRR | MCC |
|---|---|---|---|---|---|
| 0.2 | 200 | 56.5% | 98.3% | 20.6% | -0.241 |
| 0.8 | 200 | 56.0% | 89.7% | 20.5% | -0.128 |

FAR by whether the model's own code block parsed (sanitize repairs syntax errors):

- parses=True: 119/127 accepted (93.7%)

Across seeds (mean ± sd): accuracy 56.2% ± 0.0%; far 93.7% ± 0.0%; frr 20.5% ± 0.0%; mcc -0.180 ± 0.000
With no-verdict calls excluded (45 dropped): accuracy 62.0%, FAR 97.5%, FRR 6.9%, MCC -0.093.
Cost: 400 calls, mean 454 in / 403 out tokens, 15 truncated at max_tokens.

## reason [v2]

False-accept rate by failure category (incorrect code only):

| Category | n calls | Accepted | FAR |
|---|---|---|---|
| error | 17 | 16 | 94.1% |
| slow | 3 | 3 | 100.0% |
| timeout | 6 | 6 | 100.0% |
| wrong_output | 101 | 96 | 95.0% |

By sampling temperature of the candidate:

| T | n | Accuracy | FAR | FRR | MCC |
|---|---|---|---|---|---|
| 0.2 | 200 | 59.0% | 98.3% | 17.0% | -0.211 |
| 0.8 | 200 | 55.5% | 92.6% | 19.7% | -0.162 |

FAR by whether the model's own code block parsed (sanitize repairs syntax errors):

- parses=True: 121/127 accepted (95.3%)

Across seeds (mean ± sd): accuracy 57.2% ± 0.0%; far 95.3% ± 0.0%; frr 18.3% ± 0.0%; mcc -0.182 ± 0.000
With no-verdict calls excluded (37 dropped): accuracy 62.3%, FAR 97.6%, FRR 6.7%, MCC -0.091.
Cost: 400 calls, mean 454 in / 403 out tokens, 15 truncated at max_tokens.

## Corpus

- Pass rate by temperature: T=0.2: 70.5%, T=0.8: 66.0%
- Failure categories: {'wrong_output': 101, 'timeout': 6, 'slow': 3, 'error': 17}
- Model code blocks with syntax errors (before sanitize): 0
- Generations truncated at max_tokens: 0
- Labels: evalplus 6eb1e19, HumanEvalPlus v0.1.10, timeout ×5, 1 worker(s), host DESKTOP-AH0HVC6
