"""Figuras estáticas (PNG, 220 dpi) do artigo e do notebook.

Paleta categórica de referência (slots 1-3, validada para todos os pares):
azul #2a78d6, laranja #eb6834, água #1baf7a. Texto em tons neutros;
grade recessiva; um único eixo y por gráfico (sem eixo duplo).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .analysis import REGIMES, Y, compute  # noqa: E402
from .etl import load_processed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#85847f", "#e6e5e1", "#fcfcfb"

EVENTOS = [  # (x, rótulo, altura) — marcos de contexto (não implicam causalidade)
    (2008.9, "1ª UPP (2008)", 6),
    (2015.8, "Res. Conj. 2/2015", 30),
    (2018.5, "Interv. federal (2018)", 6),
    (2020.4, "ADPF 635 (jun/2020)", 30),
]


def _style() -> None:
    fams = {f.name for f in fm.fontManager.ttflist}
    fam = next((f for f in ("Inter", "Source Sans 3", "DejaVu Sans") if f in fams), "sans-serif")
    plt.rcParams.update({
        "font.family": fam, "font.size": 10.5, "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
        "axes.spines.top": False, "axes.spines.right": False, "axes.titlelocation": "left",
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlecolor": INK,
        "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
        "legend.frameon": False, "savefig.facecolor": SURFACE, "axes.axisbelow": True,
    })


def _br(x, _=None, casas=0) -> str:
    s = f"{x:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _save(fig, name: str, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    p = out / name
    fig.savefig(p, dpi=220, bbox_inches="tight", metadata={"Software": "matplotlib", "Creation Time": None})
    plt.close(fig)
    return p


# --------------------------------------------------------------------------- #
def fig_serie(df, m):
    """Fig. 1 — total de vítimas, médias por regime, quebra e marcos."""
    fig, ax = plt.subplots(figsize=(9.2, 5.1))
    ax.plot(df["ano"], df[Y], color=BLUE, lw=2, marker="o", ms=6, mec=SURFACE, mew=1.5, zorder=3)
    for nome, a, b in REGIMES:
        mu = df.loc[df["ano"].between(a, b), Y].mean()
        ax.hlines(mu, a - 0.4, b + 0.4, color=ORANGE, lw=2, ls=(0, (5, 3)), zorder=2)
        xl, yl, va = {0: ((a + b) / 2, mu - 9, "top"), 1: (2012.1, mu + 9, "bottom"), 2: (2019.9, mu - 9, "top")}[REGIMES.index((nome, a, b))]
        ax.text(xl, yl, f"média: {_br(mu, casas=0)}", color=INK2, ha="center", va=va, fontsize=9,
                bbox=dict(fc=SURFACE, ec="none", pad=1.5, alpha=0.9), zorder=5)
    k = m["rq1"]["quebra_unica"]["ano_inicio_segmento2"]
    ax.axvline(k - 0.5, color=MUTED, lw=1, ls=":")
    ax.text(k - 0.4, 352, f"quebra ótima: {k}\n(p = {_br(m['rq1']['quebra_unica']['p_permutacao'], casas=3)})",
            color=INK2, fontsize=8.5, va="top")
    for a, rot in [(2008, "pico"), (2013, "vale")]:
        v = int(df.loc[df["ano"] == a, Y].iloc[0])
        ax.annotate(f"{v} ({rot})", (a, v), xytext=(0, 9 if rot == "pico" else -16),
                    textcoords="offset points", ha="center", fontsize=9, color=INK)
    for x, lab, h in EVENTOS:
        ax.plot([x, x], [0, h], color=INK2, lw=1)
        ax.text(x, h + 2, lab, fontsize=7.6, color=INK2, ha="center", va="bottom",
                bbox=dict(fc=SURFACE, ec="none", pad=1, alpha=0.9))
    ax.set_ylim(0, 360)
    ax.set_xlim(2002.4, 2022.6)
    ax.set_xticks(range(2003, 2023, 2))
    ax.set_xlabel("Ano (1º quadrimestre: janeiro–abril)")
    ax.set_ylabel("Vítimas (nº absoluto)")
    ax.set_title("Vítimas de intervenção policial — Município do Rio, jan–abr, 2003–2022")
    ax.legend(handles=[Line2D([], [], color=BLUE, lw=2, marker="o", label="Vítimas (jan–abr)"),
                       Line2D([], [], color=ORANGE, lw=2, ls=(0, (5, 3)), label="Média do regime")],
              loc="upper right", bbox_to_anchor=(1, 1.0), fontsize=9)
    fig.text(0.01, -0.02, "Fonte: ISP-RJ / DATA.RIO, Tabela 2300. Marcos de contexto não implicam causalidade.",
             fontsize=8, color=MUTED)
    return fig


def fig_indices(df, m):
    """Fig. 2 — vítimas, taxa e população num mesmo eixo (índice 2003 = 100)."""
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    series = [("indice_vitimas_base100", BLUE, "Vítimas"), ("indice_taxa_base100", ORANGE, "Taxa por 100 mil hab."),
              ("indice_populacao_base100", AQUA, "População")]
    ax.axhline(100, color=MUTED, lw=1)
    for col, cor, nome in series:
        ax.plot(df["ano"], df[col], color=cor, lw=2, marker="o", ms=4.5, mec=SURFACE, mew=1, label=nome)
        y_end = df[col].iloc[-1]
        dy = {"indice_vitimas_base100": 5, "indice_taxa_base100": -5}.get(col, 0)
        ax.text(2022.35, y_end + dy, f"{nome} ({y_end:.0f})", color=INK, fontsize=8.8, va="center")
    r = m["rq2"]
    ax.set_xlim(2002.6, 2026.2)
    ax.set_xticks(range(2003, 2023, 2))
    ax.set_ylim(0, 125)
    ax.set_xlabel("Ano")
    ax.set_ylabel("Índice (2003 = 100)")
    ax.set_title("Contagem × taxa × população: a normalização acentua a queda")
    ax.legend(loc="lower left", ncol=3, fontsize=9)
    fig.text(0.01, -0.02,
             f"Variação 2003→2022: vítimas {_br(r['var_pct_vitimas'], casas=1)}% · taxa {_br(r['var_pct_taxa'], casas=1)}% · população +{_br(r['var_pct_populacao'], casas=1)}%.",
             fontsize=8.5, color=INK2)
    return fig


def fig_variacoes(df, m):
    """Fig. 3 — variação % anual, destacando as acima do ruído de Poisson."""
    tab = m["rq3"]["variacoes"]["tabela"]
    anos = [t["ano"] for t in tab]
    v = np.array([t["var_pct"] for t in tab])
    sig = np.array([t["p_bonf"] < 0.05 for t in tab])
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.bar(np.array(anos)[~sig], v[~sig], color="#9ec5f4", width=0.68, label="Compatível com ruído de Poisson")
    ax.bar(np.array(anos)[sig], v[sig], color=BLUE, width=0.68, label="Acima do ruído (Bonferroni, p < 0,05)")
    ax.axhline(0, color=INK2, lw=1)
    for a, x, s in zip(anos, v, sig):
        if s:
            ax.text(a, x + (4 if x > 0 else -4), f"{x:+.0f}%".replace(".", ","), ha="center",
                    va="bottom" if x > 0 else "top", fontsize=8.5, color=INK)
    ax.set_xticks(anos)
    ax.set_xticklabels([str(a)[2:] for a in anos])
    ax.set_xlabel("Ano (variação em relação ao mesmo quadrimestre do ano anterior; '03–'22)")
    ax.set_ylabel("Variação anual (%)")
    ax.set_ylim(-62, 78)
    ax.set_title("Variações interanuais: quais excedem o acaso?")
    ax.legend(loc="upper left", fontsize=9)
    return fig


def fig_regimes(df, m):
    """Fig. 4 — distribuição por regime (pontos + mediana), sem sobreposição de rótulos."""
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    rng = np.random.default_rng(7)
    for i, (nome, a, b) in enumerate(REGIMES):
        s = df[df["ano"].between(a, b)]
        x = i + rng.uniform(-0.08, 0.08, len(s))
        ax.scatter(x, s[Y], s=46, color=[BLUE, AQUA, ORANGE][i], edgecolor=SURFACE, linewidth=1, zorder=3)
        ax.hlines(s[Y].median(), i - 0.28, i + 0.28, color=INK, lw=2, zorder=4)
        ax.text(i + 0.32, s[Y].median(), f"mediana {_br(s[Y].median())}", va="center", fontsize=8.8, color=INK2)
        for alvo, va_ in ((s[Y].max(), "bottom"), (s[Y].min(), "top")):
            anos = "/".join(str(int(a))[-2:] if j else str(int(a)) for j, a in enumerate(s.loc[s[Y] == alvo, "ano"]))
            ax.text(i - 0.12, alvo + (4 if va_ == "bottom" else -4), anos, ha="right", va=va_, fontsize=8.2, color=INK2)
    ax.set_xticks(range(3))
    ax.set_xticklabels([f"{n}\n(n = {b - a + 1})" for n, a, b in REGIMES])
    ax.set_xlim(-0.6, 2.9)
    ax.set_ylim(0, 360)
    ax.set_ylabel("Vítimas (jan–abr)")
    ax.set_title("Distribuição por regime: 2019–2021 retorna ao patamar de 2003–2010")
    return fig


FIGURAS = {
    "fig1_serie_temporal.png": fig_serie,
    "fig2_indices_taxa_populacao.png": fig_indices,
    "fig3_variacoes_interanuais.png": fig_variacoes,
    "fig4_distribuicao_regimes.png": fig_regimes,
}


def setup() -> None:
    """Aplica o tema (usar no notebook antes de chamar ``fig_*``)."""
    _style()


def build_all(out: Path = ASSETS) -> list[Path]:
    _style()
    df = load_processed()
    m = compute(df)
    return [_save(f(df, m), nome, out) for nome, f in FIGURAS.items()]


if __name__ == "__main__":
    for p in build_all():
        print("OK ->", p)
