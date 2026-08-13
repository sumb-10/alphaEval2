#!/usr/bin/env python3
import multiprocessing
# multiprocessing.cpu_count = lambda: 10
import argparse
import numpy as np
import pandas as pd
import qlib

# 1. Initialize Qlib
qlib.init(
    provider_uri="path/to/your/qlib_data",
    region="cn"
)

from qlib.data import D
from gplearn.genetic import SymbolicTransformer
from gplearn.config import functions_arity, FEATURE_LIST
from scipy.stats import spearmanr

# import warnings
# warnings.filterwarnings('ignore', category=RuntimeWarning)

import time

def main(args):
    start = time.perf_counter()

    # 2. Prepare Qlib configuration
    qlib_config = {
        "data_client": D,
        "instruments": D.instruments(market="all"),
        "start_time": args.start_time,
        "end_time": args.end_time,
        "freq": "day",
    }

    # 3. Create and run SymbolicTransformer
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
        random_state=42
    )

    end = time.perf_counter()
    print(f"gplearn total time: {end - start:.6f} sec")
    transformer.fit() 

    # 6. Collect best programs and compute metrics
    programs = transformer._best_programs
    records = []
    for _, prog in enumerate(programs):
        expr = str(prog)
        ic = prog.fitness_
        records.append({"formula": expr, "IC": ic})

    # 7. Create DataFrame and save results
    result_df = pd.DataFrame(records)
    print(result_df)
    result_df.to_parquet("your.parquet")
    print("Results saved to your.parquet")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GP SymbolicTransformer on Qlib data")
    parser.add_argument("--start_time", required=True, help="Data start time in YYYY-MM-DD format")
    parser.add_argument("--end_time", required=True, help="Data end time in YYYY-MM-DD format")
    parser.add_argument("--population_size", type=int, default=100, help="Population size")
    parser.add_argument("--hall_of_fame", type=int, default=25, help="Hall of fame size")
    parser.add_argument("--n_components", type=int, default=10, help="Number of components")
    parser.add_argument("--generations", type=int, default=10, help="Number of generations")
    args = parser.parse_args()
    main(args)
