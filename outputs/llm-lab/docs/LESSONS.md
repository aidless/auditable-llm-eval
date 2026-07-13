# 经验：可审计评测的五条纪律

> **Lessons: Five Disciplines of Auditable Evaluation**
> A standalone, bilingual (EN + 中文) note distilled from the llm-lab-copilot "false-green" incident. Companion to [`REPORT.md`](../REPORT.md) and the ADRs in [`adr/`](adr/README.md).

---

## 1. 绿灯是邀请函，不是毕业证书 / A green light is an invitation, not a diploma

**English.** Any check that only confirms "non-empty + long enough" will celebrate a loop. The v3 model emitted an opening ```` ``` ```` fence and repeated one token until the length floor — the UI called it 31/31 pass; the authoritative scorer called it 7.59%. Always separate *structural* pass from *quality* grade, and make the quality grade the thing you trust.

**中文摘要.** 只查"非空 + 够长"的检查会为死循环鼓掌。v3 输出一个 ```` ``` ```` 围栏后就无限循环同一 token，界面显示 31/31 通过，权威 scorer 只给 7.59%。必须把"结构通过"和"质量打分"分开，并只信任质量打分。

---

## 2. 永远两套打分器 / Always run two scorers

**English.** A fast *live verifier* exists for UX (does it look done?); an *authoritative scorer* exists for truth (`reference_checks`: exact/soft/unsupported_claims/missing_required_points/score). Wire the **gap** between them into your CI or your review process — not into your hopes. If the two disagree, the verifier is wrong until proven otherwise.

**中文摘要.** 快验证器管体验（看起来做完没），权威 scorer 管真相（含 exact/soft/unsupported_claims/missing_required_points/score）。把两者的**落差**写进 CI 或评审流程，而不是寄托于希望。两者不一致时，默认验证器错。

---

## 3. 低侵入 ≠ 安全 / Low-invasion ≠ safe

**English.** A minimal LoRA (rank 8 / alpha 16 / 1 epoch / LR 2e-5) "barely taught anything" — training loss moved only 3.86 → 3.41 — while leaving the failure token (the fence) unconstrained. At `temp=0` greedy decoding locked onto it and collapsed. Watch **whether the loss actually moves**, not just how modest the config looks.

**中文摘要.** 极小的 LoRA（r8/α16/1epoch/LR2e-5）"几乎没教东西"——loss 只从 3.86→3.41——却让失败 token（围栏）失控；temp=0 贪心解码锁死在它上面崩溃。要看**loss 是否真在动**，别只看配置有多"克制"。

---

## 4. 复现，别信报告 / Reproduce, don't trust the report

**English.** `verify_copilot_run.py` recomputes the score from on-disk artifacts; the number printed in any write-up is a *prediction* until re-derived. The discipline verifier is the guard rail that stops a narrative from drifting ahead of the evidence. If you can't recompute it from disk, you don't have a result.

**中文摘要.** `verify_copilot_run.py` 用磁盘产物重算分数；任何文档里印的数字在重新推导前只是"预测"。纪律校验器是防止叙事跑在证据前面的护栏。若不能从磁盘复现，你就还没有结果。

---

## 5. 认知诚实可打分 / Cognitive honesty is gradeable

**English.** "I am tamper-proof" must be a *failing* answer. Encode epistemic humility into the scorer: `must_not_claim_tamper_proof`, `must_not_overclaim`, `must_warn_structural_limit`. A model that over-claims its own guarantees is worse than one that is merely wrong — it corrupts trust in the whole pipeline.

**中文摘要.** "我防篡改"必须是*挂科*答案。把认知谦逊写进 scorer：`must_not_claim_tamper_proof`、`must_not_overclaim`、`must_warn_structural_limit`。过度声称自己能力的模型比单纯答错更糟——它会腐蚀整条管线的信任。

---

## 6. 审计前提，不止审计输出 / Audit the premises, not just the outputs

**English.** An early strategy doc assumed components that **do not exist** in the code (`CompareResult`, a 337-test suite, a `planner/` module, Langfuse telemetry). We verified against the actual repo and wrote the ADRs on *real* design. Before trusting any claim — including your own past docs — check that the thing it describes is actually there. Map ≠ territory; territory wins.

**中文摘要.** 早先一份战略文档假设了代码中**并不存在**的组件（CompareResult、337 测试套件、planner/ 模块、Langfuse 遥测）。我们对照真实仓库核实，只基于*真实*设计写 ADR。在信任任何论断（包括你自己过去的文档）之前，先确认它描述的东西真的存在。地图≠领土，领土优先。

---

*Lessons distilled 2026-07-13 from the v3 → v3c auditable-eval arc. See [`REPORT.md`](../REPORT.md) for the full incident narrative.*
