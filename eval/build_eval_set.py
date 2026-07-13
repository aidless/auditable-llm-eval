"""
TMLR 领域评估题库生成器 —— 产出 200 道 ML 评估题
覆盖 5 类题型 × 40 个核心知识点 = 200 道：
  mc(单选) / derive(公式推导) / exp(实验设计) / code(代码实现) / paper(论文理解)
每题含 id / category / type / question / (options,answer for mc) / reference(for open)

用法：
    python build_eval_set.py --out eval_questions.jsonl --seed 42
依赖：仅标准库
"""

import argparse
import json
import random
from pathlib import Path

# 40 个核心知识点：correct=正确陈述，wrong=常见误解（用于构造干扰项）
KNOWLEDGE = [
    ("过拟合与欠拟合", "过拟合是高方差、训练好测试差；欠拟合是高偏差、训练测试都差。",
     ["过拟合指训练集误差很大", "正则化会加剧过拟合", "测试误差低说明一定过拟合"]),
    ("偏差-方差权衡", "模型误差可分解为偏差²+方差+噪声，复杂度升高通常降偏差增方差。",
     ["偏差和方差总是同时增大", "简单模型方差一定为0", "噪声可通过加大数据消除"]),
    ("L1/L2 正则化", "L2 使权重趋小且平滑，L1 产生稀疏权重便于特征选择。",
     ["L1 不会产生稀疏解", "正则化系数越大越易过拟合", "L2 等价于权重绝对值惩罚"]),
    ("交叉熵损失", "交叉熵衡量预测分布与真实分布的差异，分类任务常用。",
     ["交叉熵只用于回归", "交叉熵越小预测越差", "二分类用 MSE 总是更好"]),
    ("梯度下降与学习率", "学习率过大易震荡不收敛，过小收敛慢。",
     ["学习率越大越好", "SGD 一定比 Adam 快", "学习率不影响收敛"]),
    ("反向传播", "反向传播用链式法则从输出层向输入层计算梯度。",
     ["反向传播是前向计算的逆过程", "只需计算输出层梯度", "反向传播不需要激活导数"]),
    ("ReLU 激活", "ReLU 在正区线性、负区为0，缓解梯度消失且计算快。",
     ["ReLU 处处可导", "ReLU 必导致死神经元无法恢复", " sigmoid 比 ReLU 更防梯度消失"]),
    ("Softmax 归一化", "softmax 将 logits 映射为和为1的正概率分布。",
     ["softmax 输出可为负", "softmax 不需要指数", "softmax 只用于隐藏层"]),
    ("批量归一化", "BatchNorm 对每个通道在 batch 内做标准化，加速收敛、略正则。",
     ["BatchNorm 在测试时用 batch 统计量", "BatchNorm 增加过拟合", "BatchNorm 不需要可学习参数"]),
    ("Dropout", "训练时随机丢弃部分神经元，推理时关闭丢弃并缩放，等效集成。",
     ["Dropout 在推理时也随机丢弃", "Dropout 增大模型容量", "Dropout 只能用于输入层"]),
    ("卷积神经网络", "CNN 用局部卷积提取空间特征，权值共享降低参数量。",
     ["卷积不共享权重", "CNN 只能处理图像", "池化层增加参数"]),
    ("循环神经网络", "RNN 通过隐藏状态在时间步间传递信息，适合序列。",
     ["RNN 无梯度问题", "RNN 不能处理变长序列", "LSTM 是为缓解长程依赖设计"]),
    ("注意力机制", "注意力按 Query/Key 相似度对 Value 加权，捕捉长程依赖。",
     ["注意力只能用于文本", "注意力计算与序列长度无关", "注意力权重和不必为1"]),
    ("Transformer 架构", "Transformer 完全基于注意力，摒弃循环与卷积。",
     ["Transformer 必须用 RNN 编码", "Transformer 不含前馈层", "自注意力是 Transformer 核心"]),
    ("自注意力计算", "自注意力通过 QKᵀ 缩放后 softmax 得权重再乘 V。",
     ["自注意力不需要缩放", "QKᵀ 得到的是概率", "V 不参与注意力输出"]),
    ("位置编码", "位置编码为序列注入顺序信息，因注意力本身置换不变。",
     ["注意力天然感知位置", "位置编码只用于解码器", "RoPE 不属于位置编码"]),
    ("词嵌入", "嵌入将离散 token 映射到稠密向量，蕴含语义相似度。",
     ["嵌入维度必须大于词表大小", "one-hot 是稠密嵌入", "嵌入不可训练"]),
    ("预训练与微调", "预训练在大规模语料学通用表示，微调适配下游任务。",
     ["微调一定比从头训差", "预训练不需要大量数据", "冻结底层常保通用特征"]),
    ("迁移学习", "迁移学习把源任务知识用于相关目标任务，缓解数据少。",
     ["迁移学习只用于图像", "负迁移不可能发生", "领域差异大时迁移需谨慎"]),
    ("数据增强", "数据增强通过对训练样本做合理变换扩充数据、提升泛化。",
     ["增强会引入错误标签", "增强只用于图像", "Mixup 是一种插值增强"]),
    ("类别不平衡", "类别不平衡可用重采样、类别权重或 focal loss 缓解。",
     ["不平衡直接用准确率评估即可", "下采样必丢信息", "Focal Loss 降低易分样本权重"]),
    ("精确率/召回率/F1", "精确率看预测正例中有多少真正，召回率看真正例中有多少被召回。",
     ["F1 是精确率加召回率", "精确率高召回必高", "类别不均时准确率不可靠"]),
    ("ROC 与 AUC", "AUC 表示随机正例排在负例前的概率，衡量排序质量。",
     ["AUC=0.5 是完美分类", "AUC 依赖阈值", "AUC 对不平衡不敏感"]),
    ("混淆矩阵", "混淆矩阵给出 TP/FP/FN/TN，是分类指标的基础。",
     ["混淆矩阵只用于二分类", "TN 不在矩阵中", "由混淆矩阵可算 F1"]),
    ("交叉验证", "k 折交叉验证将数据分 k 份轮流验证，估计泛化稳定性。",
     ["交叉验证一定能提升测试精度", "留一法开销最小", "k 折可降低评估方差"]),
    ("贝叶斯推断", "贝叶斯推断结合先验与似然得到后验，量化参数不确定性。",
     ["贝叶斯只用似然", "先验总可被忽略", "后验未必有解析解"]),
    ("最大似然估计", "MLE 选择使观测数据似然最大的参数。",
     ["MLE 总是无偏", "MLE 等价于最小化 NLL", "MLE 需要先验分布"]),
    ("最大后验估计", "MAP 在 MLE 基础上加入先验作为正则。",
     ["MAP 不使用似然", "MAP 等价于 L2 当先验为高斯", "MAP 与 MLE 永不重合"]),
    ("KL 散度", "KL 散度衡量两分布差异，非负且在相等时为0，不对称。",
     ["KL 是对称距离", "KL 可为负", "KL=0 当且仅当两分布相同"]),
    ("变分自编码器", "VAE 用隐变量与重参数技巧最大化证据下界(ELBO)。",
     ["VAE 是判别模型", "ELBO 是似然的上界", "重参数化使梯度可回传"]),
    ("生成对抗网络", "GAN 由生成器与判别器极小极大博弈生成样本。",
     ["GAN 训练总是稳定", "判别器输出概率", "WGAN 用 Earth-Mover 距离缓解模式崩塌"]),
    ("强化学习基础", "RL 智能体通过与环境交互、最大化累积奖励学习策略。",
     ["RL 不需要奖励信号", "策略是状态到动作的映射", "RL 只用于游戏"]),
    ("策略梯度", "策略梯度直接对策略参数求导，沿回报梯度上升。",
     ["策略梯度无方差问题", "REINFORCE 使用蒙特卡洛回报", "策略梯度只能离散动作"]),
    ("马尔可夫决策过程", "MDP 用状态、动作、转移、奖励、折扣描述序贯决策。",
     ["MDP 要求状态完全可观测", "折扣因子只能为1", "转移概率必须已知才能学习"]),
    ("主成分分析", "PCA 通过协方差特征分解找最大方差方向做线性降维。",
     ["PCA 是非线性的", "PCA 需标签", "主成分彼此正交"]),
    ("KMeans 聚类", "KMeans 迭代更新簇中心最小化样本到中心距离。",
     ["KMeans 能处理任意形状簇", "K 必须自动确定", "KMeans 对初始化敏感"]),
    ("t-SNE 降维", "t-SNE 保留局部邻域结构，适合高维可视化。",
     ["t-SNE 适合训练特征", "t-SNE 保持全局距离准确", "t-SNE 输出可解释坐标轴"]),
    ("集成学习", "集成通过结合多个弱学习器（如 Bagging/Boosting）提升泛化。",
     ["集成总比单模型慢且差", "随机森林是 Bagging 集成", "Boosting 串行降低偏差"]),
    ("梯度消失/爆炸", "深层网络中梯度连乘导致趋零或发散，残差连接可缓解。",
     ["梯度消失只发生在 ReLU", "残差连接无助于此", "合理初始化可缓解爆炸"]),
    ("学习率调度", "预热避免训练初期不稳定，余弦/阶梯衰减平衡收敛速度与最终精度。",
     ["学习率调度只用于 Adam 优化器", "预热总会降低最终精度", "余弦衰减前期降得快、后期降得慢"]),
]


