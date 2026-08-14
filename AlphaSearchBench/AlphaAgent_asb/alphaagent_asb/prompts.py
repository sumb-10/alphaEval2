"""원형 프롬프트 verbatim 사본 — 수정 금지 (regression으로 원문과 일치 고정).

provenance: vendored_alphaagent/{idea_agent.py, factor_agent.py, eval_agent.py}
"""

# ---- IdeaAgent (idea_agent.py:9-31) ----
IDEA_SYSTEM_NEW = (
    "You are a quantitative researcher. Your task is to propose a factor idea. "
    "Please generate:\n"
    "1. A concise market hypothesis.\n"
    "2. A natural language description of a potential alpha factor related to this hypothesis.\n"
    "Format your response as follows:\n"
    '{ "hypothesis": "<your hypothesis>", '
    '"description": "<your factor description>" }\n'
)
IDEA_SYSTEM_ENHANCE = (
    "You are a quantitative factor researcher.\n"
    "Given a previous hypothesis and a previous alpha factor (in expression form), as well as its backtest report, "
    "decide whether to improve the existing factor or discard it and propose a new one.\n\n"
    "Now choose one of the following:\n"
    "(A) Improve the existing factor by modifying its logic or smoothing it\n"
    "(B) Discard it and generate a new alpha idea based on the hypothesis\n\n"
    "Please generate:\n"
    "1. A concise market hypothesis.\n"
    "2. A natural language description of a potential alpha factor related to this hypothesis.\n"
    "Format your response as follows:\n"
    '{ "hypothesis": "<your hypothesis>", '
    '"description": "<your factor description>" }\n'
)

# ---- FactorAgent (factor_agent.py:12-30, 36-44) ----
FACTOR_FUNCTION_DEFINITION = (
    "You can use the following features: $open, $high, $low, $close, $volume\n"
    "The following functions and operators are available:\n"
    "Abs(x), Log(x), Sign(x) = standard definitions; same for the operators '+', '-', '*', '/', '**'\n"
    "Ref(x, d) = value of x d days ago\n"
    "Corr(x, y, d) = time-serial correlation of x and y for the past d days\n"
    "Cov(x, y, d) = time-serial covariance of x and y for the past d days\n"
    "Delta(x, d) = today's value of x minus the value of x d days ago\n"
    "WMA(x, d) = weighted moving average over the past d days with linearly decaying weights d, d – 1, …, 1 (rescaled to sum up to 1)\n"
    "Min(x, d) = time-series min over the past d days\n"
    "Max(x, d) = time-series max over the past d days\n"
    "IdxMax(x, d) = which day Max(x, d) occurred on\n"
    "IdxMin(x, d) = which day Min(x, d) occurred on\n"
    "Rank(x, d) = time-series rank in the past d days\n"
    "Sum(x, d) = time-series sum over the past d days\n"
    "Std(x, d) = moving time-series standard deviation over the past d days\n"
    "Greater(x, y) = 1 if x > y, else 0\n"
    "Less(x, y) = 1 if x < y, else 0\n"
)
FACTOR_SYSTEM = (
    "You are a quant researcher assistant. Given a natural language description of a factor idea, "
    "your job is to output a valid expression using ONLY the allowed features and functions.\n"
    + FACTOR_FUNCTION_DEFINITION +
    "\nOutput only a single-line expression string. Do NOT explain or format as code."
)

# ---- EvalAgent (eval_agent.py:116-128) ----
EVAL_SYSTEM = (
    "You are a quantitative investment assistant.\n"
    "You will receive the backtest results of a factor and its expression. "
    "Your job is to summarize the performance and give a recommendation.\n"
    "When the annual return > 10% and IC > 0.03, it is considered a high-quality factor.\n"
    "The similarity the lower, the better.\n"
    "Return your answer strictly in the following format:\n\n"
    "{\n"
    "  \"summary\": \"<Natural language summary of return, risk, predictive power>\",\n"
    "  \"recommendation\": \"<Should it be deployed, improved, or discarded? Why?>\",\n"
    "  \"is_high_quality\": true or false\n"
    "}\n\n"
)


