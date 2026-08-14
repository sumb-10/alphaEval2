"""Phase 6 smoke: PFS — ε=0→1, seed 재현, 텐서 공유, t(3) 스케일, legacy 모드.

실데이터(smoke config) 사용 — 패널 로드 때문에 수 분 소요.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.config import Config                       # noqa: E402
from alphasearchbench.qd.pfs import PFSEvaluator, _rng_for, _draw_noise  # noqa: E402

FORMULA = "Mean($close, 30)"


@pytest.fixture(scope="module")
def ctx():
    from alphasearchbench.data.signal_context import SignalContext
    cfg = Config.load(os.path.join(ASB_ROOT, "configs", "smoke.yaml"))
    return SignalContext(cfg)


@pytest.fixture(scope="module")
def cfg():
    return Config.load(os.path.join(ASB_ROOT, "configs", "smoke.yaml"))


def test_noise_scale_gaussian_and_t3():
    rng = _rng_for(["scale", "check"])
    sigma = 0.0123
    g = _draw_noise(rng, (200000,), "gaussian", sigma, 3)
    t = _draw_noise(rng, (200000,), "student_t", sigma, 3)
    assert np.std(g) == pytest.approx(sigma, rel=0.02)
    assert np.std(t) == pytest.approx(sigma, rel=0.05)     # 동일 std로 rescale
    # t(3)는 fat tail — 극단값 비율이 Gaussian보다 큼
    assert (np.abs(t) > 4 * sigma).mean() > (np.abs(g) > 4 * sigma).mean()


def test_epsilon_zero_gives_pfs_one(ctx, cfg):
    ev = PFSEvaluator(ctx, cfg, sigma_override=0.0)
    row = ev.evaluate_factor(FORMULA, split="test")
    assert row["PFS_Gaussian"] == pytest.approx(1.0, abs=1e-9)
    assert row["PFS_t"] == pytest.approx(1.0, abs=1e-9)
    assert row["PFS_min"] == pytest.approx(1.0, abs=1e-9)


def test_seed_reproducibility_and_tensor_sharing(ctx, cfg):
    ev1 = PFSEvaluator(ctx, cfg)
    r1 = ev1.evaluate_factor(FORMULA, split="test")
    r1b = ev1.evaluate_factor("Std($high, 12)", split="test")
    ev2 = PFSEvaluator(ctx, cfg)
    r2 = ev2.evaluate_factor(FORMULA, split="test")
    # 같은 seed/config → 완전 재현
    for k in ("PFS_Gaussian", "PFS_t", "PFS_min"):
        assert r1[k] == r2[k]
    # 서로 다른 formula가 동일 perturbed tensor를 공유 (draw당 엔진 1개)
    assert len(ev1._pert_engine_cache) == 2 * ev1.k_draws   # gaussian+t × K
    e_a = ev1._perturbed_engine("test", "gaussian", 0)
    e_b = ev2._perturbed_engine("test", "gaussian", 0)
    assert np.array_equal(e_a.panels["$close"], e_b.panels["$close"],
                          equal_nan=True)                    # 결정론적 동일 텐서
    # sigma는 train benchmark 일변동성 (양수, 그럴듯한 스케일)
    assert 0.001 < ev1.sigma < 0.1
    assert np.isfinite(r1["PFS_Gaussian"]) and np.isfinite(r1b["PFS_Gaussian"])


def test_legacy_mode_separate_naming(ctx, cfg):
    cfg2 = Config.load(os.path.join(ASB_ROOT, "configs", "smoke.yaml"),
                       overrides={"pfs": {"mode": "legacy_alphaeval"}})
    ev = PFSEvaluator(ctx, cfg2)
    row = ev.evaluate_factor(FORMULA, split="test")
    assert "PFS_Gaussian_legacy" in row and "PFS_min_legacy" in row
    assert "PFS_Gaussian" not in row                        # 이름 혼용 금지
    assert 0.0 < row["PFS_Gaussian_legacy"] <= 1.0
    # legacy도 시드 결정론
    row2 = PFSEvaluator(ctx, cfg2).evaluate_factor(FORMULA, split="test")
    assert row["PFS_Gaussian_legacy"] == row2["PFS_Gaussian_legacy"]


def test_experimental_mode_flagged(ctx, cfg):
    cfg3 = Config.load(os.path.join(ASB_ROOT, "configs", "smoke.yaml"),
                       overrides={"pfs": {"mode": "relative_input", "k_draws": 1}})
    ev = PFSEvaluator(ctx, cfg3)
    row = ev.evaluate_factor(FORMULA, split="test")
    assert row["experimental"] is True
    assert "PFS_Gaussian_relative_input" in row             # 별도 네임스페이스
