"""Testes do pipeline (unittest, sem dependências extras).

Execução: ``python -m unittest discover -s tests -v``
"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src import analysis, etl


class TestETL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheet = etl.read_sheet(etl.RAW_DEFAULT)
        cls.df = etl.add_derived_metrics(etl.parse_table(cls.sheet))

    def test_shape_e_periodo(self):
        self.assertEqual(len(self.df), 20)
        self.assertEqual((self.df.ano.min(), self.df.ano.max()), (2003, 2022))

    def test_na_token_vira_nulo(self):
        self.assertTrue(pd.isna(self.df.loc[0, "dif_abs_publicada"]))
        self.assertTrue(pd.isna(self.df.loc[0, "dif_pct_publicada"]))
        self.assertEqual(int(self.df.isna().sum().sum()), 4)  # 2 publicadas + 2 calculadas em 2003

    def test_tipos(self):
        self.assertEqual(str(self.df["ano"].dtype), "int16")
        self.assertEqual(str(self.df["vitimas_jan_abr"].dtype), "int32")
        self.assertEqual(str(self.df["dif_abs_publicada"].dtype), "Int32")

    def test_valores_conhecidos(self):
        r = self.df.set_index("ano")
        self.assertEqual(r.loc[2008, "vitimas_jan_abr"], 331)
        self.assertEqual(r.loc[2013, "vitimas_jan_abr"], 77)
        self.assertAlmostEqual(r.loc[2003, "taxa_100mil_calc"], 4.961013, places=5)

    def test_validacao_passa_e_detecta_adulteracao(self):
        rel = etl.validate(self.df)
        self.assertEqual(rel["max_desvio_dif_abs"], 0)
        bruto = etl.parse_table(self.sheet)
        bruto.loc[5, "vitimas_jan_abr"] += 1  # adulteração na fonte
        with self.assertRaises(AssertionError):
            etl.validate(etl.add_derived_metrics(bruto))

    def test_parse_tolera_linhas_extras(self):
        extra = pd.concat([pd.DataFrame([["lixo"] + [None] * 6]), self.sheet], ignore_index=True)
        self.assertEqual(len(etl.parse_table(extra)), 20)

    def test_pipeline_deterministico(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            etl.run(etl.RAW_DEFAULT, Path(a))
            etl.run(etl.RAW_DEFAULT, Path(b))
            for nome in ("autos_resistencia_rio_jan_abr.csv.gz", "autos_resistencia_rio_jan_abr.json", "etl_log.json"):
                self.assertEqual(etl.sha256(Path(a) / nome), etl.sha256(Path(b) / nome), nome)

    def test_bruto_nao_alterado(self):
        log = json.loads((etl.OUT_DEFAULT / "etl_log.json").read_text(encoding="utf-8"))
        self.assertEqual(etl.sha256(etl.RAW_DEFAULT), log["sha256_bruto"])


class TestAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = etl.load_processed()

    def test_poisson_z_formula(self):
        pz = analysis.poisson_z(self.df)
        self.assertAlmostEqual(pz.loc[2011, "z_poisson"], (107 - 212) / np.sqrt(107 + 212), places=9)

    def test_quebra_em_2011(self):
        q = analysis.quebra_unica(self.df)
        self.assertEqual(q["ano_inicio_segmento2"], 2011)
        self.assertLess(q["p_permutacao"], 0.05)

    def test_decomposicao_log_fecha(self):
        d = analysis.contagem_vs_taxa(self.df)["decomposicao_log"]
        self.assertAlmostEqual(d["delta_ln_taxa"], d["delta_ln_vitimas"] - d["delta_ln_populacao"], places=9)

    def _close(self, a, b, path="raiz"):
        """Comparação recursiva com tolerância relativa (robusta a diferenças de ULP entre plataformas)."""
        if isinstance(a, dict):
            self.assertEqual(a.keys(), b.keys(), path)
            for k in a:
                self._close(a[k], b[k], f"{path}.{k}")
        elif isinstance(a, list):
            self.assertEqual(len(a), len(b), path)
            for i, (x, y) in enumerate(zip(a, b)):
                self._close(x, y, f"{path}[{i}]")
        elif isinstance(a, float):
            self.assertAlmostEqual(a, b, delta=1e-9 * max(1.0, abs(a)), msg=path)
        else:
            self.assertEqual(a, b, path)

    def test_metricas_json_reprodutivel(self):
        gravado = json.loads((etl.OUT_DEFAULT / "metricas_agregadas.json").read_text(encoding="utf-8"))
        recalc = json.loads(json.dumps(analysis.compute(self.df)))
        self._close(gravado, recalc)


if __name__ == "__main__":
    unittest.main()
