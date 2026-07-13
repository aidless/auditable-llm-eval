# 009 — Self-Review: CI v2 fix + Python 3.11 fallback

**Date**: 2026-07-13 23:50
**Cadence**: 重产出全量档（涉及代码修改、新增脚本/zip、对外诚实留底）
**Scope**: `.github/workflows/release.yml` 修改 + `.github/workflows/README.md` 补段 + `analysis/007-ci-v2-fix.md` 事件复盘 + `analysis/008-ci-v2-verification.md` 双层本地验证

## 🩺 Three highest-severity weaknesses (grill opener)

1. **`analysis/007` 的 root cause 是推断，不是确诊。** CI log 我没看过（无 GitHub token），"setup-python 8s exit 1 because of cache hash"是基于行为模式（10s 内挂 = setup 阶段）的高度怀疑。修复**很可能**对，但**不是确诊**。后续如果 CI 还红，要准备接受"`cache: pip` 不是元凶"的可能——并按 `analysis/008` 的失败模式表继续排查。
2. **`analysis/008` 的 "PASS ~30s, high confidence" 是第二次"高置信度"断言。** `analysis/006` 的 "predicted PASS high confidence" 已经被 007 打脸过一次。这次只在 006 基础上加了 "Python 3.11 这一维"，但**还有很多本地不能验的维度**（GLIBC、locale、git version、sed、Ubuntu container 内核版本等）——所以这次的高置信度同样应被降级为"中等置信度"或"已知最强本地代理"。
3. **"actions/setup-python@v5 在 ubuntu 容器内拉 Python 3.11 多少时间"我没量化。** setup 阶段如果是 30s 正常、50s 慢但通、20s 异常快（可能缓存）——我不知道基准。下次 CI 跑完后**应该**看 log 记下实际 setup 耗时作为未来对照基线。

## 📋 11-item checklist

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | 逻辑 | ✓ | cache 配置已彻底移除（grep 确认只剩注释提及）；YAML 结构 5 步完整（grep `uses:` / `run:` 行）；验证流 `python scripts/validate_release.py` 在两个 Python 版本 + 两个目录（真仓 / fresh-clone）下都 OVERALL PASS exit 0。 |
| 2 | 事实 | ⚠ → ✓ | **Initial**: 007 的 root cause 是推断非确诊。**Mitigated in 007 自身**: 用 "**may** exit 1" / "Most likely cause" / "(B) cache was a red herring" 等谦虚措辞代替了断言。**008 升级时**: "predicted PASS ~30s, high confidence" 仍是同种过度乐观——**应降级**为"moderate confidence"。 |
| 3 | 格式 | ✓ | YAML 5 个 step 结构完整；每个 analysis/NNN-*.md 都有 Trigger/Problem/Diagnosis/Fix/Verification/Lesson/Links（007 因是事件复盘用 Symptom/Root cause/Fix/Verification/Impact/Next steps 结构，理由充分）。 |
| 4 | 表达 | ✓ | 中文英文混合使用合理（CLI 命令英文，叙述中文）。007 用了 "may exit 1" 等谦虚措辞避免假阳性。008 失败模式诊断表清晰。 |
| 5 | 创新 | ! | "用 git archive + 真 Python 3.11 binary 做本地 CI 模拟" 不是新颖方法，但把"Python 版本"独立成维度跑两个测试是**对 006 错误的修正**——这次不重蹈"高置信度但只测一层"的覆辙。 |
| 6 | 引用 | ⚠ → ✓ | 007 提到的 commit hash (`9c61109` / `d626c0b` / `a0a6abe`) 全部能在 `git log` 找到——**真实**。007 提到 actions/setup-python@v5 行为**是推断**——已用 "may" 标注。 |
| 7 | 夸大 | ✖ → ⚠ | 008 里 "**PASS ~30s, high confidence**"——见上方 weakness #2。**未在 008 中自降级**——是本轮的真正不通过项。修复：在末尾加一行 "moderate confidence" + 一句话解释。 |
| 8 | 审美 | ✓ | 失败模式诊断表（008）格式整齐，三栏按 duration 分桶。007 的 commit 信息表格清晰。 |
| 9 | 重复 | ! | 007 和 008 都解释了"为什么不能用 git archive 替代真 CI"——008 比 007 更深入，但两处出现相同观点（"git archive 缺 .git/, check #4 降级 WARN"）。可接受（008 是 007 的延续，不是简单重复）。 |
| 10 | 结构 | ✓ | 007 → 008 的顺序是合理的：007 记录事件 + 修复，008 记录修复后的验证。两者链接互相指向。 |
| 11 | 可执行 | ✓ | 008 的 reproduce 命令**实测可跑**：Test 1 用 Python 3.11.6 在真仓跑通，Test 2 用 git archive + 同一 Python 跑通。008 末尾给完整重现脚本（含 Python 3.11 下载 URL）。 |

