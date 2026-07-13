"""
TMLR 领域训练数据采集器
- 从 arXiv 抓取 cs.LG / cs.CL / cs.AI / stat.ML 论文
- 用 CoT 模板生成 A/B/C/D 类训练样本
- 可选混入通用指令数据（E 类）防止灾难性遗忘
- 输出 ShareGPT 风格 JSONL：{"conversations": [{"role","content"}, ...]}

依赖：
    pip install arxiv  # 用于抓取；若不想联网，可用 --from-file 读本地 jsonl

用法：
    python build_dataset.py --max-papers 200 --general-ratio 0.2 --out tmlr_cot_data.jsonl
    python build_dataset.py --from-file papers.jsonl --out tmlr_cot_data.jsonl
"""

import argparse
import json
import random
from pathlib import Path

import cot_templates as ct

CATEGORIES = ["cs.LG", "cs.CL", "cs.AI", "stat.ML"]
FIELDS = ["title", "summary"]


def fetch_arxiv(max_papers: int):
    """抓取 arXiv 论文（需 arxiv 库）。返回 list[dict]。"""
    try:
        import arxiv
    except ImportError:
        raise SystemExit("未安装 arxiv 库，请先 `pip install arxiv`，或用 --from-file 读取本地数据。")
    client = arxiv.Client(page_size=100, delay_seconds=3, num_retries=3)
    search = arxiv.Search(query=" OR ".join(f"cat:{c}" for c in CATEGORIES),
                          max_results=max_papers, sort_by=arxiv.SortCriterion.Relevance)
    papers = []
    for r in client.results(search):
        papers.append({"title": r.title, "abstract": r.summary,
                       "method": "", "contribution": ""})
    return papers


def load_local(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_samples(papers: list, seed: int = 42):
    """对每篇论文生成多类 CoT 样本。"""
    random.seed(seed)
    samples = []
    for p in papers:
        # 容错：--from-file 本地数据可能用 "summary" 键，统一映射到 "abstract"
        p.setdefault("abstract", p.get("summary", ""))
        # A. 论文理解（必出）
        a = ct.TEMPLATES["A"](p)
        samples.append({"conversations": [
            {"role": "user", "content": a["user"]},
            {"role": "assistant", "content": a["assistant"]},
        ]})
        # B. 公式推导（从摘要里抽一个概念做推导提示）
        concept = random.choice(["损失函数", "似然", "梯度", "正则项", "注意力权重"])
        b = ct.TEMPLATES["B"]({
            "problem": f"结合论文《{p['title'][:40]}》的思路，推导 {concept} 关于模型参数的梯度。",
            "steps": ["写出目标函数 J(θ)",
                      f"对 θ 求偏导 ∂J/∂θ",
                      "代入本文设定化简"],
            "conclusion": f"梯度形式表明 {concept} 如何影响更新方向。",
        })
        samples.append({"conversations": [
            {"role": "user", "content": b["user"]},
            {"role": "assistant", "content": b["assistant"]},
        ]})
        # C. 实验设计
        c = ct.TEMPLATES["C"]({
            "question": f"如何验证论文《{p['title'][:40]}》提出方法的有效性？",
            "design": ["确定基线方法与数据集", "控制超参与随机种子",
                       "采用 k 折或多次随机划分", "报告均值±方差与显著性检验"],
        })
        samples.append({"conversations": [
            {"role": "user", "content": c["user"]},
            {"role": "assistant", "content": c["assistant"]},
        ]})
    return samples


def add_general(samples: list, ratio: float, seed: int = 42):
    """混入通用指令数据（E 类），占总条数 ratio。"""
    if ratio <= 0:
        return samples
    random.seed(seed)
    n_gen = int(len(samples) * ratio / (1 - ratio))
    general_pool = [
        ("用一句话解释什么是过拟合。", "过拟合指模型在训练集上误差很小，但在未见数据上泛化误差大，通常因容量过大或训练过久。"),
        ("把这段中文翻译成英文：模型在测试集上表现稳定。", "The model performs stably on the test set."),
        ("列举三种常见的正则表达式用途。", "1) 邮箱/手机号校验；2) 日志提取；3) 代码静态分析中的模式匹配。"),
        ("写一段 Python 读取 CSV 的前五行。", "import pandas as pd\ndf = pd.read_csv('data.csv')\nprint(df.head())"),
        ("什么是 REST API？", "REST 是一种基于 HTTP 资源的接口风格，用标准方法（GET/POST 等）操作资源，无状态且可缓存。"),
    ]
    for _ in range(n_gen):
        u, a = random.choice(general_pool)
        samples.append({"conversations": [
            {"role": "user", "content": u},
            {"role": "assistant", "content": a},
        ]})
    random.shuffle(samples)
    return samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-papers", type=int, default=200)
    ap.add_argument("--from-file", type=str, default="")
    ap.add_argument("--general-ratio", type=float, default=0.2)
    ap.add_argument("--out", type=str, default="tmlr_cot_data.jsonl")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    papers = load_local(args.from_file) if args.from_file else fetch_arxiv(args.max_papers)
    print(f"[info] 论文数: {len(papers)}")

    samples = build_samples(papers, seed=args.seed)
    samples = add_general(samples, args.general_ratio, seed=args.seed)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"[done] 生成 {len(samples)} 条训练样本 -> {out}")


if __name__ == "__main__":
    main()