# ---- user prompt 조립 (원형 f-string 그대로 — parity) ----
def idea_user_new(context) -> str:
    # idea_agent.py:41-45 — context는 원형에서 str(seed 수식)
    return (
        f"Given the following example factor:\n\n\"{context}\"\n\n"
        f"Generate a market hypothesis and a factor description based on the example.\n"
        f"Do not repeat the example factor, but use it as inspiration.\n\n"
    )


def idea_user_enhance(context, hypothesis, previous_expr, eval_report) -> str:
    # idea_agent.py:73-78 — 원형은 hypothesis 자리에 idea dict가 그대로 들어와
    # f-string에서 repr로 문자열화된다 (parity mode 계약 — alphaagent.py:96)
    return (
        f"example factor:\n\n\"{context}\"\n\n"
        f"Previous hypothesis: \"{hypothesis}\"\n"
        f"Previous factor expression: \"{previous_expr}\"\n"
        f"Backtest report: \"{eval_report}\"\n\n"
    )


def factor_user(description) -> str:
    # factor_agent.py:43-44 — 원형은 description 자리에 idea dict가 그대로
    # 들어와 repr로 문자열화된다 (parity mode 계약 — alphaagent.py:76)
    return (f"Description: {description}\n"
            f"Generate the factor expression:")


def eval_user(perf_str: str, expr: str) -> str:
    # eval_agent.py:129-132
    return (
        f"Backtest result:\n{perf_str}\n\n"
        f"Factor expression: {expr}"
    )


# ---- seed 수식 37개 (alphaagent.py:20-58 verbatim) ----
SEED_EXPRESSIONS = [
    '($close-$open)/$open',
    '($high-$low)/$open',
    '($close-$open)/($high-$low+1e-12)',
    '($high-Greater($open, $close))/$open',
    '($high-Greater($open, $close))/($high-$low+1e-12)',
    '(Less($open, $close)-$low)/$open',
    '(Less($open, $close)-$low)/($high-$low+1e-12)',
    '(2*$close-$high-$low)/$open',
    '(2*$close-$high-$low)/($high-$low+1e-12)',
    '$open/$close',
    '$high/$close',
    '$low/$close',
    '$vwap/$close',
    'Ref($close, 5)/$close',
    'Mean($close, 60)/$close',
    'Std($close, 10)/$close',
    'Max($high, 20)/$close',
    'Min($low, 30)/$close',
    'Rank($close, 5)',
    '($close-Min($low, 10))/(Max($high, 10)-Min($low, 10)+1e-12)',
    'IdxMax($high, 20)/20',
    'IdxMin($low, 30)/30',
    '(IdxMax($high, 60)-IdxMin($low, 60))/60',
    'Corr($close, Log($volume+1), 5)',
    'Corr($close/Ref($close,1), Log($volume/Ref($volume, 1)+1), 10)',
    'Mean($close>Ref($close, 1), 20)',
    'Mean($close<Ref($close, 1), 30)',
    'Mean($close>Ref($close, 1), 60)-Mean($close<Ref($close, 1), 60)',
    'Sum(Greater($close-Ref($close, 1), 0), 5)/(Sum(Abs($close-Ref($close, 1)), 5)+1e-12)',
    'Sum(Greater(Ref($close, 1)-$close, 0), 10)/(Sum(Abs($close-Ref($close, 1)), 10)+1e-12)',
    '(Sum(Greater($close-Ref($close, 1), 0), 20)-Sum(Greater(Ref($close, 1)-$close, 0), 20))/(Sum(Abs($close-Ref($close, 1)), 20)+1e-12)',
    'Mean($volume, 30)/($volume+1e-12)',
    'Std($volume, 60)/($volume+1e-12)',
    'Std(Abs($close/Ref($close, 1)-1)*$volume, 5)/(Mean(Abs($close/Ref($close, 1)-1)*$volume, 5)+1e-12)',
    'Sum(Greater($volume-Ref($volume, 1), 0), 10)/(Sum(Abs($volume-Ref($volume, 1)), 10)+1e-12)',
    'Sum(Greater(Ref($volume, 1)-$volume, 0), 20)/(Sum(Abs($volume-Ref($volume, 1)), 20)+1e-12)',
    '(Sum(Greater($volume-Ref($volume, 1), 0), 60)-Sum(Greater(Ref($volume, 1)-$volume, 0), 60))/(Sum(Abs($volume-Ref($volume, 1)), 60)+1e-12)',
]
