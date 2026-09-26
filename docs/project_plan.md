# FYP Project Plan

**Agentic Engineering for Collaborative Algorithm Design in OpenClaw**
*Sub-topic: Verification Reliability in Multi-Agent Code Generation*

| | |
|---|---|
| Student | Sai Harsha Venugopal (U2321873F) |
| Programme | Double Degree (Hons), Computer Science & Business |
| Project No. / Course | CCDS26-0044 / SC4079 |
| Supervisor | A/P Chee Wei Tan |
| Academic Year | 2026/27, Semester 1 — Aug 2026 to May 2027 |
| Date | 9 September 2026 |

## 1. Problem Statement

**Main problem to solve.** Multi-agent systems for code generation depend on a step that is rarely examined directly: at some point an agent must judge whether a candidate solution is correct without being shown the answer. A critic accepts or rejects code, an arbiter picks between competing designs, a repair loop decides whether to stop. Every one of these decisions is a verification judgement made without ground truth. If that judgement is unreliable, the surrounding protocol inherits the unreliability — a critic that accepts plausible-looking but incorrect code will confidently pass it downstream, and a critic that rejects correct code will discard good work. This project measures how reliable such verification actually is, what makes it better or worse, and how much of the performance of a collaborative agent system depends on it.

**Why it is important.** Verification is the load-bearing component of agentic engineering, and it is usually assumed rather than measured. Published multi-agent systems report end-to-end accuracy gains but seldom report how often their critic was wrong, or in which direction. Without that number it is impossible to tell whether a protocol works because role separation genuinely helps, or because the benchmark's hidden tests happened to be forgiving. The same problem appears well beyond code generation: any autonomous system that acts on its own self-assessment inherits the error profile of that assessment.

**Potential impact and benefits.** The intended outputs are a reusable, open evaluation harness built on OpenClaw for measuring verifier reliability, a labelled corpus of candidate solutions with ground-truth correctness and failure categories, and an empirical account of which verification strategies are trustworthy and under what conditions. A practical result would be design guidance: a stated reliability threshold below which adding a critic to a pipeline does more harm than good.

## 2. Research Question

Can an agent determine whether generated code is correct without access to ground truth, and does the reliability of that judgement determine the effectiveness of collaborative algorithm design?

## 3. Existing Approaches

The initial survey covers four strands. This list is preliminary and will be expanded during Semester 1.

- **Self-correction and self-critique.** Self-Refine (Madaan et al., 2023) and Reflexion (Shinn et al., 2023) use a model's own feedback to iterate on its output. Huang et al. (2024) argue that large language models cannot yet reliably self-correct reasoning without external feedback, and that apparent gains often come from oracle signals leaking into the loop. This tension is the direct motivation for the project.
- **Execution-grounded verification.** CodeT (Chen et al., 2022) generates test cases alongside solutions and uses agreement between them to rank candidates. Self-Debugging (Chen et al., 2023) feeds execution traces back to the model. These replace opinion with evidence, at additional cost.
- **Trained verifiers.** Cobbe et al. (2021) train separate verifier models to score candidate solutions, and Lightman et al. (2023) show that process-level supervision outperforms outcome-level supervision. These establish that verification is a distinct capability from generation, not a by-product of it.
- **Multi-agent systems and benchmarks.** ChatDev (Qian et al., 2024) and MetaGPT (Hong et al., 2024) assign specialised roles including reviewers and testers. HumanEval (Chen et al., 2021) and MBPP (Austin et al., 2021) are the standard benchmarks; EvalPlus (Liu et al., 2023) shows that their original hidden tests are weak enough to mark incorrect solutions as passing, which matters because those tests will supply this project's ground-truth labels.

## 4. Research Gaps

- **Verification is measured indirectly.** Existing work reports end-to-end task accuracy, not the verifier's own confusion matrix. The false-accept and false-reject rates of the critic agent are almost never published, so the mechanism behind reported gains is unverified.
- **Error asymmetry is unexamined.** Whether verifiers fail predominantly by accepting wrong code or by rejecting right code has different engineering consequences, and no systematic comparison across verification strategies exists.
- **Reliability is not stratified by failure type.** A verifier that catches syntax errors but misses silent off-by-one errors is far less useful than an aggregate accuracy figure suggests.
- **The link between verifier quality and protocol performance is untested.** No published work establishes the threshold at which adding a critic to a pipeline stops helping.

