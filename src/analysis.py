"""Métricas agregadas e testes estatísticos usados nas perguntas de pesquisa.

Todas as funções são puras e determinísticas (sementes fixas), de modo que
``python -m src.analysis`` regenera ``data/processed/metricas_agregadas.json``
bit a bit.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .etl import OUT_DEFAULT, load_processed

SEED = 2022
N_PERM = 20_000
Y = "vitimas_jan_abr"


# --------------------------------------------------------------------------- #
# Estatística descritiva
# --------------------------------------------------------------------------- #
def descritivas(s: pd.Series) -> dict:
    s = s.dropna().astype(float)
    q1, med, q3 = s.quantile([0.25, 0.5, 0.75])
    return {
        "n": int(s.size),
        "media": float(s.mean()),
        "desvio_padrao": float(s.std(ddof=1)),
        "coef_variacao": float(s.std(ddof=1) / s.mean()),
        "minimo": float(s.min()),
        "q1": float(q1),
        "mediana": float(med),
        "q3": float(q3),
        "maximo": float(s.max()),
        "iqr": float(q3 - q1),
        "mad": float(stats.median_abs_deviation(s)),
        "assimetria": float(stats.skew(s, bias=False)) if s.size > 2 else None,
    }


# --------------------------------------------------------------------------- #
# RQ1 – tendência e quebra estrutural
# --------------------------------------------------------------------------- #
def tendencia(df: pd.DataFrame, col: str = Y) -> dict:
    """Mann-Kendall (via τ de Kendall vs. tempo) e inclinação de Theil-Sen."""
    tau, p = stats.kendalltau(df["ano"], df[col])
    ts = stats.theilslopes(df[col], df["ano"], alpha=0.95)
    return {
        "kendall_tau": float(tau),
        "kendall_p": float(p),
        "theil_sen_inclinacao": float(ts.slope),
        "theil_sen_ic95": [float(ts.low_slope), float(ts.high_slope)],
        "theil_sen_intercepto": float(ts.intercept),
    }


def _sse_dois_segmentos(y: np.ndarray, k: int) -> float:
    a, b = y[:k], y[k:]
    return float(((a - a.mean()) ** 2).sum() + ((b - b.mean()) ** 2).sum())


def quebra_unica(df: pd.DataFrame, col: str = Y, min_seg: int = 3) -> dict:
    """Ponto de quebra único (níveis constantes por trecho) + teste de permutação.

    Escolhe o ponto que minimiza a soma dos quadrados dos resíduos (SSE) de dois
    segmentos de média constante. A significância vem de permutações da série
    (H0: sem estrutura temporal), comparando a redução relativa de SSE.
    Como o ponto é escolhido a partir dos dados, a permutação refaz a busca em
    cada réplica — isso evita o viés de "escolher o melhor corte e testá-lo".
    """
    y = df[col].to_numpy(float)
    anos = df["ano"].to_numpy()
    n = y.size
    ks = range(min_seg, n - min_seg + 1)
    sse_tot = float(((y - y.mean()) ** 2).sum())

    def melhor(v):
        return min((_sse_dois_segmentos(v, k), k) for k in ks)

    sse, k = melhor(y)
    ganho_obs = 1 - sse / sse_tot
    rng = np.random.default_rng(SEED)
    ganhos = np.empty(N_PERM)
    for i in range(N_PERM):
        v = rng.permutation(y)
        s, _ = melhor(v)
        ganhos[i] = 1 - s / float(((v - v.mean()) ** 2).sum())
    p = float((1 + (ganhos >= ganho_obs).sum()) / (1 + N_PERM))
    a, b = y[:k], y[k:]
    return {
        "ano_inicio_segmento2": int(anos[k]),
        "media_segmento1": float(a.mean()),
        "media_segmento2": float(b.mean()),
        "reducao_percentual_medias": float((b.mean() / a.mean() - 1) * 100),
        "r2_dois_niveis": float(ganho_obs),
        "p_permutacao": p,
        "n_permutacoes": N_PERM,
        "semente": SEED,
    }


# Regimes usados na narrativa (definidos APÓS a inspeção dos dados — exploratório)
REGIMES = [("2003–2010", 2003, 2010), ("2011–2018", 2011, 2018), ("2019–2022", 2019, 2022)]


def regimes(df: pd.DataFrame, col: str = Y) -> list[dict]:
    out = []
    for nome, a, b in REGIMES:
        s = df.loc[df["ano"].between(a, b), col]
        d = descritivas(s)
        d.update(regime=nome, inicio=a, fim=b)
        out.append(d)
    return out


def comparar_regimes(df: pd.DataFrame, col: str = Y) -> dict:
    """Mann-Whitney U entre pares de regimes (exploratório; ver limitações)."""
    g = {n: df.loc[df["ano"].between(a, b), col] for n, a, b in REGIMES}
    nomes = list(g)
    res = {}
    for i in range(len(nomes)):
        for j in range(i + 1, len(nomes)):
            u = stats.mannwhitneyu(g[nomes[i]], g[nomes[j]], alternative="two-sided")
            res[f"{nomes[i]} vs {nomes[j]}"] = {"U": float(u.statistic), "p": float(u.pvalue)}
    return res


# --------------------------------------------------------------------------- #
# RQ2 – contagem × taxa × população
# --------------------------------------------------------------------------- #
def contagem_vs_taxa(df: pd.DataFrame) -> dict:
    i, f = df.iloc[0], df.iloc[-1]
    n = len(df) - 1
    cagr = lambda a, b: float(((b / a) ** (1 / n) - 1) * 100)  # noqa: E731
    rho_ct = stats.spearmanr(df[Y], df["taxa_100mil_calc"])
    rho_pop = stats.spearmanr(df[Y], df["populacao"])
    # decomposição log: Δln(taxa) = Δln(vítimas) − Δln(população)
    dln = lambda c: float(np.log(f[c] / i[c]))  # noqa: E731
    return {
        "ano_inicial": int(i["ano"]),
        "ano_final": int(f["ano"]),
        "vitimas_inicial": int(i[Y]),
        "vitimas_final": int(f[Y]),
        "var_pct_vitimas": float((f[Y] / i[Y] - 1) * 100),
        "taxa_inicial": float(i["taxa_100mil_calc"]),
        "taxa_final": float(f["taxa_100mil_calc"]),
        "var_pct_taxa": float((f["taxa_100mil_calc"] / i["taxa_100mil_calc"] - 1) * 100),
        "populacao_inicial": float(i["populacao"]),
        "populacao_final": float(f["populacao"]),
        "var_pct_populacao": float((f["populacao"] / i["populacao"] - 1) * 100),
        "cagr_vitimas_pct": cagr(i[Y], f[Y]),
        "cagr_taxa_pct": cagr(i["taxa_100mil_calc"], f["taxa_100mil_calc"]),
        "cagr_populacao_pct": cagr(i["populacao"], f["populacao"]),
        "decomposicao_log": {
            "delta_ln_vitimas": dln(Y),
            "delta_ln_populacao": dln("populacao"),
            "delta_ln_taxa": dln("taxa_100mil_calc"),
            "parcela_populacao_pct": float(dln("populacao") / -dln("taxa_100mil_calc") * 100),
        },
        "spearman_vitimas_taxa": {"rho": float(rho_ct.statistic), "p": float(rho_ct.pvalue)},
        "spearman_vitimas_populacao": {"rho": float(rho_pop.statistic), "p": float(rho_pop.pvalue)},
        "max_dif_posicao_ranking": int(
            (df[Y].rank(method="min") - df["taxa_100mil_calc"].rank(method="min")).abs().max()
        ),
        "tendencia_taxa": tendencia(df, "taxa_100mil_calc"),
        "ano_pico_vitimas": int(df.loc[df[Y].idxmax(), "ano"]),
        "ano_pico_taxa": int(df.loc[df["taxa_100mil_calc"].idxmax(), "ano"]),
        "ano_vale_vitimas": int(df.loc[df[Y].idxmin(), "ano"]),
        "ano_vale_taxa": int(df.loc[df["taxa_100mil_calc"].idxmin(), "ano"]),
    }


# --------------------------------------------------------------------------- #
# RQ3 – volatilidade e variações atípicas
# --------------------------------------------------------------------------- #
def modified_z(x: pd.Series) -> pd.Series:
    """Escore z modificado (Iglewicz & Hoaglin): 0,6745·(x − mediana)/MAD."""
    mad = stats.median_abs_deviation(x.dropna())
    return 0.6745 * (x - x.median()) / mad


def poisson_z(df: pd.DataFrame) -> pd.DataFrame:
    """Compara cada variação anual com o ruído esperado de uma contagem de Poisson.

    Sob H0 (taxa constante entre dois anos), Var(n_t − n_{t−1}) = n_t + n_{t−1},
    logo z = (n_t − n_{t−1}) / √(n_t + n_{t−1}). O valor-p bicaudal recebe
    correção de Bonferroni (m = nº de comparações).
    """
    n = df.set_index("ano")[Y].astype(float)
    d = n.diff().dropna()
    z = d / np.sqrt(n + n.shift(1)).dropna()
    p = 2 * stats.norm.sf(z.abs())
    m = len(z)
    return pd.DataFrame({"z_poisson": z, "p_bonferroni": np.minimum(1.0, p * m)})


def variacoes_atipicas(df: pd.DataFrame) -> dict:
    v = df.set_index("ano")["dif_pct_calc"].dropna()
    pz = poisson_z(df)
    z = modified_z(v)
    q1, q3 = v.quantile([0.25, 0.75])
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    tab = pd.DataFrame({"var_pct": v, "z_mod": z, "tukey": (v < lo) | (v > hi), "z35": z.abs() > 3.5,
                        "z_poisson": pz["z_poisson"], "p_bonf": pz["p_bonferroni"]})
    return {
        "n_variacoes": int(v.size),
        "mediana_var_pct": float(v.median()),
        "mad_var_pct": float(stats.median_abs_deviation(v)),
        "cerca_tukey": [float(lo), float(hi)],
        "limiar_z_modificado": 3.5,
        "anos_tukey": [int(a) for a in tab.index[tab["tukey"]]],
        "anos_z_modificado": [int(a) for a in tab.index[tab["z35"]]],
        "maiores_quedas": [{"ano": int(a), "var_pct": float(x)} for a, x in v.nsmallest(3).items()],
        "maiores_altas": [{"ano": int(a), "var_pct": float(x)} for a, x in v.nlargest(3).items()],
        "anos_acima_ruido_poisson": [int(a) for a in tab.index[tab["p_bonf"] < 0.05]],
        "n_quedas": int((v < 0).sum()),
        "n_altas": int((v > 0).sum()),
        "n_estavel": int((v == 0).sum()),
        "tabela": [
            {"ano": int(a), "var_pct": float(r.var_pct), "z_mod": float(r.z_mod),
             "tukey": bool(r.tukey), "z35": bool(r.z35),
             "z_poisson": float(r.z_poisson), "p_bonf": float(r.p_bonf)}
            for a, r in tab.iterrows()
        ],
    }


def volatilidade_por_regime(df: pd.DataFrame) -> list[dict]:
    out = []
    for nome, a, b in REGIMES:
        s = df.loc[df["ano"].between(a, b), "dif_pct_calc"].dropna()
        out.append({
            "regime": nome,
            "n": int(s.size),
            "media_abs_var_pct": float(s.abs().mean()),
            "mediana_abs_var_pct": float(s.abs().median()),
            "desvio_padrao_var_pct": float(s.std(ddof=1)) if s.size > 1 else None,
        })
    return out


# --------------------------------------------------------------------------- #
# Consolidação
# --------------------------------------------------------------------------- #
def compute(df: pd.DataFrame | None = None) -> dict:
    df = load_processed() if df is None else df
    return {
        "serie": {
            "periodo": [int(df["ano"].min()), int(df["ano"].max())],
            "n_anos": int(len(df)),
            "total_acumulado": int(df[Y].sum()),
            "descritivas_vitimas": descritivas(df[Y]),
            "descritivas_taxa": descritivas(df["taxa_100mil_calc"]),
        },
        "rq1": {
            "tendencia_vitimas": tendencia(df),
            "quebra_unica": quebra_unica(df),
            "regimes": regimes(df),
            "mann_whitney": comparar_regimes(df),
        },
        "rq2": contagem_vs_taxa(df),
        "rq3": {
            "variacoes": variacoes_atipicas(df),
            "volatilidade_por_regime": volatilidade_por_regime(df),
        },
    }


def main() -> None:
    m = compute()
    p = OUT_DEFAULT / "metricas_agregadas.json"
    p.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK -> {p}")


if __name__ == "__main__":
    main()