def build(seed: int = 42):
    random.seed(seed)
    questions = []
    qid = 0
    for name, correct, wrongs in KNOWLEDGE:
        # mc
        opts = [correct] + wrongs[:3]
        random.shuffle(opts)
        questions.append({
            "id": f"mc-{qid:03d}", "category": name, "type": "mc",
            "question": f"关于「{name}」，下列说法正确的是？",
            "options": opts, "answer": correct,
        })
        qid += 1
        # derive
        questions.append({
            "id": f"derive-{qid:03d}", "category": name, "type": "derive",
            "question": f"请推导与「{name}」相关的关键数学公式，并说明每步依据。",
            "reference": f"应围绕 {name} 的核心定义/目标函数，写出推导并解释假设。",
        })
        qid += 1
        # exp
        questions.append({
            "id": f"exp-{qid:03d}", "category": name, "type": "exp",
            "question": f"如何设计实验验证「{name}」对模型性能的影响？给出假设、变量与统计检验。",
            "reference": "需明确可检验假设、控制变量、多次随机种子、显著性检验与效应量报告。",
        })
        qid += 1
        # code
        questions.append({
            "id": f"code-{qid:03d}", "category": name, "type": "code",
            "question": f"用 PyTorch 实现一个与「{name}」相关的组件或函数，并说明数值稳定性处理。",
            "reference": "代码应可直接运行，包含前向计算与必要的 clamp/eps 等稳定性处理。",
        })
        qid += 1
        # paper
        questions.append({
            "id": f"paper-{qid:03d}", "category": name, "type": "paper",
            "question": f"请总结「{name}」相关的研究进展要点、典型方法与其局限。",
            "reference": "应覆盖动机、代表性方法、适用场景与已知局限。",
        })
        qid += 1
    return questions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval_questions.jsonl")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    qs = build(args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for q in qs:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    # 统计
    from collections import Counter
    cnt = Counter(q["type"] for q in qs)
    print(f"[done] 生成 {len(qs)} 道题 -> {out}")
    print("题型分布:", dict(cnt))


if __name__ == "__main__":
    main()