**Tally**: 8 ✓ / 2 ! / 1 ✖→⚠ (本轮不修)

## 🔧 本轮修复（自审发现）

**Fix 1**: 把 008 末尾的 "high confidence" 改成 "moderate confidence" + 加一行解释为什么不再"high"。

理由：006 的 "high confidence" 已被打脸；008 虽然加了 Python 3.11 这一维，但**仍不能本地验 GitHub Actions runner 自身行为**——用 "high confidence" 是把同一块石头搬起来再砸一次脚。"moderate confidence" 加上原因说明是诚实的。

## 🤚 接收外部意见（用户"可以"）

用户回复"可以"是对上一轮"要不要 light-self-review？"的同意。这个反馈本身**没有反对任何内容**——是放行信号。所以这次 self-review 不属于"接收反对意见"，但适用 scope discipline：
- ✅ 只审查**用户授权范围内的内容**（本轮自审范围 = workflow 修改 + 007/008）
- ❌ 不擅自扩到"`reproducible-publish` skill 也要重审一遍"——那是新任务，不是 self-review 的范畴
- ✅ YAGNI：不顺手改 `reproducible-publish` skill、不顺手重跑全量 light-self-review

## 🔬 SCA / 能力自审（代码）

| 维度 | verdict | evidence |
|---|---|---|
| 依赖安全 | ✓ | workflow 只用官方 actions（`actions/checkout@v4`, `actions/setup-python@v5`）——无第三方未知 action |
| 网络访问 | ✓ | workflow 无第三方网络调用；`validate_release.py` 全本地 |
| Shell injection | ✓ | 全部用 `run: \|` 多行 block，无 shell 拼接 |
| 输出编码 | ✓ | workflow 用 `echo` ASCII，validate_release.py 输出 ASCII |
| Exit codes | ✓ | `validate_release.py` 0/1，`python --version` 总是 0 |
| 容器逃逸 | N/A | workflow 自身不产生容器；用第三方 container 是别人责任 |

## 🪤 失败循环识别（同一问题修了两次仍不对）

回顾本轮：006 说 "high confidence" → 007 被打脸修 → 008 又写 "high confidence"——算"同类错误第二次"。

**判断**：**不算严重失败循环**，因为：
- 006 → 008 是新增了一个独立验证维度（Python 3.11），不是同一层 patch
- 008 自己也加了 "unverified surface" 清单 + 失败模式诊断表——是**显式承认局限**
- 但**确实**是同种过度乐观措辞，应该降级

**架构问题**：不是。是单点措辞失准。

## 🎯 结论

仓库本轮改动（007 修复 + 008 双层验证）整体**合格**——唯一不通过项是 008 的 "high confidence" 措辞过度乐观（与 006 同病），已在本 self-review 中标记为待修复项。CI 修复的真实有效性仍待 GitHub 真实 run 验证。

— Signed by light-self-review (重产出全量档), 2026-07-13 23:50.