"""
将研究者自有"审稿语料"转化为"审稿偏好"CoT 训练样本（M2 路径 B：第二轮 LoRA）

目标：让模型学习用户的**审稿视角与评判偏好**，补足现有管道只有"作者侧"领域理解的缺口。
      现有 convert_manuscript.py 产出的是"作者理解"样本（提炼方法/复现实验/解释公式）；
      本脚本产出的是"审稿人侧"样本（给定论文片段→用户的审稿意见；或陈述用户的审稿准则）。

输入格式（JSONL，每行一个评审单元，二选一或混合）：
  1) 针对片段的审稿意见：
     {"excerpt": "论文方法/实验片段原文", "review": "用户对该片段的真实审稿意见"}
  2) 审稿准则/偏好（强化"用户看重什么"）：
     {"principles": "用户在评审中最看重的方面，如：方法严谨性、消融充分性、可复现性、显著性检验…"}
  * 可加 "_note" 字段做备注，脚本忽略之。

输出格式（ShareGPT，与 train_lora.py 兼容）：
  {"conversations":[{"role":"user","content":...},{"role":"assistant","content":...}]}

用法：
  # 用你的真实语料（把模板替换为 #47-51 审稿反馈/PC 笔记/复盘）后：
  python convert_reviews.py --in review_corpus.jsonl --out review_cot_data.jsonl
  # 生成一份输入格式模板（含示例，非真实语料）：
  python convert_reviews.py --make-template review_corpus_TEMPLATE.jsonl

注意：
  - 输出质量完全取决于你的真实语料；脚本只做格式转换与轻量清洗，**不臆造审稿观点**。
  - 生成的 review_cot_data.jsonl 可直接并入 data/training_all.jsonl 做第二轮 LoRA（见 run_all.py --reviews）。
"""

import argparse
import json
from pathlib import Path


def _clean(text: str, max_chars: int = 1200) -> str:
    """轻量清洗：去首尾空白、合并多余空行、截断以控 seq_len。"""
    text = text.strip()
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return text[:max_chars]


def make_template(path: str):
    """写一份示例模板（明确标记为示例，非真实语料）。"""
    rows = [
        {
            "_note": "示例模板-请替换为你的真实审稿语料（非真实内容）",
            "excerpt": "我们提出方法 X，在三个数据集上取得了 SOTA 结果，优于此前最佳方法约 2%。",
            "review": "主要问题：(1) 缺乏与强基线的公平对比，未说明基线是否用了相同超参与数据划分；"
                      "(2) 仅报告点估计，未给出多次运行的均值±方差与显著性检验，结论可信度不足；"
                      "(3) 建议补充消融实验，说明各模块的贡献。这些是方法类论文最易被质疑的点。",
        },
        {
            "_note": "示例模板-请替换为你的真实审稿准则（非真实内容）",
            "principles": "我在评审 ML 论文时最看重：① 方法动机与问题定义是否清晰；"
                          "② 实验是否包含充分消融与强基线、是否报告方差与显著性；"
                          "③ 结论是否被证据充分支持、有无过度宣称；"
                          "④ 可复现性（代码/数据/随机种子）。创新性固然重要，但严谨性优先于增量 SOTA。",
        },
        {
            "_note": "示例模板-请替换为你的真实审稿语料（非真实内容）",
            "excerpt": "本文使用合成数据增强训练集，声称可提升小样本下的泛化。",
            "review": "合成增强的合理性存疑：未验证增强样本是否引入分布偏移或标签噪声；"
                      "建议给出增强前后样本的可视化对比，并说明增强策略为何保留语义。",
        },
    ]
    out = Path(path)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[template] 已写入示例模板 -> {out}（请替换为你的真实审稿语料后使用）")


def build_samples(entry: dict, max_chars: int):
    """从一条语料生成 0~1 个训练样本。"""
    samples = []
    excerpt = _clean(entry.get("excerpt", ""), max_chars)
    review = _clean(entry.get("review", ""), max_chars)
    principles = _clean(entry.get("principles", ""), max_chars)

    if excerpt and review:
        samples.append({"conversations": [
            {"role": "user", "content":
                "作为审稿人，请评审以下论文片段，指出核心问题、证据缺口与改进建议：\n\n" + excerpt},
            {"role": "assistant", "content": review},
        ]})
    elif principles:
        samples.append({"conversations": [
            {"role": "user", "content":
                "作为审稿人，你在评审一篇机器学习论文时最看重哪些方面？请陈述你的核心审稿准则。"},
            {"role": "assistant", "content": principles},
        ]})
    else:
        # 既无 excerpt+review 也无 principles：无法构造有意义样本
        print(f"[warn] 跳过一条无效语料（需 excerpt+review 或 principles）：{str(entry)[:60]}")
    return samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="",
                    help="审稿语料 JSONL（每行 {excerpt,review} 或 {principles}）")
    ap.add_argument("--out", default="review_cot_data.jsonl")
    ap.add_argument("--make-template", default="",
                    help="生成输入格式模板到指定路径并退出")
    ap.add_argument("--max-chars", type=int, default=1200,
                    help="单字段最大字符，过长截断以控 seq_len")
    args = ap.parse_args()

    if args.make_template:
        make_template(args.make_template)
        return
    if not args.inp:
        raise SystemExit("请指定 --in <语料.jsonl>，或用 --make-template 生成模板。")

    rows = []
    with open(args.inp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    samples = []
    for e in rows:
        samples.extend(build_samples(e, args.max_chars))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"[done] 从 {len(rows)} 条语料生成 {len(samples)} 条审稿偏好样本 -> {out}")


if __name__ == "__main__":
    main()
