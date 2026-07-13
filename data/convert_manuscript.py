"""
将研究者自有稿件（.tex / .md）转化为 CoT 训练样本
- 按章节切分（LaTeX \\section 或 Markdown ##）
- 提取"方法/实验/公式"相关段落
- LaTeX 公式抽取增强：抽取独立公式 -> 公式理解样本
- 套用 CoT 模板生成 A/C/B/F 类样本
- 导出 build_samples_from_text / extract_formulas 供 build_dataset_fulltext 复用
- 输出 manuscript_cot_data.jsonl（ShareGPT 风格）

用法：
    python convert_manuscript.py --in ../my_paper.tex --out manuscript_cot_data.jsonl
    python convert_manuscript.py --in notes.md --out manuscript_cot_data.jsonl

注意：这是轻量启发式提取，生成后请人工抽查 10% 校正，避免把错误推理写进训练集。
"""

import argparse
import json
import re
from pathlib import Path

import cot_templates as ct

SECTION_RE = re.compile(r"^\\section\{(.*?)\}|^#{1,3}\s+(.*)$", re.M)
MATH_RE = re.compile(r"(\$.*?\$|\\\(.*?\\\)|\\\[.*?\\\])", re.S)

# 公式抽取规格：(正则, 公式内容所在 group)
_FORMULA_SPECS = [
    (r"\\begin\{(equation|equation\*|align|align\*|gather|gather\*|eqnarray)\}(.+?)\\end\{\1\}", 2),
    (r"\$\$(.+?)\$\$", 1),
    (r"\\\[(.+?)\\\]", 1),
    (r"(?<![\$\\])\$(.+?)\$(?![\$])", 1),
]


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def split_sections(text: str):
    """返回 [(title, body), ...]"""
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return [("(full)", text)]
    secs = []
    for i, m in enumerate(matches):
        title = m.group(1) or m.group(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        secs.append((title.strip(), text[start:end].strip()))
    return secs


def looks_method(title: str) -> bool:
    return any(k in title.lower() for k in ["method", "approach", "model", "架构", "方法", "模型"])


def looks_exp(title: str) -> bool:
    return any(k in title.lower() for k in ["experiment", "eval", "result", "实验", "评估", "结果"])


def extract_formulas(text: str):
    """抽取 LaTeX 文本中的独立公式（去注释、清洗、去重、过滤长度）。"""
    text = re.sub(r"(?m)%.*$", "", text)  # 去行注释
    out = []
    for pat, grp in _FORMULA_SPECS:
        for m in re.finditer(pat, text, re.S):
            f = m.group(grp).strip().strip("$")  # 剥掉偶发的边界 $（如源码中 $$$...$$$）
            f = re.sub(r"\s+", " ", f)
            if 8 <= len(f) <= 400:
                out.append(f)
    seen, uniq = set(), []
    for f in out:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def make_formula_sample(latex: str) -> dict:
    """公式理解样本（F 类）：解释每项含义与 ML 作用。"""
    return {
        "user": (
            f"请解释以下 LaTeX 公式每一项的含义，并说明它在机器学习中的作用：\n\n"
            f"$${latex}$$"
        ),
        "assistant": (
            f"我们逐项解析公式 `${latex}`：\n\n"
            f"**1. 整体含义**：该式描述了…（根据具体符号给出解释，如期望、损失、似然等）。\n\n"
            f"**2. 关键项**：识别其中的变量、参数与算子，说明其物理/统计意义与假设。\n\n"
            f"**3. 在 ML 中的作用**：该公式通常用于…（如损失计算、概率建模、正则化、注意力得分等），"
            f"理解它有助于正确实现前向过程并合理调参。"
        ),
    }


def build_samples_from_text(title: str, text: str, max_chars: int = 1500, max_formulas: int = 5):
    """通用：从一段(论文/稿件)文本生成多类 CoT 样本。供稿件与 arXiv 正文级共用。"""
    # 轻量去噪（保留正文与公式）
    text = re.sub(r"\\(usepackage|documentclass|begin|end|label|ref|cite)\b.*", "", text)
    secs = split_sections(text)
    samples = []

    for t, body in secs:
        body = body[:max_chars]
        if not body.strip():
            continue
        if looks_method(t):
            a = ct.TEMPLATES["A"]({
                "title": title or t, "abstract": body[:200],
                "method": body, "contribution": "",
            })
            samples.append({"conversations": [
                {"role": "user", "content": a["user"]},
                {"role": "assistant", "content": a["assistant"]},
            ]})
        elif looks_exp(t):
            c = ct.TEMPLATES["C"]({
                "question": f"如何复现/验证本节《{t}》描述的实验？",
                "design": ["对齐数据集与预处理", "固定随机种子与超参",
                           "多次运行取均值±方差", "与正文报告结果交叉核对"],
            })
            samples.append({"conversations": [
                {"role": "user", "content": c["user"]},
                {"role": "assistant", "content": c["assistant"]},
            ]})
        # 含公式的段落 -> 推导样本
        if MATH_RE.search(body):
            b = ct.TEMPLATES["B"]({
                "problem": f"解释本节《{t}》中的关键公式推导。",
                "steps": ["定位核心等式", "说明每项含义与假设",
                          "给出简化或变形"],
                "conclusion": "该推导支撑了方法的正确性。",
            })
            samples.append({"conversations": [
                {"role": "user", "content": b["user"]},
                {"role": "assistant", "content": b["assistant"]},
            ]})

    # 公式级样本（更细粒度，每篇限 max_formulas 条避免公式爆炸）
    for latex in extract_formulas(text)[:max_formulas]:
        f = make_formula_sample(latex)
        samples.append({"conversations": [
            {"role": "user", "content": f["user"]},
            {"role": "assistant", "content": f["assistant"]},
        ]})
    return samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", default="manuscript_cot_data.jsonl")
    ap.add_argument("--max-chars", type=int, default=1500,
                    help="单段最长字符，过长截断避免超出 seq_len")
    ap.add_argument("--max-formulas", type=int, default=5,
                    help="每篇最多抽取公式样本数")
    args = ap.parse_args()

    text = read_text(args.inp)
    samples = build_samples_from_text("(manuscript)", text,
                                      max_chars=args.max_chars,
                                      max_formulas=args.max_formulas)
    out = Path(args.out)
    with out.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"[done] 从 {args.inp} 生成 {len(samples)} 条稿件样本 -> {out}")


if __name__ == "__main__":
    main()
