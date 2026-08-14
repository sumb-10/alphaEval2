# qlib_backtester/backtester.py

import pandas as pd
import numpy as np
from qlib.data import D
from typing import List, Tuple, Optional

class FactorBacktester:
    """
    简单的因子回测器

    Parameters
    ----------
    factor_expr : str
        因子表达式，可直接传给 Qlib 的 D.features，例如 "Add(Mean($close, 5), 2)"
    start_date : str
        回测开始日期，格式 "YYYY-MM-DD"
    end_date : str
        回测结束日期，格式 "YYYY-MM-DD"
    instruments : Optional[List[str]]
        标的列表，默认自动取 CSI300 成分股
    freq : str
        数据频率，默认为 "day"
    """

    def __init__(
        self,
        factor_expr: str,
        start_date: str,
        end_date: str,
        instruments: Optional[List[str]] = None,
        freq: str = "day",
        long_threshold: float = 0.2,
        short_threshold: float = 0.2,
    ):
        self.factor_expr = factor_expr
        self.start_date = start_date
        self.end_date = end_date
        self.freq = freq
        self.long_threshold = (
            long_threshold / 100 if long_threshold > 1 else long_threshold
        )
        self.short_threshold = (
            short_threshold / 100 if short_threshold > 1 else short_threshold
        )
        # 如果用户未指定标的，默认取 CSI300
        self.instruments = (
            instruments
            if instruments is not None
            else D.list_instruments(
                market="csi300", start_time=start_date, end_time=end_date
            )
        )

        self.factor_data: pd.DataFrame = pd.DataFrame()
        self.label_data: pd.DataFrame = pd.DataFrame()
        self.ic_series: pd.Series = pd.Series(dtype=float)
        self.rank_ic_series: pd.Series = pd.Series(dtype=float)
        self.ic: float = float("nan")
        self.rank_ic: float = float("nan")
        self.pnl: pd.DataFrame = pd.DataFrame()
        
    def load_data(self) -> None:
        """从 Qlib 上拉取因子值和收益率标签"""
        # 因子值
        self.factor_data = D.features(
            instruments=self.instruments,
            fields=[self.factor_expr],
            start_time=self.start_date,
            end_time=self.end_date,
            freq=self.freq,
        )
        print(f"Loaded factor data for {len(self.factor_data)} records.")
        self.label_data = D.features(
            instruments=self.instruments,
            fields=["Ref($close, -1)/$close - 1"],
            start_time=self.start_date,
            end_time=self.end_date,
            freq=self.freq,
        )
        self.data = self.factor_data.join(self.label_data, how="inner").dropna()
        self.data.columns = ["factor", "label"]

    def calculate_ic(self) -> None:
        """ 计算每日 IC"""
        self.ic_series = self.data.groupby(level="datetime").apply(
            lambda x: x["factor"].corr(x["label"])
        )
        self.ic = self.ic_series.mean()
        
    def calculate_rank_ic(self) -> None:
        """ 计算每日 Rank-IC"""
        self.rank_ic_series = self.data.groupby(level="datetime").apply(
            lambda x: x["factor"].rank().corr(x["label"].rank())
        )
        self.rank_ic = self.rank_ic_series.mean()

    def calculate_pnl(self) -> None:
        """ 计算每日 PnL 和换手率"""
        records = []
        prev_longs: Optional[set] = None
        prev_shorts: Optional[set] = None

        for date, group in self.data.groupby(level="datetime"):
            f = group["factor"]
            l = group["label"]

            # 多头 / 空头筛选
            long_cut = f.quantile(1 - 0.2)
            short_cut = f.quantile(0.2)

            longs = set(f[f >= long_cut].index.get_level_values("instrument"))
            shorts = set(f[f <= short_cut].index.get_level_values("instrument"))

            long_ret = l[f >= long_cut].mean()
            short_ret = -l[f <= short_cut].mean()
            pnl = (long_ret + short_ret) / 2
            market_mean = l.mean()

            if prev_longs is None:
                turnover = float("nan")
            else:
                long_out = prev_longs - longs
                long_in = longs - prev_longs
                short_out = prev_shorts - shorts
                short_in = shorts - prev_shorts
                trades = len(long_out) + len(long_in) + len(short_out) + len(short_in)
                denom = len(prev_longs) + len(prev_shorts)
                turnover = trades / denom if denom > 0 else float("nan")
            cost = turnover * 0.0015 if turnover else 0 # 假设每次交易成本为 0.15%
            pnl = pnl - cost
                
            records.append((date, pnl, turnover, market_mean))
            prev_longs, prev_shorts = longs, shorts

        pnl_df = pd.DataFrame(
            records, columns=["datetime", "pnl", "turnover", "market_mean"]
        ).set_index("datetime")
        self.pnl =  pnl_df.sort_index()
        
    def calculate_performance(self) -> pd.DataFrame:
        """
        按年（及总览）计算业绩指标：
          - AnnRet    年化收益率
          - AnnTurn   年化换手率
          - Sharpe    年化夏普比率
          - IC        日度 IC 均值
          - RankIC    日度 Rank-IC 均值
          - MaxDD     最大回撤
          - Fitness   Sharpe * IC

        Returns
        perf_df: DataFrame
          index=年份(或'total')，columns 如上
        """
        # 确保中间数据已准备
        if self.pnl.empty:
            self.calculate_pnl()

        if self.ic_series.empty:
            self.calculate_ic()
        
        if self.rank_ic_series.empty:
            self.calculate_rank_ic()

        results = []
        # 年度 & 全样本两轮
        def agg_period(pnl_s, to_s, ic_s, ric_s, name):
            n = len(pnl_s)
            # 年化收益 ?或取均值*252
            cum_ret = pnl_s.add(1).prod() - 1
            ann_ret = (1 + cum_ret) ** (252 / n) - 1 if n > 0 else np.nan
            # 年化换手
            ann_turn = round(to_s.mean(), 2)
            # 夏普
            mu, sigma = pnl_s.mean(), pnl_s.std(ddof=1)
            sharpe = mu / sigma * np.sqrt(252) if sigma and n > 1 else np.nan
            sharpe = round(sharpe, 2)
            # IC / RankIC
            ic_m = round(ic_s.mean(), 3)
            ric_m = round(ric_s.mean(), 3)
            # MaxDrawdown
            cum = pnl_s.add(1).cumprod()
            dd = (cum - cum.cummax()) / cum.cummax()
            max_dd = dd.min()
            # Fitness
            fitness = round(sharpe * (abs(ann_ret / ann_turn)) ** 0.5, 2) if ann_turn else np.nan
            ann_ret = ann_ret

            return {
                "period": name,
                "AnnRet": ann_ret,
                "AnnTurn": ann_turn,
                "Sharpe": sharpe,
                "IC": ic_m,
                "RankIC": ric_m,
                "MaxDD": max_dd,
                "Fitness": fitness,
            }

        # 按年分组
        pnl_s = self.pnl["pnl"]
        to_s = self.pnl["turnover"]
        for year, idx in pnl_s.groupby(pnl_s.index.year):
            mask = pnl_s.index.year == year
            results.append(
                agg_period(
                    pnl_s[mask],
                    to_s[mask],
                    self.ic_series[mask],
                    self.rank_ic_series[mask],
                    str(year),
                )
            )
        # 全样本
        results.append(
            agg_period(pnl_s, to_s, self.ic_series, self.rank_ic_series, "total")
        )

        perf_df = pd.DataFrame(results).set_index("period")
        return perf_df

    def run(self) -> pd.DataFrame:
        """
        一键跑完整流程，返回 performance summary
        """
        print(f"Loading data for factor: {self.factor_expr}.")
        self.load_data()
        print("Calculating PnL.")
        self.calculate_pnl()
        res = self.calculate_performance()
        print("Performance Summary:")
        return res 