This project addresses these gaps by treating verification as the object of study rather than as a component, measuring it as a classification problem against ground truth, and then connecting that measurement to end-to-end performance.

## 5. Approach

### Aims

- Build a configurable verification framework as an OpenClaw skill package supporting several verification strategies behind a common interface.
- Construct a labelled corpus of candidate solutions with ground-truth correctness and categorised failure modes.
- Measure the reliability of each verification strategy as a classification problem, stratified by failure type.
- Quantify how much end-to-end performance a verifier of a given reliability actually delivers.

### Research Questions and Hypotheses

**RQ1.** How accurately can an agent classify a candidate solution as correct or incorrect without access to the hidden tests?
**H1.** Verification by reading code alone will show a high false-accept rate, because plausible structure is a weak proxy for correctness.

**RQ2.** Does verification strategy change reliability, and at what cost? Strategies compared: (a) direct judgement from reading; (b) reasoning before judging; (c) writing and executing self-generated tests; (d) writing a brute-force reference implementation and differential-testing against it; (e) majority vote across independent verifiers.
**H2.** Execution-grounded strategies (c) and (d) will substantially outperform judgement-only strategies (a) and (b), at materially higher token and time cost.

**RQ3.** Does reliability depend on the type of error present?
**H3.** Reliability will be highest for runtime and syntax failures and lowest for semantically plausible code that fails only on edge cases or exceeds time limits.

**RQ4.** How much of the achievable performance gain does a verifier of a given reliability actually capture?
**H4.** Gains will be bounded by verifier accuracy, and below some accuracy threshold verifier-based selection will perform no better than random selection.

### Experiment Design

No human participants are involved, so the study population is a corpus of generated programs rather than people. IRB review is therefore not applicable; this will be confirmed with the supervisor.

