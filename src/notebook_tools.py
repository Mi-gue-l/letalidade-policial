"""Executor mínimo de notebooks (sem Jupyter).

Executa as células de código de um ``.ipynb`` em um único espaço de nomes,
captura ``stdout``, o valor da última expressão (DataFrames em texto e HTML) e
figuras do Matplotlib (PNG), e grava as saídas no próprio arquivo.

Serve para **regenerar os outputs do notebook em ambientes sem JupyterLab**:

    python -m src.notebook_tools notebooks/analise_exploratoria.ipynb

(Com Jupyter instalado, o equivalente é
``jupyter nbconvert --to notebook --execute --inplace <arquivo>``.)
"""
from __future__ import annotations

import ast
import base64
import contextlib
import io
import json
import os
import sys
import traceback
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _lines(text: str) -> list[str]:
    parts = text.splitlines(keepends=True)
    return parts


def _fig_outputs(n_exec: int) -> list[dict]:
    outs = []
    for num in plt.get_fignums():
        buf = io.BytesIO()
        plt.figure(num).savefig(buf, format="png", dpi=110, bbox_inches="tight")
        outs.append({
            "output_type": "display_data",
            "data": {"image/png": base64.b64encode(buf.getvalue()).decode(), "text/plain": ["<Figure>"]},
            "metadata": {},
        })
    plt.close("all")
    return outs


def _value_output(val, n_exec: int) -> dict | None:
    if val is None:
        return None
    data = {"text/plain": _lines(repr(val) if not isinstance(val, (pd.DataFrame, pd.Series)) else val.to_string())}
    if isinstance(val, (pd.DataFrame, pd.Series)):
        data["text/html"] = _lines(val.to_html() if isinstance(val, pd.DataFrame) else val.to_frame().to_html())
    return {"output_type": "execute_result", "execution_count": n_exec, "data": data, "metadata": {}}


def execute_cell(source: str, ns: dict, n_exec: int) -> list[dict]:
    outputs: list[dict] = []
    out, err = io.StringIO(), io.StringIO()
    value = None
    try:
        tree = ast.parse(source)
        last = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = ast.Expression(tree.body.pop().value)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            exec(compile(tree, "<celula>", "exec"), ns)
            if last is not None:
                value = eval(compile(last, "<celula>", "eval"), ns)
    except Exception:  # noqa: BLE001 - propagamos como saída de erro, como o Jupyter
        tb = traceback.format_exc().splitlines()
        outputs.append({"output_type": "error", "ename": type(sys.exc_info()[1]).__name__,
                        "evalue": str(sys.exc_info()[1]), "traceback": tb})
        raise_after = True
    else:
        raise_after = False
    if out.getvalue():
        outputs.insert(0, {"output_type": "stream", "name": "stdout", "text": _lines(out.getvalue())})
    if err.getvalue():
        outputs.append({"output_type": "stream", "name": "stderr", "text": _lines(err.getvalue())})
    v = _value_output(value, n_exec)
    if v:
        outputs.append(v)
    outputs.extend(_fig_outputs(n_exec))
    if raise_after:
        raise RuntimeError("Erro na execução da célula:\n" + "\n".join(outputs[-1]["traceback"] if outputs[-1]["output_type"] == "error" else []))
    return outputs


def execute_notebook(path: Path) -> None:
    nb = json.loads(path.read_text(encoding="utf-8"))
    os.chdir(ROOT)  # caminhos relativos à raiz do repositório
    sys.path.insert(0, str(ROOT))
    ns: dict = {"__name__": "__main__"}
    n = 0
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        n += 1
        src = "".join(cell["source"])
        cell["outputs"] = execute_cell(src, ns, n)
        cell["execution_count"] = n
    path.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def make_notebook(cells: list[tuple[str, str]]) -> dict:
    """Cria a estrutura nbformat 4.5 a partir de ``[(tipo, fonte), ...]``."""
    out = []
    for i, (tipo, fonte) in enumerate(cells):
        c = {"id": f"c{i:03d}", "cell_type": tipo, "metadata": {}, "source": _lines(fonte.strip("\n"))}
        if tipo == "code":
            c.update(execution_count=None, outputs=[])
        out.append(c)
    return {
        "cells": out,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.13"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    execute_notebook(Path(sys.argv[1]).resolve())
    print("Notebook executado:", sys.argv[1])
