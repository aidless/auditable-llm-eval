"""
arXiv 正文级采集器（解析 full-text 源码包）
- 用 arxiv 库下载论文源码包(.tar.gz) -> 解压 -> 解析 .tex 正文
- 复用 convert_manuscript.build_samples_from_text 生成 A/C/B/F 类 CoT 样本
- 相比 build_dataset.py（仅摘要级），本文可拿到方法/实验/公式的真实正文，质量更高
- 可选混入通用指令数据防遗忘
- 输出 fulltext_cot_data.jsonl（ShareGPT 风格）

依赖：
    pip install arxiv
    # 下载源码需联网；若已离线准备好论文源，用 --from-dir 读本地解压目录

用法：
    python build_dataset_fulltext.py --max-papers 100 --general-ratio 0.2 --out fulltext_cot_data.jsonl
    python build_dataset_fulltext.py --from-dir ./papers_src --out fulltext_cot_data.jsonl
"""

import argparse
import json
import os
import random
import tarfile
import tempfile
from pathlib import Path

import convert_manuscript as cm


def _extract_tex_from_tar(tar_path: str, work_dir: str) -> list:
    """解压源码包，返回其中 .tex 文件路径列表。"""
    texs = []
    try:
        with tarfile.open(tar_path, "r:*") as tar:
            tar.extractall(path=work_dir, filter="data")
        for root, _, files in os.walk(work_dir):
            for fn in files:
                if fn.endswith(".tex"):
                    texs.append(os.path.join(root, fn))
    except Exception as e:
        print(f"[warn] 解压失败 {tar_path}: {e}")
    return texs


def _download_source(result, cache_dir: str):
    """下载论文源码包，返回 .tar.gz 路径；失败（或 arXiv 端点返回非 gzip）返回 None。

    兼容性说明（2026-07 实测）：
    - arxiv <4：Result 自带 `download_source(dirpath=...)`，直接用。
    - arxiv >=4：`download_source` 已被移除，`source_url` 变为需调用的方法，
      且其返回的端点（/e-print/ 或 /src/）近期被 arXiv 服务端改为返回 PDF。
      故新版一律自行下载并校验 gzip magic；若拿到 PDF/HTML 则视为失败。
    """
    import urllib.request
    tar_path = None
    # 1) 旧版 arxiv：直接有 download_source
    if hasattr(result, "download_source"):
        try:
            tar_path = result.download_source(dirpath=cache_dir)
        except Exception:
            tar_path = None
    # 2) 新版 arxiv：source_url() 给出端点，或兜底构造 e-print 端点，自行下载
    if not tar_path:
        url = None
        if hasattr(result, "source_url"):
            try:
                url = result.source_url()
                if callable(url):
                    url = url()
            except Exception:
                url = None
        if not url:
            sid = result.get_short_id() if hasattr(result, "get_short_id") else ""
            url = f"https://arxiv.org/e-print/{sid}"
        sid = result.get_short_id() if hasattr(result, "get_short_id") else "paper"
        tar_path = os.path.join(cache_dir, sid.replace("/", "_") + ".tar.gz")
        try:
            urllib.request.urlretrieve(url, tar_path)
            with open(tar_path, "rb") as f:
                magic = f.read(2)
            if magic != b"\x1f\x8b":  # 非 gzip（arXiv 现返回 PDF/HTML）→ 降级
                os.remove(tar_path)
                return None
        except Exception:
            return None
    return tar_path


