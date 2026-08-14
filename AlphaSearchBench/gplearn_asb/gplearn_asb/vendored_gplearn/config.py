window_lengths = [5, 12, 30, 64]

FEATURE_LIST = ["$adjclose", "$amount", "$change", "$close", "$factor", "$high", "$low", "$open", "$volume", "$vwap"]

functions_arity = {
    # 一元算子
    "Abs": 1,
    "Sign": 1,
    "Log": 1,
    # "Not": 1,

    # 二元算子
    "Add": 2,
    "Sub": 2,
    "Mul": 2,
    "Div": 2,
    "Power": 2,
    "Greater": 2,
    "Less": 2,
    # "And": 2,
    # "Or": 2,

    # Rolling 类算子，均设为 arity=4
    "Ref": 4,
    "Mean": 4,
    "Sum": 4,
    "Std": 4,
    "Var": 4,
    "Skew": 4,
    "Kurt": 4,
    "Min": 4,
    "Max": 4,
    "IdxMin": 4,
    "IdxMax": 4,
    "Med": 4,
    "Mad": 4,
    "Delta": 4,
    "Slope": 4,
    "Rsquare": 4,
    "Resi": 4,
    "WMA": 4,
    "EMA": 4,
    # "Cov": 4,
    # "Corr": 4,
    # "Quantile": 4,
}

