"""ETL da Tabela 2300 (DATA.RIO / ISP-RJ).

Lê a planilha ``.xls`` bruta, higieniza, tipa, valida e persiste em formatos
abertos. O arquivo bruto **nunca** é alterado: toda transformação é registrada
em ``data/processed/etl_log.json`` (rastreabilidade).

Uso::

    python -m src.etl                     # usa os caminhos padrão
    python -m src.etl --raw X.xls --out Y # caminhos explícitos
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

LOG = logging.getLogger("etl")

ROOT = Path(__file__).resolve().parents[1]
RAW_DEFAULT = ROOT / "data" / "raw" / "tabela_2300_data_rio.xls"
OUT_DEFAULT = ROOT / "data" / "processed"
SHEET = "T 2300"
MESES_QUADRIMESTRE = 4  # janeiro a abril
NA_TOKENS = {"..", "…", "-", "--", ""}  # ".." = "Não se aplica dado numérico" (nota da fonte)

# Mapeamento posicional: coluna da planilha -> nome normalizado (snake_case)
COLUNAS = {
    0: "ano",
    1: "vitimas_jan_abr",
    2: "dif_abs_publicada",
    3: "dif_pct_publicada",
    4: "populacao",
    5: "taxa_100mil_publicada",
    6: "media_mensal_publicada",
}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def sha256(path: Path) -> str:
    """Hash SHA-256 do arquivo (prova de integridade do dado bruto)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()


def _to_number(valor):
    """Converte célula em float; tokens de 'não se aplica' viram NaN."""
    if valor is None:
        return np.nan
    if isinstance(valor, str):
        txt = valor.strip()
        if txt in NA_TOKENS:
            return np.nan
        return float(txt.replace(",", "."))
    return float(valor)


# --------------------------------------------------------------------------- #
# Extração
# --------------------------------------------------------------------------- #
def read_sheet(raw: Path) -> pd.DataFrame:
    """Lê a aba bruta sem interpretar cabeçalho (``header=None``)."""
    return pd.read_excel(raw, sheet_name=SHEET, header=None, engine="calamine")


def extract_metadata(sheet: pd.DataFrame) -> dict:
    """Extrai título, fonte e notas de rodapé escritos na planilha."""
    textos = [str(v).strip() for v in sheet[0].tolist() if isinstance(v, str)]
    titulo = next((t for t in textos if t.startswith("Tabela")), "")
    fonte = next((t for t in textos if t.startswith("Fonte:")), "")
    notas = [t for t in textos if re.match(r"^\d - ", t)]
    return {"titulo": titulo, "fonte": fonte, "notas": notas}


def parse_table(sheet: pd.DataFrame) -> pd.DataFrame:
    """Isola as linhas de dados (primeira coluna = ano) e tipa as colunas.

    As linhas de dados são localizadas pelo conteúdo (um ano de 4 dígitos na
    primeira coluna), e não por posição fixa; assim o parser tolera linhas de
    cabeçalho/rodapé extras em futuras versões da planilha.
    """
    def eh_ano(v) -> bool:
        try:
            return 1900 <= int(float(v)) <= 2100 and float(v) == int(float(v))
        except (TypeError, ValueError):
            return False

    linhas = sheet[sheet[0].map(eh_ano)].copy()
    if linhas.empty:
        raise ValueError("Nenhuma linha de dados encontrada na planilha.")
    linhas = linhas.iloc[:, : len(COLUNAS)]
    linhas.columns = list(COLUNAS.values())

    df = linhas.map(_to_number).reset_index(drop=True)
    df["ano"] = df["ano"].astype("int16")
    df["vitimas_jan_abr"] = df["vitimas_jan_abr"].astype("int32")
    # inteiros anuláveis: a 1ª diferença (2003) é ".." na fonte
    df["dif_abs_publicada"] = df["dif_abs_publicada"].astype("Int32")
    for c in ("dif_pct_publicada", "populacao", "taxa_100mil_publicada", "media_mensal_publicada"):
        df[c] = df[c].astype("float64")
    return df