def fetch_fulltext(max_papers: int, cache_dir: str):
    """下载 arXiv 源码包并解析正文，返回 list[dict]{title, text}。

    注意：arXiv 服务端（约 2025 起）已不再通过 /e-print/、/src/ 提供源码包
    （统一重定向为 PDF），程序化下载源码当前不可靠。本函数会尝试下载并校验
    gzip；若端点返回 PDF/HTML 或出错，则**降级为摘要**（text=r.summary），
    不崩溃。真正的正文级数据请用 --from-dir 传入手动下载的源码包。
    """
    try:
        import arxiv
    except ImportError:
        raise SystemExit("未安装 arxiv 库，请先 `pip install arxiv`；或改用 --from-dir 读本地源码。")
    os.makedirs(cache_dir, exist_ok=True)
    client = arxiv.Client(page_size=50, delay_seconds=3, num_retries=3)
    search = arxiv.Search(query="cat:cs.LG OR cat:cs.CL OR cat:cs.AI OR cat:stat.ML",
                          max_results=max_papers, sort_by=arxiv.SortCriterion.Relevance)
    papers = []
    n_full = n_abs = 0
    for r in client.results(search):
        title = r.title
        tar_path = _download_source(r, cache_dir)
        if tar_path:
            with tempfile.TemporaryDirectory() as wd:
                texs = _extract_tex_from_tar(tar_path, wd)
                full = []
                for tp in texs:
                    try:
                        full.append(Path(tp).read_text(encoding="utf-8", errors="ignore"))
                    except Exception:
                        pass
            if full:
                papers.append({"title": title, "text": "\n".join(full)})
                n_full += 1
            else:
                papers.append({"title": title, "text": r.summary})  # 无 .tex → 摘要
                n_abs += 1
        else:
            papers.append({"title": title, "text": r.summary})  # 源码端点失效 → 摘要
            n_abs += 1
    print(f"[info] 正文级成功 {n_full} 篇 / 降级为摘要 {n_abs} 篇"
          f"（若 n_full 偏低，多为 arXiv 源码端点返回 PDF 所致，建议改用 --from-dir）")
    return papers


def load_local_dir(dir_path: str):
    """读本地已解压的论文源：每个子目录是一篇论文，内含 .tex。"""
    rows = []
    for sub in sorted(Path(dir_path).iterdir()):
        if not sub.is_dir():
            continue
        texs = [str(p) for p in sub.rglob("*.tex")]
        texts = []
        for tp in texs:
            texts.append(Path(tp).read_text(encoding="utf-8", errors="ignore"))
        if texts:
            rows.append({"title": sub.name, "text": "\n".join(texts)})
    return rows


def build_samples(papers: list, seed: int = 42, max_formulas: int = 5):
    samples = []
    for p in papers:
        samples.extend(cm.build_samples_from_text(
            p["title"], p["text"], max_chars=1500, max_formulas=max_formulas))
    return samples


def add_general(samples: list, ratio: float, seed: int = 42):
    if ratio <= 0:
        return samples
    random.seed(seed)
    n_gen = int(len(samples) * ratio / (1 - ratio))
    general_pool = [
        ("用一句话解释什么是过拟合。", "过拟合指模型在训练集上误差很小，但在未见数据上泛化误差大，通常因容量过大或训练过久。"),
        ("把这段中文翻译成英文：模型在测试集上表现稳定。", "The model performs stably on the test set."),
        ("列举三种常见的正则表达式用途。", "1) 邮箱/手机号校验；2) 日志提取；3) 代码静态分析中的模式匹配。"),
        ("写一段 Python 读取 CSV 的前五行。", "import pandas as pd\ndf = pd.read_csv('data.csv')\nprint(df.head())"),
        ("什么是 REST API？", "REST 是一种基于 HTTP 资源的接口风格，用标准方法操作资源，无状态且可缓存。"),
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
    ap.add_argument("--max-papers", type=int, default=100)
    ap.add_argument("--from-dir", type=str, default="",
                    help="本地已解压论文源目录（每子目录一篇，含 .tex）")
    ap.add_argument("--cache-dir", type=str, default="F:/arxiv_src",
                    help="arXiv 源码包缓存目录（默认 F 盘，避开 C 盘空间压力）")
    ap.add_argument("--general-ratio", type=float, default=0.2)
    ap.add_argument("--max-formulas", type=int, default=5)
    ap.add_argument("--out", default="fulltext_cot_data.jsonl")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if args.from_dir:
        papers = load_local_dir(args.from_dir)
    else:
        papers = fetch_fulltext(args.max_papers, args.cache_dir)
    print(f"[info] 论文数: {len(papers)}")

    samples = build_samples(papers, seed=args.seed, max_formulas=args.max_formulas)
    samples = add_general(samples, args.general_ratio, seed=args.seed)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"[done] 正文级生成 {len(samples)} 条训练样本 -> {out}")


if __name__ == "__main__":
    main()
