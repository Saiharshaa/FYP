# Literature review: outline and reading map

Working outline for the interim report's literature review (due 25 Jan 2027).
It sets out the structure, which source supports which claim, and which
reading is still needed. **No prose here:** the text is to be written by the
student. Sources marked *(to add)* are not yet in the plan's reference list.
Check each one (authors, venue, year) before citing it.

## Proposed structure (about 2,500–3,500 words)

1. **Why verification matters in agentic code generation** (about 400 words)
   - Multi-agent pipelines assign reviewer/tester roles: ChatDev (Qian et
     al., 2024) and MetaGPT (Hong et al., 2024).
   - Claim to support: these systems report end-to-end gains but not the
     critic's own error rates (Gap 1 in the plan).
   - Reading task: for ChatDev and MetaGPT, note exactly what they measure
     and whether any reviewer accuracy is reported.

2. **Self-correction and its limits** (about 600 words). Relevant to RQ1
   and H1.
   - Self-Refine (Madaan et al., 2023) and Reflexion (Shinn et al., 2023):
     iterating on the model's own feedback.
   - Huang et al. (2024): without external feedback, self-correction does
     not reliably help, and apparent gains can come from oracle leakage.
   - Link to the pilot: self-verification at 1.5B accepts 87–100% of
     incorrect code, and the answer-order control rules out a
     format-following artefact.
   - *(to add)* LLM-as-a-judge reliability: Zheng et al. (2023), "Judging
     LLM-as-a-Judge with MT-Bench and Chatbot Arena".
   - *(to add)* Self-preference bias in LLM evaluators: Panickssery et al.
     (2024), "LLM Evaluators Recognize and Favor Their Own Generations".
     This motivates the self- versus cross-verification ablation.

3. **Execution-grounded verification** (about 600 words). Relevant to RQ2
   and H2.
   - CodeT (Chen et al., 2022): generated tests plus dual agreement ranking.
     It is the direct precedent for strategy (c) and for writing tests from
     the specification only.
   - Self-Debugging (Chen et al., 2023): execution feedback in the loop.
   - Strategy (d), differential testing against a brute-force reference,
     sits here. Reading task: find prior work on LLM-written oracles or
     reference implementations (e.g. search "differential testing LLM
     oracle").
   - Point to make: execution replaces opinion with evidence, but the
     evidence is itself model-written. Wrong expected values cause false
     rejects (measured via FRR).

4. **Trained verifiers and process supervision** (about 400 words)
   - Cobbe et al. (2021): a separately trained verifier beats fine-tuning
     alone.
   - Lightman et al. (2023): process supervision beats outcome supervision.
   - Use: verification is a distinct capability from generation. This
     project measures off-the-shelf models as verifiers rather than
     training one; state that scope explicitly.

5. **Benchmarks and ground truth** (about 500 words)
   - HumanEval (Chen et al., 2021) and MBPP (Austin et al., 2021).
   - EvalPlus (Liu et al., 2023): the original tests are weak, and
     HumanEval+ catches incorrect code that the originals pass. This
     justifies using HumanEval+ labels.
   - Reproducibility notes from this project: evalplus pinned, HumanEval/32
     excluded, and timeout categories that depend on host load. Mention
     briefly as limitations.

6. **Measuring a verifier** (about 300 words). Relevant to RQ3 and RQ4.
   - Treat verification as binary classification: FAR, FRR, MCC under class
     imbalance. *(to add)* Chicco & Jurman (2020), on MCC versus accuracy
     and F1.
   - Selection/headroom framing for RQ4. Reading task: find work comparing
     verifier-based reranking against oracle (pass@k) ceilings.

7. **Gaps this project addresses** (about 300 words): restate the plan's
   four gaps, each tied to an RQ and to the evidence above.

## Models and tooling to cite in Methods (not the review)

- Qwen2.5-Coder: *(to add)* Hui et al. (2024), *Qwen2.5-Coder Technical
  Report*.
- Llama 3.1: *(to add)* the Llama 3 model report, "The Llama 3 Herd of
  Models" (2024).
- vLLM: *(to add)* Kwon et al. (2023), "Efficient Memory Management for
  Large Language Model Serving with PagedAttention", SOSP.
- Code Llama (Rozière et al., 2023) is in the plan list. Keep it only if a
  Code Llama model is used; otherwise drop it.
- OpenClaw / NemoIR: decide with the supervisor whether the integration is
  still in scope (the plan's stretch goal).

## Evidence from this project to cite in the review's framing

The numbers are in `notebook/LAB_NOTEBOOK.md` and
`reports/pilot-q15b/report.md`:
- direct: 400/400 CORRECT; the answer-order control still accepts 127/127
  incorrect.
- reason: MCC −0.06 (v1) / −0.10 (v2); the majority vote's v1 gain is a
  parsing artefact.
- RQ4: no judgement-only strategy captures any selection headroom (all
  95% CIs include 0).
- (c)/(d): pilot pending.
