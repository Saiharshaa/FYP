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
| reference [v1] single call, seeds [0, 1, 2] | 1200 | 55.8% [48.6%, 63.0%] | 18.6% [10.9%, 25.2%] | 56.2% [46.4%, 65.2%] | 0.245 [0.147, 0.347] | 46.7% | 48 | 3.8s |
| reference [v1] majority vote (3 seeds) | 400 | 58.0% [45.0%, 70.5%] | 6.3% [1.7%, 12.4%] | 58.6% [41.7%, 74.2%] | 0.356 [0.207, 0.503] | – | ×3 | ×3 |
| self-tests [v1] single call, seeds [0, 1, 2] | 1200 | 42.7% [31.8%, 53.2%] | 6.0% [0.4%, 15.7%] | 81.2% [69.8%, 91.1%] | 0.168 [-0.009, 0.304] | 15.8% | 63 | 4.9s |
| self-tests [v1] majority vote (3 seeds) | 400 | 42.0% [29.8%, 54.5%] | 5.5% [0.0%, 15.6%] | 82.4% [67.0%, 96.1%] | 0.163 [-0.074, 0.327] | – | ×3 | ×3 |
| self-tests [v2] single call, seeds [0, 1, 2] | 1200 | 44.4% [34.1%, 54.6%] | 8.9% [1.3%, 19.2%] | 77.3% [65.0%, 87.8%] | 0.166 [-0.006, 0.314] | 2.5% | 63 | 4.9s |
| self-tests [v2] majority vote (3 seeds) | 400 | 44.5% [32.5%, 57.0%] | 5.5% [0.0%, 15.6%] | 78.8% [61.8%, 92.8%] | 0.199 [-0.016, 0.360] | – | ×3 | ×3 |
| baseline: always accept | 400 | 68.2% | 100.0% | 0.0% | 0.000 | – | – | – |
| baseline: always reject | 400 | 31.8% | 0.0% | 100.0% | 0.000 | – | – | – |

Parser check: 2000 logged calls; re-parsing with v1 reproduces the logged verdict for all but 0; v2 changes direct: 0, direct-swapped: 0, reason: 32, self-tests: 160, reference: 0 calls.

## Selection (RQ4)

Pick one candidate per problem: random (expected), verifier (random among accepted; random if none accepted), oracle (a correct one if any). Headroom captured = (verifier − random) / (oracle − random): 0 = random, 1 = oracle.

| Strategy | Random | Verifier | Oracle | Headroom captured |
|---|---|---|---|---|
| direct [v1] single call (mean over seeds) | 68.2% | 68.2% | 90.0% | +0.00 |
| direct-swapped [v1] single call (mean over seeds) | 68.2% | 68.1% | 90.0% | -0.01 |
| reason [v1] single call (mean over seeds) | 68.2% | 67.8% | 90.0% | -0.02 |
| reason [v1] majority vote | 68.2% | 69.4% | 90.0% | +0.05 [-0.02, +0.15] |
| reason [v2] single call (mean over seeds) | 68.2% | 67.9% | 90.0% | -0.01 |
| reason [v2] majority vote | 68.2% | 68.4% | 90.0% | +0.01 [-0.02, +0.04] |
| reference [v1] single call (mean over seeds) | 68.2% | 69.8% | 90.0% | +0.07 |
| reference [v1] majority vote | 68.2% | 69.3% | 90.0% | +0.05 [-0.32, +0.31] |
| self-tests [v1] single call (mean over seeds) | 68.2% | 67.7% | 90.0% | -0.03 |
| self-tests [v1] majority vote | 68.2% | 66.5% | 90.0% | -0.08 [-0.36, +0.05] |
| self-tests [v2] single call (mean over seeds) | 68.2% | 68.5% | 90.0% | +0.01 |
| self-tests [v2] majority vote | 68.2% | 66.5% | 90.0% | -0.08 [-0.36, +0.05] |
Execution strategy `reference`: verdicts from running code (exec.jsonl); 1200 candidate executions, 46.7% with no verdict (unusable tests/reference); errors {'reference:NameError': 100, 'no_reference': 200, 'reference:TimeoutError': 1, 'reference:MemoryError': 12, 'reference:TypeError': 70, 'reference:UnboundLocalError': 10, 'no_result': 5, 'reference:AttributeError': 10, 'reference:ValueError': 10, 'reference:SystemError': 5}. Tokens and latency are per candidate (one model call per problem and seed, split over its candidates).
Execution strategy `self-tests`: verdicts from running code (exec.jsonl); 1200 candidate executions, 15.8% with no verdict (unusable tests/reference); errors {}. Tokens and latency are per candidate (one model call per problem and seed, split over its candidates).

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

