# Verifier reliability: `verify-pilot-q15b`

Corpus `pilot-q15b`: 400 candidates on 40 problems, 273 correct (base rate 68.2%). Generator qwen2.5-coder-1.5b-instruct-q4km; verifier `qwen2.5-coder-1.5b-instruct-q4km` (**self-verification**).

Accept = verdict CORRECT. FAR = share of incorrect code accepted; FRR = share of correct code rejected; no verdict counts as reject. 95% CIs: bootstrap over problems (2000 resamples).

Verdict parsers: **v1** is the pre-registered run-time parser (`VERDICT: X`, else a leading bare word); **v2** also accepts a LaTeX `\boxed{CORRECT}` answer. Rows marked v2 appear only where v2 changes a verdict.

| Strategy | n | Accuracy | FAR (false accept) | FRR (false reject) | MCC | No verdict | Out tok | Latency |
|---|---|---|---|---|---|---|---|---|
| direct [v1] single call, seeds [0] | 400 | 68.2% [56.0%, 79.2%] | 100.0% [100.0%, 100.0%] | 0.0% [0.0%, 0.0%] | 0.000 [0.000, 0.000] | 0.0% | 7 | 6.7s |
| direct-swapped [v1] single call, seeds [0] | 400 | 63.7% [52.2%, 75.2%] | 100.0% [100.0%, 100.0%] | 6.6% [0.4%, 15.7%] | -0.148 [-0.240, -0.035] | 0.0% | 7 | 7.2s |
| reason [v1] single call, seeds [0, 1, 2] | 1200 | 60.2% [51.5%, 68.7%] | 87.4% [78.6%, 93.5%] | 17.6% [13.0%, 22.6%] | -0.063 [-0.165, 0.056] | 12.4% | 385 | 32.3s |
| reason [v1] majority vote (3 seeds) | 400 | 66.5% [56.0%, 76.8%] | 90.6% [76.6%, 98.6%] | 7.0% [2.4%, 13.7%] | 0.043 [-0.145, 0.265] | – | ×3 | ×3 |
| reason [v2] single call, seeds [0, 1, 2] | 1200 | 60.2% [50.9%, 69.0%] | 91.6% [87.1%, 95.3%] | 15.6% [11.3%, 20.5%] | -0.099 [-0.173, -0.017] | 9.8% | 385 | 32.3s |
| reason [v2] majority vote (3 seeds) | 400 | 64.5% [53.0%, 75.0%] | 98.4% [95.6%, 100.0%] | 6.2% [2.1%, 12.0%] | -0.102 [-0.185, -0.003] | – | ×3 | ×3 |
| baseline: always accept | 400 | 68.2% | 100.0% | 0.0% | 0.000 | – | – | – |
| baseline: always reject | 400 | 31.8% | 0.0% | 100.0% | 0.000 | – | – | – |

Parser check: 2000 logged calls; re-parsing with v1 reproduces the logged verdict for all but 0; v2 changes direct: 0, direct-swapped: 0, reason: 32 calls.

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
| error | 51 | 46 | 90.2% |
| slow | 9 | 8 | 88.9% |
| timeout | 18 | 17 | 94.4% |
| wrong_output | 303 | 262 | 86.5% |

By sampling temperature of the candidate:

| T | n | Accuracy | FAR | FRR | MCC |
|---|---|---|---|---|---|
| 0.2 | 600 | 62.8% | 87.6% | 16.1% | -0.047 |
| 0.8 | 600 | 57.7% | 87.3% | 19.2% | -0.081 |

FAR by whether the model's own code block parsed (sanitize repairs syntax errors):

- parses=True: 333/381 accepted (87.4%)

Across seeds (mean ± sd): accuracy 60.2% ± 3.9%; far 87.4% ± 5.9%; frr 17.6% ± 4.5%; mcc -0.062 ± 0.104
With no-verdict calls excluded (149 dropped): accuracy 65.4%, FAR 96.5%, FRR 4.4%, MCC -0.022.
Cost: 1200 calls, mean 454 in / 385 out tokens, 28 truncated at max_tokens.

## reason [v2]

False-accept rate by failure category (incorrect code only):

| Category | n calls | Accepted | FAR |
|---|---|---|---|
| error | 51 | 47 | 92.2% |
| slow | 9 | 8 | 88.9% |
| timeout | 18 | 17 | 94.4% |
| wrong_output | 303 | 277 | 91.4% |

By sampling temperature of the candidate:

| T | n | Accuracy | FAR | FRR | MCC |
|---|---|---|---|---|---|
| 0.2 | 600 | 63.2% | 92.7% | 13.5% | -0.087 |
| 0.8 | 600 | 57.3% | 90.7% | 17.9% | -0.114 |

FAR by whether the model's own code block parsed (sanitize repairs syntax errors):

- parses=True: 349/381 accepted (91.6%)

Across seeds (mean ± sd): accuracy 60.2% ± 3.3%; far 91.6% ± 3.6%; frr 15.6% ± 3.2%; mcc -0.097 ± 0.089
With no-verdict calls excluded (117 dropped): accuracy 64.9%, FAR 96.7%, FRR 4.3%, MCC -0.023.
Cost: 1200 calls, mean 454 in / 385 out tokens, 28 truncated at max_tokens.

## Corpus

- Pass rate by temperature: T=0.2: 70.5%, T=0.8: 66.0%
- Failure categories: {'wrong_output': 101, 'timeout': 6, 'slow': 3, 'error': 17}
- Model code blocks with syntax errors (before sanitize): 0
- Generations truncated at max_tokens: 0
- Labels: evalplus 6eb1e19, HumanEvalPlus v0.1.10, timeout ×5, 1 worker(s), host DESKTOP-AH0HVC6