# --------------------------------------------------------------------------- #
# Transformação: métricas derivadas (recalculadas, nunca sobrescrevem a fonte)
# --------------------------------------------------------------------------- #
def add_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Recalcula as métricas a partir das colunas primárias.

    Mantém as colunas ``*_publicada`` intactas e cria ``*_calc`` para permitir
    auditoria (ver :func:`validate`).
    """
    out = df.sort_values("ano").reset_index(drop=True).copy()
    out["dif_abs_calc"] = out["vitimas_jan_abr"].diff().astype("Int32")
    out["dif_pct_calc"] = out["vitimas_jan_abr"].pct_change() * 100
    out["taxa_100mil_calc"] = out["vitimas_jan_abr"] / out["populacao"] * 1e5
    out["media_mensal_calc"] = out["vitimas_jan_abr"] / MESES_QUADRIMESTRE
    base = out.loc[0]
    out["indice_vitimas_base100"] = out["vitimas_jan_abr"] / base["vitimas_jan_abr"] * 100
    out["indice_taxa_base100"] = out["taxa_100mil_calc"] / base["taxa_100mil_calc"] * 100
    out["indice_populacao_base100"] = out["populacao"] / base["populacao"] * 100
    return out


# --------------------------------------------------------------------------- #
# Validação
# --------------------------------------------------------------------------- #
def validate(df: pd.DataFrame) -> dict:
    """Checagens de integridade; levanta ``AssertionError`` em violações graves.

    Retorna um relatório (dict) com os desvios máximos entre valores publicados
    e recalculados.
    """
    assert df["ano"].is_unique, "anos duplicados"
    assert (df["ano"].diff().dropna() == 1).all(), "série anual não é contígua"
    assert (df["vitimas_jan_abr"] >= 0).all(), "contagem negativa"
    assert df["populacao"].notna().all() and (df["populacao"] > 0).all(), "população inválida"
    assert df[["vitimas_jan_abr", "populacao"]].notna().all().all(), "nulos em colunas primárias"

    def desvio(pub, calc):
        d = (df[pub].astype("float64") - df[calc].astype("float64")).abs()
        return float(d.max(skipna=True))

    rel = {
        "max_desvio_dif_abs": desvio("dif_abs_publicada", "dif_abs_calc"),
        "max_desvio_dif_pct": desvio("dif_pct_publicada", "dif_pct_calc"),
        "max_desvio_taxa_100mil": desvio("taxa_100mil_publicada", "taxa_100mil_calc"),
        "max_desvio_media_mensal": desvio("media_mensal_publicada", "media_mensal_calc"),
        "nulos_por_coluna": {k: int(v) for k, v in df.isna().sum().items() if v},
    }
    assert rel["max_desvio_dif_abs"] == 0, "diferença absoluta publicada ≠ recalculada"
    assert rel["max_desvio_dif_pct"] < 1e-6, "diferença % publicada ≠ recalculada"
    assert rel["max_desvio_taxa_100mil"] < 1e-6, "taxa publicada ≠ recalculada"
    assert rel["max_desvio_media_mensal"] < 1e-9, "média mensal publicada ≠ recalculada"
    return rel


# --------------------------------------------------------------------------- #
# Persistência
# --------------------------------------------------------------------------- #
def _write_csv_gz(df: pd.DataFrame, path: Path) -> None:
    """CSV comprimido **determinístico** (mtime=0 ⇒ mesmo hash a cada execução)."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, filename="") as gz:
        gz.write(df.to_csv(index=False).encode("utf-8"))
    path.write_bytes(buf.getvalue())


def save(df: pd.DataFrame, meta: dict, rel: dict, raw: Path, out_dir: Path, linhas_lidas: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_gz = out_dir / "autos_resistencia_rio_jan_abr.csv.gz"
    js = out_dir / "autos_resistencia_rio_jan_abr.json"
    _write_csv_gz(df, csv_gz)
    registros = json.loads(df.to_json(orient="records", force_ascii=False))
    js.write_text(json.dumps(registros, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    log = {
        "script": "src/etl.py",
        "arquivo_bruto": str(raw.relative_to(ROOT)) if raw.is_relative_to(ROOT) else raw.name,
        "sha256_bruto": sha256(raw),
        "aba": SHEET,
        "metadados_fonte": meta,
        "linhas_lidas_na_aba": int(linhas_lidas),
        "linhas_de_dados": int(len(df)),
        "periodo": [int(df["ano"].min()), int(df["ano"].max())],
        "regras_aplicadas": [
            "Linhas de dados identificadas por ano (1900-2100) na 1ª coluna; cabeçalhos e notas descartados da tabela (mas preservados em metadados_fonte).",
            "Token '..' (Não se aplica dado numérico) convertido em NaN/<NA>; nenhuma imputação.",
            "Colunas renomeadas para snake_case; sufixo '_publicada' = valor da fonte.",
            "Tipos: ano=int16, vitimas=int32, dif_abs=Int32 (anulável), demais=float64.",
            "Métricas recalculadas (*_calc) e comparadas às publicadas; divergências acima da tolerância interrompem o pipeline.",
            "Índices base 100 (2003=100) criados para comparar escalas distintas num mesmo eixo.",
            "Nenhuma linha foi removida ou imputada.",
        ],
        "validacao": rel,
        "saidas": {
            csv_gz.name: sha256(csv_gz),
            js.name: sha256(js),
        },
    }
    (out_dir / "etl_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return log


# --------------------------------------------------------------------------- #
# Orquestração
# --------------------------------------------------------------------------- #
def load_processed(out_dir: Path = OUT_DEFAULT) -> pd.DataFrame:
    """Carrega o dataset tratado (uso no notebook e nos demais módulos)."""
    return pd.read_csv(out_dir / "autos_resistencia_rio_jan_abr.csv.gz")


def run(raw: Path = RAW_DEFAULT, out_dir: Path = OUT_DEFAULT) -> pd.DataFrame:
    LOG.info("Lendo %s", raw)
    sheet = read_sheet(raw)
    meta = extract_metadata(sheet)
    df = add_derived_metrics(parse_table(sheet))
    rel = validate(df)
    save(df, meta, rel, raw, out_dir, len(sheet))
    LOG.info("OK: %d linhas -> %s", len(df), out_dir)
    return df


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raw", type=Path, default=RAW_DEFAULT)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args.raw, args.out)


if __name__ == "__main__":
    main()
