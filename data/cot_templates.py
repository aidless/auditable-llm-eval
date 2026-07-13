"""
CoT 数据模板定义 —— TMLR 领域专家微调用
类型：
  A. 论文理解   B. 公式推导   C. 实验设计   D. 代码实现   E. 通用防遗忘
每个模板是一个函数，接收素材 dict，返回 {"user": str, "assistant": str}
训练数据统一为 ShareGPT 风格 conversations 字段（见 build_dataset.py）。
"""

# ---------- A. 论文理解 ----------
def t_paper_understanding(item: dict) -> dict:
    title = item["title"]
    abstract = item["abstract"]
    method = item.get("method", "")
    contribution = item.get("contribution", "")
    return {
        "user": (
            f"请阅读以下 TMLR 论文信息，提炼其核心方法与创新点。\n\n"
            f"标题：{title}\n摘要：{abstract}"
        ),
        "assistant": (
            f"我来逐步分析这篇论文。\n\n"
            f"**1. 研究问题**：从摘要看，作者试图解决 {abstract[:60]}… 这一核心问题。\n\n"
            f"**2. 核心方法**：{method if method else '论文提出的方法主要围绕摘要中描述的思路展开，关键在于…'}\n\n"
            f"**3. 主要创新**：{contribution if contribution else '相较已有工作，本文的贡献在于…'}\n\n"
            f"**4. 总结**：该方法在…场景下具有…优势，潜在局限是…"
        ),
    }


# ---------- B. 公式推导 ----------
def t_formula_derivation(item: dict) -> dict:
    problem = item["problem"]
    steps = item["steps"]  # list[str]
    conclusion = item["conclusion"]
    step_text = "\n".join(f"**步骤 {i+1}**：{s}" for i, s in enumerate(steps))
    return {
        "user": f"请推导并解释：{problem}",
        "assistant": (
            f"我们一步步推导。\n\n{step_text}\n\n"
            f"**结论**：{conclusion}"
        ),
    }


# ---------- C. 实验设计 ----------
def t_experiment_design(item: dict) -> dict:
    question = item["question"]
    hypothesis = item.get("hypothesis", "")
    design = item["design"]  # list[str]
    design_text = "\n".join(f"- {d}" for d in design)
    return {
        "user": f"研究问题：{question}\n请设计实验方案（含假设、变量、评估指标）。",
        "assistant": (
            f"**研究假设**：{hypothesis if hypothesis else '需要先明确可检验的假设，例如…'}\n\n"
            f"**实验设计**：\n{design_text}\n\n"
            f"**评估与统计**：选择合适指标（如准确率/对数似然/效应量），并用…检验进行显著性判断，"
            f"同时报告置信区间与多次随机种子的方差，避免单点结论。"
        ),
    }


# ---------- D. 代码实现 ----------
def t_code_implementation(item: dict) -> dict:
    task = item["task"]
    code = item["code"]
    explanation = item.get("explanation", "")
    return {
        "user": f"请用 PyTorch 实现：{task}",
        "assistant": (
            f"```python\n{code}\n```\n\n"
            f"{explanation if explanation else '上述实现包含前向计算与必要的数值稳定性处理（如对 logits 做 clamp 防止 log(0)）。'}"
        ),
    }


# ---------- E. 通用防遗忘 ----------
def t_general(item: dict) -> dict:
    return {"user": item["user"], "assistant": item["assistant"]}


TEMPLATES = {
    "A": t_paper_understanding,
    "B": t_formula_derivation,
    "C": t_experiment_design,
    "D": t_code_implementation,
    "E": t_general,
}

if __name__ == "__main__":
    # 自测
    demo = t_formula_derivation({
        "problem": "推导高斯分布下均值的最大似然估计。",
        "steps": ["写出对数似然 L(μ)=Σ log N(x_i;μ,σ²)",
                  "对 μ 求偏导并令为 0",
                  "解得 μ_MLE = x̄"],
        "conclusion": "样本均值是无偏估计。",
    })
    print(demo["assistant"])
