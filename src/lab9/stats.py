"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError(f"length mismatch: human={len(human)}, judge={len(judge)}")
    # Chuẩn hóa nhãn và đếm 4 ô ma trận nhầm lẫn với POS = "FAIL" là lớp dương
    tp = fp = fn = tn = 0
    for h_raw, j_raw in zip(human, judge):
        h_pos = h_raw.strip().upper() == POS
        j_pos = j_raw.strip().upper() == POS
        if h_pos and j_pos:
            tp += 1
        elif not h_pos and j_pos:
            fp += 1
        elif h_pos and not j_pos:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    # Precision = tp/(tp+fp), Recall = tp/(tp+fn); trả 0.0 khi mẫu số bằng 0
    cm = confusion(human, judge)
    p_den = cm["tp"] + cm["fp"]
    r_den = cm["tp"] + cm["fn"]
    precision = cm["tp"] / p_den if p_den else 0.0
    recall = cm["tp"] / r_den if r_den else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    cm = confusion(human, judge)
    n = cm["tp"] + cm["fp"] + cm["fn"] + cm["tn"]
    if n == 0:
        raise ValueError("cohen_kappa undefined on empty input")
    # Tỉ lệ đồng thuận quan sát (p_o) và đồng thuận ngẫu nhiên kỳ vọng (p_e)
    p_o = (cm["tp"] + cm["tn"]) / n
    human_pos = (cm["tp"] + cm["fn"]) / n
    judge_pos = (cm["tp"] + cm["fp"]) / n
    human_neg = 1.0 - human_pos
    judge_neg = 1.0 - judge_pos
    p_e = human_pos * judge_pos + human_neg * judge_neg
    if abs(1.0 - p_e) < 1e-12:
        raise ValueError("cohen_kappa undefined when p_e == 1 (constant labels)")
    return (p_o - p_e) / (1.0 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    # Công thức Rogan-Gladen: (p_obs + spec - 1) / (sens + spec - 1), cắt về [0, 1]
    denom = sensitivity + specificity - 1.0
    if denom <= 0.0:
        return max(0.0, min(1.0, observed_rate))
    corrected = (observed_rate + specificity - 1.0) / denom
    return max(0.0, min(1.0, corrected))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy.stats import bootstrap

    if len(a) != len(b):
        raise ValueError(f"length mismatch: a={len(a)}, b={len(b)}")
    if len(a) == 0:
        raise ValueError("paired_bootstrap requires at least one paired item")

    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    # Nếu hai phiên bản giống hệt nhau trên mọi item -> hiệu và CI đều bằng 0
    if np.array_equal(arr_a, arr_b):
        return (0.0, 0.0, 0.0)

    diff_mean = float(np.mean(arr_a - arr_b))
    # Paired bootstrap theo từng item (cùng item, cùng thứ tự) bằng phương pháp percentile
    res = bootstrap(
        (arr_a, arr_b),
        statistic=lambda x, y, axis=-1: np.mean(x - y, axis=axis),
        paired=True,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="percentile",
        rng=np.random.default_rng(rng),
    )
    return (diff_mean, float(res.confidence_interval.low), float(res.confidence_interval.high))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    # TODO M6
    raise NotImplementedError


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    # TODO M6
    raise NotImplementedError