- **Corpus construction.** For each benchmark problem, generate multiple candidate solutions at varying sampling temperature. Execute every candidate against the strengthened hidden test suites to assign a ground-truth correct/incorrect label. Manually categorise a stratified sample of failures into wrong algorithm, implementation bug, unhandled edge case, and timeout.
- **Verification conditions.** Each verification strategy sees only the problem statement and the candidate code. It never sees the hidden tests. Each strategy returns a binary verdict, which is scored against the ground-truth label.
- **Selection experiment.** For each problem, generate k candidates and compare three selection policies: random selection (floor), verifier-based selection, and oracle selection using the hidden tests (ceiling). This isolates how much of the available headroom the verifier captures.
- **Ablations.** Self-verification versus cross-verification (does a model judge its own output less reliably than another model's?), and one open-weight model run locally on the CCDS TC1 cluster against one API model, subject to budget.
- **Controls.** All strategies evaluated on identical candidate pools. Multiple seeds per configuration with means and confidence intervals reported. All prompts, responses, token counts and timings logged for reproducibility.

### Measures of Success

- **Verifier reliability:** accuracy, precision, recall, false-accept rate, false-reject rate, and Matthews correlation coefficient (appropriate given class imbalance).
- **Headroom captured:** (verifier-selected pass rate − random pass rate) ÷ (oracle pass rate − random pass rate).
- **Cost:** input and output tokens, wall-clock time, and number of agent turns per verification.
- **Stratified reliability** broken down by failure category and problem difficulty.
- **Minimum viable outcome:** one benchmark, one model, three verification strategies, with a complete confusion matrix and failure analysis. Additional benchmarks, models and strategies are extensions conditional on compute and budget.

## 6. Prototype Implementation and Technical Development

- **Runtime.** OpenClaw, pinned to a single release for the duration of the evaluation, with all runtime-specific calls isolated behind a thin adapter so that a breaking upstream change does not invalidate collected results. Verification strategies are implemented as OpenClaw skills selected by configuration file rather than code change.
- **Sandboxed execution.** All model-generated code runs inside a resource-limited container with no network access, enforced timeouts and memory caps.
- **Experiment harness.** Python. Every run writes prompts, responses, verdicts, token counts and timings to a structured results store. The harness checkpoints and resumes, because the TC1 default QoS enforces a six-hour wall-clock limit per job and a full sweep will not complete in a single submission.
- **Compute.** Local open-weight model inference on the CCDS GPU cluster (TC1) via SLURM batch submission; the default allocation of one V100 32GB accommodates models in the 7B–13B range. A GPU cluster application will be submitted this month. API access for a closed-weight comparison is subject to budget approval, and the evaluation is designed to remain complete without it.
- **Optional integration.** If the core evaluation completes early, the verification protocols will be expressed as NemoIR workflow definitions and compiled to a validated intermediate representation with explicit capability policies. This is a stretch goal and is not required for the project to be complete.

## 7. Project Timeline

| Period | Phase | Milestone / Deliverable |
|---|---|---|
| Sep 2026 | Phase 0 — Setup | OpenClaw installed and version-pinned; sandboxed executor working; TC1 GPU access approved; literature survey drafted. |
| Oct 2026 | Phase 1 — Labelled corpus | Candidate solution pool generated and executed against hidden tests; ground-truth labels and failure categories assigned. |
| Nov 2026 | Phase 2 — Verifier strategies | All five verification strategies implemented as OpenClaw skills; first confusion matrices on HumanEval. |
| Dec 2026 (vacation) | Phase 3 — Full evaluation | Full sweep across strategies, benchmarks and models; stratified analysis by failure category; selection experiment (random / verifier / oracle). |
| Jan 2027 | Phase 4 — Analysis and writing | Interim Report submitted to supervisor — 25 Jan 2027. |
| Feb 2027 | Phase 5 — Extensions | Self- versus cross-verification ablation; cost analysis; any experiments arising from supervisor feedback. |
| Mar 2027 | Phase 6 — Consolidation | Experiments frozen; Final Report submitted — 22 Mar 2027. |
| Apr 2027 | Phase 7 — Revision | Amended Final Report — 16 Apr 2027; DRNTU submission. |
| May 2027 | Phase 8 — Presentation | Oral presentation and demonstration — 7 and 10–12 May 2027. |

## 8. Risks and Mitigation

- **Six-hour SLURM wall limit.** Checkpoint-and-resume built into the harness from the first sprint rather than retrofitted.
- **API budget uncertainty.** Whether LLM API credits are claimable under the CCDS FYP expense guidelines is unclear; confirmation will be sought early. The evaluation is scoped so that a local-model-only result remains a complete project.
- **Weak hidden tests producing noisy labels.** Use strengthened test suites (EvalPlus) rather than the original HumanEval tests, and treat label quality as an explicitly reported limitation.
- **Benchmark contamination.** Assemble a small held-out set of recent problems and report results on it separately from the standard benchmarks.
- **Negative result.** If no verification strategy proves reliable, that is a reportable finding: it would indicate that current multi-agent code generation protocols rest on an unsound component. The project is not structured to require a positive result.
- **Competing commitments.** Infrastructure and the labelled corpus will be completed before the December vacation so that the compute-heavy sweep runs during the period with fewest conflicts.

## 9. Working Arrangements

Proposed cadence: a written progress update to the supervisor every two weeks, and a meeting at least monthly by Zoom or in person. A shared FYP folder and a Git repository will be set up and shared with the supervisor so that progress is visible without relying on self-reporting.

## 10. Indicative References

- Chen, M. et al. (2021). Evaluating Large Language Models Trained on Code. arXiv:2107.03374.
- Austin, J. et al. (2021). Program Synthesis with Large Language Models. arXiv:2108.07732.
- Cobbe, K. et al. (2021). Training Verifiers to Solve Math Word Problems. arXiv:2110.14168.
- Chen, B. et al. (2022). CodeT: Code Generation with Generated Tests. arXiv:2207.10397.
- Chen, X. et al. (2023). Teaching Large Language Models to Self-Debug. arXiv:2304.05128.
- Madaan, A. et al. (2023). Self-Refine: Iterative Refinement with Self-Feedback. NeurIPS.
- Shinn, N. et al. (2023). Reflexion: Language Agents with Verbal Reinforcement Learning. NeurIPS.
- Lightman, H. et al. (2023). Let's Verify Step by Step. arXiv:2305.20050.
- Liu, J. et al. (2023). Is Your Code Generated by ChatGPT Really Correct? NeurIPS.
- Rozière, B. et al. (2023). Code Llama: Open Foundation Models for Code. arXiv:2308.12950.
- Huang, J. et al. (2024). Large Language Models Cannot Self-Correct Reasoning Yet. ICLR.
- Qian, C. et al. (2024). ChatDev: Communicative Agents for Software Development. ACL.
- Hong, S. et al. (2024). MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework. ICLR.
- OpenClaw documentation and source repository; NemoIR compiler toolchain documentation.
