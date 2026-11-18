# Dicionário de Dados

Conjunto: **Vítimas de "auto de resistência" (homicídio decorrente de oposição à intervenção policial) no Município do Rio de Janeiro — 1º quadrimestre (jan–abr), 2003–2022**.

| Item | Descrição |
|---|---|
| Fonte primária | Instituto de Segurança Pública do Estado do Rio de Janeiro (ISP-RJ) — <http://www.ispdados.rj.gov.br/> (acesso registrado na planilha: 24/05/2022) |
| Publicador do recorte | DATA.RIO / Instituto Pereira Passos (IPP), *Tabela 2300* (cálculos e tabulação: IPP, Coordenadoria Técnica de Informações da Cidade) |
| Arquivo bruto | `data/raw/tabela_2300_data_rio.xls` · SHA-256 `179553629368d5962295634ed9eeb118cb0b1188d6ddf7f02a854182fa7b2d35` · aba de dados: `T 2300` |
| Granularidade | **1 linha = 1 ano**; cada linha cobre apenas o **1º quadrimestre** (jan–abr) |
| Unidade espacial | Município do Rio de Janeiro (agregado; sem desagregação por bairro, AISP ou perfil da vítima) |
| Cobertura temporal | 2003–2022 (20 observações) |
| Arquivos tratados | `data/processed/autos_resistencia_rio_jan_abr.csv.gz` (UTF-8, separador `,`, ponto decimal) e `.json` (lista de registros) |
| Rastreabilidade | `data/processed/etl_log.json` (hash do bruto e das saídas, regras aplicadas, desvios da validação) |
| Métricas agregadas | `data/processed/metricas_agregadas.json` (resultados estatísticos usados no artigo) |
| Licença | Tratamento, código e texto: ver `LICENSE` (MIT) e `LICENSE-DATA.md` (CC BY 4.0). Os dados originais permanecem sujeitos aos termos de uso do ISP-RJ/DATA.RIO. |

## Variáveis do arquivo tratado

Convenção: sufixo `_publicada` = valor **exatamente como divulgado na fonte**; sufixo `_calc` = **recalculado** por `src/etl.py` a partir das colunas primárias (usado para auditar a fonte; as duas versões coincidem — ver `etl_log.json`).

| # | Variável | Significado (pesquisa) | Tipo primitivo | Unidade / formato | Origem | Nulos |
|---|---|---|---|---|---|---|
| 1 | `ano` | Ano do 1º quadrimestre observado | `int16` | AAAA (2003–2022) | Fonte | 0 |
| 2 | `vitimas_jan_abr` | **Variável-resposta.** Total de vítimas de oposição à intervenção policial registradas em jan–abr no MRJ | `int32` | pessoas (contagem ≥ 0) | Fonte | 0 |
| 3 | `dif_abs_publicada` | Diferença absoluta do total em relação ao mesmo quadrimestre do ano anterior | `Int32` (anulável) | pessoas (pode ser negativa) | Fonte | 1 (2003: `..`) |
| 4 | `dif_pct_publicada` | Diferença percentual em relação ao ano anterior | `float64` | % | Fonte | 1 (2003: `..`) |
| 5 | `populacao` | População residente estimada/projetada pelo ISP para o último mês do quadrimestre | `float64` | habitantes (valor fracionário da projeção; **não** arredondado) | Fonte | 0 |
| 6 | `taxa_100mil_publicada` | Taxa de vítimas por 100 mil habitantes no quadrimestre | `float64` | vítimas / 100 mil hab. (quadrimestral, **não** anualizada) | Fonte | 0 |
| 7 | `media_mensal_publicada` | Média mensal de vítimas no quadrimestre | `float64` | vítimas / mês | Fonte | 0 |
| 8 | `dif_abs_calc` | `vitimas_jan_abr[t] − vitimas_jan_abr[t−1]` | `Int32` (anulável) | pessoas | Derivada | 1 (2003) |
| 9 | `dif_pct_calc` | `(vitimas[t] / vitimas[t−1] − 1) × 100` | `float64` | % | Derivada | 1 (2003) |
| 10 | `taxa_100mil_calc` | `vitimas_jan_abr / populacao × 100 000` | `float64` | vítimas / 100 mil hab. | Derivada | 0 |
| 11 | `media_mensal_calc` | `vitimas_jan_abr / 4` | `float64` | vítimas / mês | Derivada | 0 |
| 12 | `indice_vitimas_base100` | `vitimas[t] / vitimas[2003] × 100` | `float64` | índice (2003 = 100) | Derivada | 0 |
| 13 | `indice_taxa_base100` | `taxa_100mil_calc[t] / taxa_100mil_calc[2003] × 100` | `float64` | índice (2003 = 100) | Derivada | 0 |
| 14 | `indice_populacao_base100` | `populacao[t] / populacao[2003] × 100` | `float64` | índice (2003 = 100) | Derivada | 0 |

### Valores ausentes
O único ausente é a primeira diferença (2003), pois não há ano anterior; a fonte o marca com `..` (“Não se aplica dado numérico”). O ETL converte `..` em nulo e **não imputa** valores.

### Regras de validação (executadas a cada `python -m src.etl`)
Anos únicos e contíguos · contagens não negativas · população positiva · sem nulos em `ano`, `vitimas_jan_abr`, `populacao` · `dif_abs`, `dif_pct`, `taxa` e `media_mensal` publicadas = recalculadas (tolerância 10⁻⁶).

## Métricas agregadas (`metricas_agregadas.json`)

| Bloco | Conteúdo |
|---|---|
| `serie` | Estatísticas descritivas (n, média, desvio-padrão, CV, quartis, IQR, MAD, assimetria) de vítimas e taxa |
| `rq1` | Tau de Kendall e inclinação de Theil–Sen; quebra única por mínimo de SSE com teste de permutação (20 000 réplicas, semente 2022); regimes e testes de Mann–Whitney |
| `rq2` | Variações acumuladas e CAGR de vítimas, taxa e população; decomposição logarítmica; Spearman vítimas×taxa e vítimas×população; picos e vales |
| `rq3` | Variações anuais, escore z modificado (MAD), cerca de Tukey, **z de Poisson** com correção de Bonferroni e volatilidade por regime |

## Terminologia
“Auto de resistência” e “resistência seguida de morte” eram designações usadas nos registros policiais; a **Resolução Conjunta nº 2, de 13/10/2015**, determinou sua substituição por “lesão corporal ou morte decorrentes de oposição à intervenção policial”. A Tabela 2300 usa a expressão “Homicídio decorrente de oposição à intervenção policial” (nota 1 da planilha). A classificação é **provisória** (primeira impressão da autoridade policial) e pode ser alterada no curso da investigação, do processo e da sentença (aba “Definições” da planilha).

## Limitações conhecidas
* Apenas o **1º quadrimestre**; não é possível extrapolar para o ano inteiro nem estudar sazonalidade.
* Agregado municipal: sem informação sobre local, perfil das vítimas, corporação ou contexto da ocorrência.
* Contagem de **registros** policiais: sujeita a subnotificação, reclassificação e mudanças de procedimento ao longo do tempo.
* Coluna `populacao` é projeção do ISP (valores fracionários); a taxa herda essa incerteza.
* Dados de 2022 refletem a consulta de 24/05/2022 e podem ter sido revisados pela fonte depois.