## reference [v1]

False-accept rate by failure category (incorrect code only):

| Category | n calls | Accepted | FAR |
|---|---|---|---|
| error | 51 | 1 | 2.0% |
| slow | 9 | 0 | 0.0% |
| timeout | 18 | 0 | 0.0% |
| wrong_output | 303 | 70 | 23.1% |

By sampling temperature of the candidate:

| T | n | Accuracy | FAR | FRR | MCC |
|---|---|---|---|---|---|
| 0.2 | 600 | 54.0% | 21.5% | 56.3% | 0.210 |
| 0.8 | 600 | 57.5% | 16.2% | 56.1% | 0.277 |

FAR by whether the model's own code block parsed (sanitize repairs syntax errors):

- parses=True: 71/381 accepted (18.6%)

Across seeds (mean ± sd): accuracy 55.8% ± 3.3%; far 18.6% ± 13.8%; frr 56.2% ± 7.3%; mcc 0.251 ± 0.103
With no-verdict calls excluded (560 dropped): accuracy 74.4%, FAR 37.8%, FRR 20.6%, MCC 0.404.
Cost: 1200 calls, mean 32 in / 48 out tokens, 200 truncated at max_tokens.

## self-tests [v1]

False-accept rate by failure category (incorrect code only):

| Category | n calls | Accepted | FAR |
|---|---|---|---|
| error | 51 | 0 | 0.0% |
| slow | 9 | 3 | 33.3% |
| timeout | 18 | 15 | 83.3% |
| wrong_output | 303 | 5 | 1.7% |

By sampling temperature of the candidate:

| T | n | Accuracy | FAR | FRR | MCC |
|---|---|---|---|---|---|
| 0.2 | 600 | 40.8% | 6.8% | 81.1% | 0.154 |
| 0.8 | 600 | 44.5% | 5.4% | 81.3% | 0.181 |

FAR by whether the model's own code block parsed (sanitize repairs syntax errors):

- parses=True: 23/381 accepted (6.0%)

Across seeds (mean ± sd): accuracy 42.7% ± 2.7%; far 6.0% ± 1.2%; frr 81.2% ± 4.3%; mcc 0.167 ± 0.036
With no-verdict calls excluded (190 dropped): accuracy 45.2%, FAR 7.1%, FRR 77.5%, MCC 0.190.
Cost: 1200 calls, mean 31 in / 63 out tokens, 480 truncated at max_tokens.

## self-tests [v2]

False-accept rate by failure category (incorrect code only):

| Category | n calls | Accepted | FAR |
|---|---|---|---|
| error | 51 | 0 | 0.0% |
| slow | 9 | 5 | 55.6% |
| timeout | 18 | 15 | 83.3% |
| wrong_output | 303 | 14 | 4.6% |

By sampling temperature of the candidate:

| T | n | Accuracy | FAR | FRR | MCC |
|---|---|---|---|---|---|
| 0.2 | 600 | 42.8% | 9.6% | 77.1% | 0.155 |
| 0.8 | 600 | 46.0% | 8.3% | 77.5% | 0.176 |

FAR by whether the model's own code block parsed (sanitize repairs syntax errors):

- parses=True: 34/381 accepted (8.9%)

Across seeds (mean ± sd): accuracy 44.4% ± 1.9%; far 8.9% ± 4.5%; frr 77.3% ± 0.7%; mcc 0.167 ± 0.065
With no-verdict calls excluded (30 dropped): accuracy 44.1%, FAR 9.3%, FRR 76.9%, MCC 0.163.
Cost: 1200 calls, mean 31 in / 63 out tokens, 480 truncated at max_tokens.

## Corpus

- Pass rate by temperature: T=0.2: 70.5%, T=0.8: 66.0%
- Failure categories: {'wrong_output': 101, 'timeout': 6, 'slow': 3, 'error': 17}
- Model code blocks with syntax errors (before sanitize): 0
- Generations truncated at max_tokens: 0
- Labels: evalplus 6eb1e19, HumanEvalPlus v0.1.10, timeout ×5, 1 worker(s), host DESKTOP-AH0HVC6
