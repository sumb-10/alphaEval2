#!/usr/bin/env python3
"""run_gplearn_fast.py — gplearn.py의 결과 불변 고속 러너 (원본 파일 무수정).

원본 gplearn.py 대비:
  1. qlib.init을 실데이터 경로 + kernels 지정으로 수행하고,
     backtest/ictester.py의 import 시점 placeholder 재-init을 no-op으로 차단
  2. gplearn.genetic._parallel_evolve 를 배치 평가판(fast_eval)으로 monkey-patch
     → 개체당 Qlib 조회 3회(factor×2+label×1)가 chunk당 1회 + label 1회로 감소
     → 같은 random_state면 생성되는 factor와 IC가 원본과 동일 (verify_equivalence.py로 확인)
  3. 원본에 빠져 있는 transformer.fit() 호출 포함
  4. 저장은 CSV + pickle (AlphaEval38 env에 parquet 엔진이 없음; 있으면 parquet도 저장)

사용 예 (저장소 루트에서):
  python scripts/run_gplearn_fast.py --start_time 2010-01-01 --end_time 2019-12-31 \
      --population_size 1000 --hall_of_fame 50 --n_components 10 --generations 5 \
      --market all --kernels 32 --out out/gplearn_fast
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
    qlib.init = lambda *a, **k: None   # backtest/ictester.py의 module-level 재-init 차단


def save_results(df, out_prefix):
    os.makedirs(os.path.dirname(out_prefix) or ".", exist_ok=True)
    csv_path = out_prefix + ".csv"
    pkl_path = out_prefix + ".pkl"
    df.to_csv(csv_path, index=False)
    df.to_pickle(pkl_path)
    saved = [csv_path, pkl_path]
    try:
        pq_path = out_prefix + ".parquet"
        df.to_parquet(pq_path)          # pyarrow/fastparquet 있을 때만 성공
        saved.append(pq_path)
    except Exception:
        pass
    return saved


def main(args):
    kernels = args.kernels or int(os.environ.get("SLURM_CPUS_PER_TASK", 0)) or 8
    init_qlib_once(args.provider_uri, kernels)

    # qlib 초기화 이후에만 import 가능 (모듈 기본 인자가 import 시점에 D.instruments를 평가)
    import pandas as pd
    from qlib.data import D
    from fast_eval import ensure_backtest_importable
    ensure_backtest_importable(REPO)   # backtest/backtester.py 누락 보완 (원본 무수정)
    import gplearn.genetic as G
    from gplearn.genetic import SymbolicTransformer
    from gplearn.config import functions_arity, FEATURE_LIST
    from fast_eval import FastICEvaluator, make_fast_parallel_evolve  # noqa: E402

    instruments = D.instruments(market=args.market)
    qlib_config = {
        "data_client": D,
        "instruments": instruments,
        "start_time": args.start_time,
        "end_time": args.end_time,
        "freq": "day",
    }

    evaluator = FastICEvaluator(instruments, args.start_time, args.end_time,
                                freq="day", chunk_size=args.chunk_size)
    G._parallel_evolve = make_fast_parallel_evolve(evaluator)

    print(f"[run] market={args.market} kernels={kernels} chunk={args.chunk_size} "
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
        n_jobs=1,   # qlib 내부 ParallelExt와의 중첩 병렬 금지 — 병렬성은 kernels로 확보
    )
    transformer.fit()          # 원본 gplearn.py에 빠져 있는 호출
    t1 = time.perf_counter()

    records = [{"formula": str(p), "IC": p.fitness_} for p in transformer._best_programs]
    result_df = pd.DataFrame(records)
    print(result_df)
    saved = save_results(result_df, args.out)
    print(f"[run] total {t1 - t0:.1f}s  eval[{evaluator.stats()}]")
    print(f"[run] results saved to: {', '.join(saved)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Result-invariant fast runner for AlphaEval gplearn")
    p.add_argument("--start_time", required=True)
    p.add_argument("--end_time", required=True)
    p.add_argument("--population_size", type=int, default=100)
    p.add_argument("--hall_of_fame", type=int, default=25)
    p.add_argument("--n_components", type=int, default=10)
    p.add_argument("--generations", type=int, default=10)
    p.add_argument("--market", default="all", help="qlib universe (all/csi300/...)")
    p.add_argument("--kernels", type=int, default=None,
                   help="qlib internal workers (default: SLURM_CPUS_PER_TASK or 8)")
    p.add_argument("--chunk_size", type=int, default=24, help="expressions per D.features call")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--provider_uri", default=DEFAULT_PROVIDER)
    p.add_argument("--out", default="out/gplearn_fast", help="output path prefix (no extension)")
    main(p.parse_args())
