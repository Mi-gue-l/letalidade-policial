"""Homologação final do repositório (FAIR + reprodutibilidade).

    python -m src.check_repo          # falha (exit 1) se algo obrigatório faltar

* Estrutura de diretórios e arquivos exigidos.
* Integridade: SHA-256 do bruto e das saídas contra ``etl_log.json``.
* Requirements pinados (``==``).
* Dicionário cobre todas as colunas do dado tratado.
* Artigo: seções obrigatórias, resumo, referências a figuras existentes.
* Avisos para campos ainda marcados com ``[PREENCHER``.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

from .etl import OUT_DEFAULT, RAW_DEFAULT, ROOT, load_processed, sha256

OBRIGATORIOS = [
    "README.md", "LICENSE", "LICENSE-DATA.md", "requirements.txt", ".gitignore",
    "data/raw/tabela_2300_data_rio.xls", "data/data_dictionary.md",
    "data/processed/autos_resistencia_rio_jan_abr.csv.gz", "data/processed/etl_log.json",
    "notebooks/analise_exploratoria.ipynb", "src/__init__.py", "src/etl.py",
    "docs/index.html", "docs/assets",
]
SECOES = ["Resumo", "Abstract", "1 Introdução", "2 Metodologia", "3 Resultados", "4 Conclusão",
          "5 Disponibilidade dos dados", "6 Referências"]


def main() -> int:
    erros, avisos = [], []

    for rel in OBRIGATORIOS:
        if not (ROOT / rel).exists():
            erros.append(f"ausente: {rel}")

    log = json.loads((OUT_DEFAULT / "etl_log.json").read_text(encoding="utf-8"))
    if sha256(RAW_DEFAULT) != log["sha256_bruto"]:
        erros.append("hash do arquivo bruto difere do etl_log.json")
    for nome, h in log["saidas"].items():
        if sha256(OUT_DEFAULT / nome) != h:
            erros.append(f"hash divergente: {nome}")

    reqs = [l.strip() for l in (ROOT / "requirements.txt").read_text().splitlines()
            if l.strip() and not l.startswith("#")]
    for l in reqs:
        if "==" not in l:
            erros.append(f"requirements não pinado: {l}")

    dic = (ROOT / "data" / "data_dictionary.md").read_text(encoding="utf-8")
    for col in load_processed().columns:
        if f"`{col}`" not in dic:
            erros.append(f"coluna sem entrada no dicionário: {col}")

    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    for s in SECOES:
        if s not in html:
            erros.append(f"artigo sem seção: {s}")
    for img in re.findall(r'src="(assets/[^"]+)"', html):
        if not (ROOT / "docs" / img).exists():
            erros.append(f"figura referenciada não existe: {img}")
    if 'name="viewport"' not in html:
        erros.append("artigo sem meta viewport (responsividade)")
    if re.search(r'(src|href)="https?://[^"]*\.(js|css)"', html):
        avisos.append("artigo depende de script/CSS externo")

    nb = json.loads((ROOT / "notebooks" / "analise_exploratoria.ipynb").read_text(encoding="utf-8"))
    sem_saida = [i for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code" and not c["outputs"]
                 and c["source"] and not "".join(c["source"]).strip().startswith("import")]
    if sem_saida:
        avisos.append(f"células de código sem saída executada: {sem_saida}")

    pend = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
            if p.is_file() and p.suffix in {".md", ".html", ".json", ".cff", ""} and ".git" not in p.parts
            and "__pycache__" not in p.parts and p.name != "check_repo.py"
            and "[PREENCHER" in p.read_text(encoding="utf-8", errors="ignore")]
    if pend:
        avisos.append("campos [PREENCHER] pendentes em: " + ", ".join(sorted(pend)))

    for a in avisos:
        print("AVISO:", a)
    for e in erros:
        print("ERRO :", e)
    print("OK — estrutura FAIR e integridade verificadas." if not erros else f"{len(erros)} erro(s).")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
