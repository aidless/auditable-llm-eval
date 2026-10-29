# 016 — 文档漂移修复 + 评测腿打包（pyproject）
**Date**: 2026-10-28
**Trigger**: 一次跨两仓的只读审计（`aidless/auditable-llm-eval` + `aidless/mcp-guard`）。
审计在 GitHub 上看不到 README / pyproject / tests 的搜索结果，提示"先确认项目结构、依赖、
运行入口和测试方式"。克隆后逐文件核对，发现本仓存在 **5 处文档/结构漂移**：
其中 3 处在本仓、2 处在 `mcp-guard`（那份改在 mcp-guard 仓内完成，证据见
`~/work/agent-reliability/`）。
**Scope**: 本文件只记录 auditable-llm-eval 侧的改动。
**HEAD at authoring**: `11d8f3890441c785a5ceb60c0da8286d028760c2`

---

## 🩺 Problem（逐条，带证据）

| # | 漂移 | 证据 |
|---|---|---|
| 1 | 仓库**不可 `pip install`**：没有 `pyproject.toml` / `setup.py` / `requirements.txt`，只有面向 Windows+3060 训练的 `requirements_win3060.txt` | `ls` 结果；GitHub 代码搜索"找不到 pyproject"不是搜索故障，是真的没有 |
| 2 | 测试计数漂移：根 README 徽章写 40，`tests/README.md` 写 "Ran 39 tests" 且称 `test_scorer.py` 是"唯一文件"，两个 workflow 注释也写 39 | 实际 `Ran 40 tests`（39 在 `test_scorer.py` + 1 在 `test_demo.py`） |
| 3 | TL;DR 写 "a 30-point deception zone"，`demo.py` 实际打印 **32 points** | `python3 demo.py` → `deception gap : naive 100% green vs authoritative 68% — 32 points`；两个权威分是 0.67 / 0.69，均值 0.68 |

历史文档 `analysis/012-final-state-report.md` 等也写着 39——那是**当时的快照**，按
"留痕可审计"纪律**不改写**；本文件记录当前态（40）。

---

## 🔍 Diagnosis

- #1 不是 bug，是当年的**明确取舍**（§2.1 原话："本仓库是制品集合…不是可 pip install 的库"）。
  但留下的后果是：外部读者用 `pip install` / `import` 的标准动作全部失败，而且**没有任何
  文件解释为什么**。取舍本身没错，**缺的是诚实的说明 + 一个能满足该动作的最小配置**。
- #2 是 `test_demo.py`（2026-10-25 随 60 秒 demo 加入）没有同步到两处文档 + 两处 workflow 注释。
- #3 是 30 / 32 的口径问题：作者写的是"两个权威分的落差"（69 − 67 ≈ 2？不，是 100% vs 均值），
  实际 demo 打印的是 100% 与均值之差。**数字都能复算，措辞需要对齐到实际输出。**

---

## 🔧 Fix

1. **新增 `pyproject.toml`**（零运行时依赖）+ `copilot/__init__.py`：
   - `packages = ["copilot"]`，`py-modules = ["verify_copilot_run"]`
   - 两个 console script：`auditable-eval-score`、`auditable-eval-verify`
   - **不引入任何第三方依赖**——评分器与校验器仍然只用标准库，本仓核心命题不变。
   - `.gitignore` 补 `*.egg-info/`、`build/`、`dist/`。
   - 根 README §2.1 改写：说明"评测腿现在**可以**装成包"，但**本仓定位仍是制品集合**，
     装包只是为了给"能不能 pip install"一个诚实答案。
2. **测试计数对齐到 40**：`tests/README.md`（含 `test_demo.py` 独立小节与总数）、
   `release.yml` 注释、`mutation-control.yml` 两处注释。
3. **TL;DR 口径对齐**：改为 "a **32-point** deception zone (100% naive green vs. the 68% mean
   of the two authoritative scores)"，与 `demo.py` 的实际输出逐字一致。

---

## ✅ Verification（本机实测，2026-10-28，Python 3.12.3）

```bash
python3 -m unittest discover -s tests          # Ran 40 tests ... OK
python3 -m pytest tests -q                     # 40 passed
python3 scripts/validate_release.py            # selftest/spec/verifier/gitignore 全 PASS, OVERALL: PASS
python3 demo.py                                # 0.67 / 0.69, match=True, "32 points"
python3 -m venv /tmp/ale-venv && /tmp/ale-venv/bin/pip install -e .
/tmp/ale-venv/bin/auditable-eval-score --selftest   # SELFTEST: PASS
/tmp/ale-venv/bin/python -c "from copilot.score_copilot_run_v2 import run"   # import OK
```

`validate_release.py` 的第 4 项检查输出从 "113 tracked files" 变为实际计数——该检查
**没有硬编码 113**，所以新增文件不会让它变红（这一点在加 `pyproject.toml` 之前先查过源码）。

---

## 📌 Lesson

> **取舍要写下来，漂移要有人负责。**

"本仓不是可安装库"是一个合理取舍，但只写在正文的一句话里，等于让所有后来者
重新踩一遍"为什么 pip install 失败"。真正的修复不是反转取舍，而是
**把取舍显式化**（README 说明 + 一个满足标准动作的最小配置），
这样"不能 pip install"从 bug 变成了**有文档的边界**。

同类的还有计数漂移：一个新测试文件（`test_demo.py`）加进来时，
所有提到"39"的地方都成了陈述性错误——**数字型陈述比代码更容易腐烂**，
因为没有任何测试会检查 README 里的数字。

---

## 🔗 Links

- 规格：[`specs/scoring-rules.json`](../specs/scoring-rules.json)、
  [`specs/eval.endpoints.json`](../specs/eval.endpoints.json)
- 打包配置：[`pyproject.toml`](../pyproject.toml)
- 姊妹仓同批改动与跨仓证据：`~/work/agent-reliability/`（本机路径，不在本仓内）
- 上一条：[`015-fix-insufficient.md`](./015-fix-insufficient.md)
- 索引：`analysis/README.md`

