"""Gera ``docs/index.html`` (artigo) a partir de um template Jinja2.

Todos os números do texto vêm de ``data/processed/metricas_agregadas.json`` e
os trechos de código são extraídos do código-fonte real (``inspect``): artigo,
notebook e pipeline não podem divergir.

    python -m src.build_article
"""
from __future__ import annotations

import inspect
import json
import re
import shutil
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import analysis, etl
from .etl import ROOT, load_processed

DOCS = ROOT / "docs"
TEMPLATES = ROOT / "src" / "templates"
META = ROOT / "src" / "project_meta.json"

EVENTOS = [
    {"x": 2008.9, "rotulo": "1ª UPP", "texto": "Instalação da primeira Unidade de Polícia Pacificadora (Santa Marta), 2008."},
    {"x": 2015.8, "rotulo": "Res. Conjunta 2/2015", "texto": "Resolução Conjunta nº 2, de 13/10/2015: substitui “auto de resistência” por “oposição à intervenção policial”."},
    {"x": 2018.5, "rotulo": "Interv. federal", "texto": "Intervenção federal na segurança pública do RJ (Decreto 9.288, de 16/02/2018; até 31/12/2018)."},
    {"x": 2020.4, "rotulo": "ADPF 635", "texto": "Liminar na ADPF 635 (jun/2020) restringe operações policiais em favelas durante a pandemia."},
]


def br(x, casas: int = 1, sinal: bool = False) -> str:
    """Formata número no padrão pt-BR (vírgula decimal, ponto de milhar)."""
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    s = f"{x:+,.{casas}f}" if sinal else f"{x:,.{casas}f}"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return s.replace("-", "−") if sinal or x < 0 else s


def pv(p: float) -> str:
    """Formata valor-p."""
    if p < 0.001:
        return "< 0,001"
    return br(p, 3)


def n_palavras(txt: str) -> int:
    return len(re.findall(r"\w+(?:[-’']\w+)*", txt, flags=re.UNICODE))


def _fonte(fn) -> str:
    return inspect.getsource(fn).rstrip()


def contexto() -> dict:
    meta = json.loads(META.read_text(encoding="utf-8"))
    df = load_processed()
    m = json.loads((etl.OUT_DEFAULT / "metricas_agregadas.json").read_text(encoding="utf-8"))
    log = json.loads((etl.OUT_DEFAULT / "etl_log.json").read_text(encoding="utf-8"))
    pz = {t["ano"]: t for t in m["rq3"]["variacoes"]["tabela"]}

    registros = []
    for _, r in df.iterrows():
        a = int(r["ano"])
        t = pz.get(a)
        registros.append({
            "ano": a,
            "vitimas": int(r["vitimas_jan_abr"]),
            "taxa": round(float(r["taxa_100mil_calc"]), 4),
            "media_mensal": float(r["media_mensal_calc"]),
            "populacao": round(float(r["populacao"])),
            "var_pct": None if t is None else round(t["var_pct"], 3),
            "z_poisson": None if t is None else round(t["z_poisson"], 3),
            "p_bonf": None if t is None else round(t["p_bonf"], 5),
            "acima_ruido": bool(t and t["p_bonf"] < 0.05),
            "idx_vitimas": round(float(r["indice_vitimas_base100"]), 3),
            "idx_taxa": round(float(r["indice_taxa_base100"]), 3),
            "idx_pop": round(float(r["indice_populacao_base100"]), 3),
        })
    js_data = {
        "registros": registros,
        "regimes": [{"nome": n, "a": a, "b": b} for n, a, b in analysis.REGIMES],
        "eventos": EVENTOS,
        "quebra": m["rq1"]["quebra_unica"]["ano_inicio_segmento2"],
    }
    snippets = {
        "parse_table": _fonte(etl.parse_table),
        "derived": _fonte(etl.add_derived_metrics),
        "validate": _fonte(etl.validate),
        "poisson": _fonte(analysis.poisson_z),
        "quebra": _fonte(analysis.quebra_unica),
    }
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "Vítimas de intervenção policial no Município do Rio de Janeiro, 1º quadrimestre, 2003–2022 (dados tratados)",
        "description": "Série anual (20 observações) do total de vítimas de oposição à intervenção policial no 1º quadrimestre, "
                       "população e taxa por 100 mil habitantes, tratada a partir da Tabela 2300 do DATA.RIO (fonte: ISP-RJ).",
        "url": meta["pages_url"],
        "keywords": ["segurança pública", "letalidade policial", "Rio de Janeiro", "dados abertos", "FAIR"],
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "isAccessibleForFree": True,
        "inLanguage": "pt-BR",
        "temporalCoverage": "2003/2022",
        "spatialCoverage": "Município do Rio de Janeiro, Brasil",
        "creator": [{"@type": "Person", "name": a} for a in meta["autores"]],
        "isBasedOn": "http://www.ispdados.rj.gov.br/",
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv",
                          "contentUrl": meta["pages_url"] + "assets/dados_tratados.csv"}],
    }
    return {
        "jsonld": json.dumps(jsonld, ensure_ascii=False, indent=1).replace("</", "<\\/"),
        "meta": meta, "m": m, "log": log, "df": df, "registros": registros,
        "js_data": json.dumps(js_data, ensure_ascii=False, separators=(",", ":")),
        "snippets": snippets, "eventos": EVENTOS,
        "regimes": {r["regime"]: r for r in m["rq1"]["regimes"]},
        "vol": {v["regime"]: v for v in m["rq3"]["volatilidade_por_regime"]},
    }


def render(out: Path = DOCS / "index.html") -> dict:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.globals.update(br=br, pv=pv)
    ctx = contexto()
    tpl = env.get_template("article.html.j2")
    html = tpl.render(**ctx)

    # verificações editoriais (falham o build se violadas)
    resumos = re.findall(r'<p class="abstract-text" lang="(\w\w)">(.*?)</p>', html, flags=re.S)
    contagens = {}
    for lang, txt in resumos:
        limpo = re.sub(r"<[^>]+>", "", txt)
        contagens[lang] = n_palavras(limpo)
        assert 150 <= contagens[lang] <= 250, f"Resumo '{lang}' tem {contagens[lang]} palavras (exigido: 150–250)"
    assert set(contagens) == {"pt", "en"}, "faltam resumos pt/en"
    kws = re.findall(r'<ul class="keywords" lang="(\w\w)">(.*?)</ul>', html, flags=re.S)
    for lang, ul in kws:
        n = len(re.findall(r"<li>", ul))
        assert 4 <= n <= 6, f"palavras-chave '{lang}': {n}"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    # dado tratado em CSV simples para download direto pela página
    pd.read_csv(etl.OUT_DEFAULT / "autos_resistencia_rio_jan_abr.csv.gz").to_csv(
        DOCS / "assets" / "dados_tratados.csv", index=False)
    shutil.copyfile(ROOT / "data" / "data_dictionary.md", DOCS / "assets" / "data_dictionary.md")
    return {"palavras_resumo": contagens, "bytes": len(html.encode("utf-8"))}


if __name__ == "__main__":
    info = render()
    print("OK -> docs/index.html", info)
