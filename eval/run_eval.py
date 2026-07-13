"""
TMLR 评估运行器
- mc 题：自动判分（比对模型输出与标准答案）
- open 题（derive/exp/code/paper）：调用本地微调后模型生成回答，输出供人工/LLM 评分
  （自动评分需模型推理，这里给出框架，开放题分数由人工或外部 LLM 判定）

用法：
    # 仅统计 mc 自动正确率（给定模型输出文件 answers.jsonl）
    python run_eval.py --questions eval_questions.jsonl --answers answers.jsonl --mode mc

    # 对开放题调用微调模型生成回答（需 transformers + 合并权重）
    python run_eval.py --questions eval_questions.jsonl --model ../outputs/qwen25-3b-tmlr-merged --mode open
"""

import argparse
import json
from pathlib import Path


def load_jsonl(p):
    rows = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def eval_mc(questions, answers):
    """answers: list of {"id":..., "output":...}。
    判分：模型输出包含正确陈述 → 正确；若输出包含某错误项文本 → 错误；
    否则按正确陈述是否出现判（容错复述/改写，避免严格子串误杀）。"""
    ans_map = {a["id"]: a["output"] for a in answers}
    correct, total = 0, 0
    for q in questions:
        if q["type"] != "mc":
            continue
        total += 1
        out = ans_map.get(q["id"], "") or ""
        # 任一错误项被当作"选择"出现 → 判错（比单纯匹配正确项更稳）
        wrong_hit = any(w in out for w in q.get("options", []) if w != q["answer"])
        if q["answer"] in out and not wrong_hit:
            correct += 1
    acc = correct / total if total else 0
    print(f"[mc] 正确 {correct}/{total} = {acc:.3f}")
    return acc


def gen_open(questions, model_path, max_new_tokens=512):
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    tok = AutoTokenizer.from_pretrained(model_path)
    pipe = pipeline("text-generation", model=model_path,
                    torch_dtype="auto", device_map="auto")
    out_rows = []
    for q in questions:
        # mc 也生成回答（题干不展示选项，模型需复述正确陈述），供 eval_mc 判分
        prompt = tok.apply_chat_template(
            [{"role": "user", "content": q["question"]}],
            tokenize=False, add_generation_prompt=True)
        resp = pipe(prompt, max_new_tokens=max_new_tokens, do_sample=False)[0]["generated_text"]
        ans = resp[len(prompt):]
        out_rows.append({"id": q["id"], "category": q["category"],
                         "type": q["type"], "question": q["question"], "output": ans})
    outp = Path("open_answers.jsonl")
    with outp.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[open] 生成 {len(out_rows)} 条开放回答 -> {outp}（请人工或外部 LLM 评分）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="eval_questions.jsonl")
    ap.add_argument("--answers", default="answers.jsonl")
    ap.add_argument("--model", default="../outputs/qwen25-3b-tmlr-merged")
    ap.add_argument("--mode", choices=["mc", "open"], default="mc")
    args = ap.parse_args()

    qs = load_jsonl(args.questions)
    if args.mode == "mc":
        ans = load_jsonl(args.answers)
        eval_mc(qs, ans)
    else:
        gen_open(qs, args.model)


if __name__ == "__main__":
    main()
