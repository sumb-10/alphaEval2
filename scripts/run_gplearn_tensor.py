#!/usr/bin/env python3
"""run_gplearn_tensor.py — gplearn 러너 (평가기 = 텐서 패널 프리로드).

run_gplearn_fast.py 의 사본으로, 세대 평가기를 FastICEvaluator(Qlib 배치 조회)
대신 TensorEvaluator(패널 1회 적재 + 연산자 직접 계산)로 교체한 것이다.

fast 러너와의 차이:
  * 시작 시 패널 프리로드 ~50s가 추가되지만, 이후 수식+IC 한 사이클이
    market=all 기준 10~18배 빠르다 (12.9~41s → 0.7~4.2s).
  * IC는 qlib 경로와 verify_tensor_eval.py 기준 37/37 비트 일치이지만
    '결과 불변 보장'은 아니다 — 드물게 ~1e-7 잔차가 tournament 순위를
    뒤집을 수 있다. 엄밀한 결과 불변이 필요하면 run_gplearn_fast.py 사용.
  * fit() 마지막 hall-of-fame 상관도 단계는 원본 execute() 경로(qlib 조회)를
    그대로 사용한다 (hall_of_fame 횟수만큼 조회 발생).

사용 예 (저장소 루트에서):
  python scripts/run_gplearn_tensor.py --start_time 2010-01-01 --end_time 2019-12-31 \
      --population_size 1000 --hall_of_fame 50 --n_components 10 --generations 5 \
      --market all --kernels 32 --out out/gplearn_tensor
"""

import argparse
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_PROVIDER = "/gpfs/home1/sku07891/00.hojin/QuantaAlpha/data/qlib/cn_data"


def init_qlib_once(provider_uri, kernels):
    """실 qlib.init 후, 이후의 모든 qlib.init 호출(placeholder 포함)을 무력화."""
    import qlib
    qlib.init(provider_uri=provider_uri, region="cn", kernels=kernels,
              expression_cache=None, dataset_cache=None)
    qlib._real_init = qlib.init
    qlib.init = lambda *a, **k: None


def save_results(df, out_prefix):
    os.makedirs(os.path.dirname(out_prefix) or ".", exist_ok=True)
    csv_path = out_prefix + ".csv"
    pkl_path = out_prefix + ".pkl"
    df.to_csv(csv_path, index=False)
    df.to_pickle(pkl_path)
    saved = [csv_path, pkl_path]
    try:
        df.to_parquet(out_prefix + ".parquet")
        saved.append(out_prefix + ".parquet")
    except Exception:
        pass
    return saved


def main(args):
    kernels = args.kernels or int(os.environ.get("SLURM_CPUS_PER_TASK", 0)) or 8
    init_qlib_once(args.provider_uri, kernels)

    import pandas as pd
    from qlib.data import D
    from fast_eval import ensure_backtest_importable, make_fast_parallel_evolve
    ensure_backtest_importable(REPO)
    import gplearn.genetic as G
    from gplearn.genetic import SymbolicTransformer
    from gplearn.config import functions_arity, FEATURE_LIST
    from tensor_eval import TensorEvaluator

    instruments = D.instruments(market=args.market)
    qlib_config = {
        "data_client": D,
        "instruments": instruments,
        "start_time": args.start_time,
        "end_time": args.end_time,
        "freq": "day",
    }

    t0 = time.perf_counter()
    evaluator = TensorEvaluator(args.start_time, args.end_time, market=args.market)
    t_panel = time.perf_counter() - t0
    print(f"[run] tensor panel preload {t_panel:.1f}s "
          f"(grid {len(evaluator.sel_dates)}d x {len(evaluator.columns)} stocks)")

    G._parallel_evolve = make_fast_parallel_evolve(evaluator)

    print(f"[run] evaluator=tensor market={args.market} kernels={kernels} "
          f"pop={args.population_size} gens={args.generations} seed={args.seed}")

    t0 = time.perf_counter()
    transformer = SymbolicTransformer(
        population_size=args.population_size,
        hall_of_fame=args.hall_of_fame,
        n_components=args.n_components,
        generations=args.generations,
        function_set=functions_arity.keys(),
        metric="pearson",
        parsimony_coefficient=0.0,
        qlib_config=qlib_config,
        feature_names=FEATURE_LIST,
        random_state=args.seed,
        n_jobs=1,
    )
    transformer.fit()
    t1 = time.perf_counter()

    records = [{"formula": str(p), "IC": p.fitness_} for p in transformer._best_programs]
    result_df = pd.DataFrame(records)
    print(result_df)
    saved = save_results(result_df, args.out)
    print(f"[run] total {t1 - t0:.1f}s (+panel {t_panel:.1f}s)  eval[{evaluator.stats()}]")
    print(f"[run] results saved to: {', '.join(saved)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Tensor-evaluator runner for AlphaEval gplearn")
    p.add_argument("--start_time", required=True)
    p.add_argument("--end_time", required=True)
    p.add_argument("--population_size", type=int, default=100)
    p.add_argument("--hall_of_fame", type=int, default=25)
    p.add_argument("--n_components", type=int, default=10)
    p.add_argument("--generations", type=int, default=10)
    p.add_argument("--market", default="all", help="qlib universe (all/csi300/...)")
    p.add_argument("--kernels", type=int, default=None,
                   help="qlib workers — 패널 적재/hall-of-fame 단계에만 사용")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--provider_uri", default=DEFAULT_PROVIDER)
    p.add_argument("--out", default="out/gplearn_tensor", help="output path prefix")
    main(p.parse_args())
