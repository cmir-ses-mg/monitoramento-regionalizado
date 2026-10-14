"""
Gera monitoramento.json (aba Políticas do site) a partir do relatório de
monitoramento das políticas exportado pelo sistema.

Uso:  python scripts/gerar_monitoramento.py caminho/Relatorio.xlsx [saida.json] [BOPAINEL.csv]

- Lê a aba "relatorio 1" com os nomes de colunas originais do sistema.
- Cada "ID Solicitação" é uma unidade monitorada (município × indicador × período,
  e às vezes equipe/estabelecimento). No relatório ela se repete uma vez por
  "Etapa do Monitoramento"; aqui vira uma linha só, com a etapa mais avançada.
- Município: casa pelo nome com a regionalização PDR/MG; se não casar,
  usa o CNPJ do fundo municipal encontrado na planilha do BO (opcional).
"""
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

AQUI = Path(__file__).resolve().parent
ENTRADA = Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI.parent / "relatorio_monitoramento.xlsx"
SAIDA = Path(sys.argv[2]) if len(sys.argv) > 2 else AQUI.parent / "monitoramento.json"
BO = Path(sys.argv[3]) if len(sys.argv) > 3 else AQUI.parent / "BOPAINEL.csv"
ABA = "relatorio 1"

ETAPAS = {
    "Coleta de Dados": 1,
    "Ciência ou Recurso Sobre os Resultados Apurados": 2,
    "Análise e Deliberação da Comissão Macrorregional": 3,
}
STATUS = {"Atingiu": 0, "Não Atingiu": 1, "Não Informado": 2}


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", s.upper()).split())


def txt(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s in ("\\N", "nan", "NaT") else s


def num(v):
    try:
        f = float(v)
        return None if pd.isna(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def dia(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return pd.Timestamp(v).strftime("%Y-%m-%d")
    except Exception:
        return None


def main():
    df = pd.read_excel(ENTRADA, sheet_name=ABA, dtype=object)
    obrig = ["Nome Estratégia ou Projeto", "Nº Resolução", "Município", "CNPJ Beneficiário", "ID Indicador",
             "Nome Indicador", "Etapa do Monitoramento", "ID Solicitação", "Status Cumprimento"]
    faltando = [c for c in obrig if c not in df.columns]
    if faltando:
        sys.exit(f"Colunas não encontradas na aba '{ABA}': {faltando}")

    # ---------- município -> código IBGE (6 dígitos)
    reg = pd.read_csv(AQUI / "regionalizacao.csv", dtype=str)
    por_nome = {norm(m): c for m, c in zip(reg["municipio"], reg["cod6"])}
    por_cnpj = {}
    if BO.exists():
        bo = pd.read_csv(BO, dtype=str, usecols=["CNPJ_CPF Credor - Formatado", "Município Credor - Código"])
        bo["cnpj"] = bo["CNPJ_CPF Credor - Formatado"].str.replace(r"\D", "", regex=True).str.lstrip("0")
        por_cnpj = dict(zip(bo["cnpj"], bo["Município Credor - Código"]))

    def cod_mun(nome, cnpj):
        c = por_nome.get(norm(nome))
        if not c:
            c = por_cnpj.get(re.sub(r"\D", "", str(cnpj)).lstrip("0"))
        return c or "0"

    df["_etapa"] = df["Etapa do Monitoramento"].map(ETAPAS).fillna(1).astype(int)
    df = df.sort_values(["ID Solicitação", "_etapa"])

    # ---------- dicionários
    pols, pol_idx = [], {}
    inds, ind_idx = [], {}
    textos, txt_idx = [], {}

    def tid(s):
        s = txt(s)
        if not s or s == "Ciência automática após finalização da etapa.":
            return -1
        if s not in txt_idx:
            txt_idx[s] = len(textos)
            textos.append(s)
        return txt_idx[s]

    faixas, faixa_idx = [], {}

    def fid(s):
        s = txt(s)
        if not s:
            return -1
        if s not in faixa_idx:
            faixa_idx[s] = len(faixas)
            faixas.append(s)
        return faixa_idx[s]

    periodos, per_idx = [], {}

    def pid(t):
        if t not in per_idx:
            per_idx[t] = len(periodos)
            periodos.append(list(t))
        return per_idx[t]

    cats = ["Meta Não Atingida", "Outro Motivo", "Correção de Indicador", "Perda de Prazo"]

    rows, sem_mun = [], set()
    for sol, g in df.groupby("ID Solicitação", sort=False):
        ult = g.iloc[-1]                       # etapa mais avançada
        primeiro = lambda col: next((v for v in g[col] if txt(v)), None)

        res = int(ult["Nº Resolução"])
        if res not in pol_idx:
            pol_idx[res] = len(pols)
            pols.append(dict(
                res=res, nome=txt(ult["Nome Estratégia ou Projeto"]), sub=txt(ult["Subsecretaria"]),
                cma=txt(ult["Comissão Macrorregional (CMA)"]), bloco=txt(ult["Bloco"]),
                per=txt(ult["Periodicidade"]), tipo=txt(ult["Tipo"]),
            ))
        iid = int(ult["ID Indicador"])
        if iid not in ind_idx:
            ind_idx[iid] = len(inds)
            inds.append(dict(id=iid, nome=txt(ult["Nome Indicador"]), fonte=txt(ult["Tipo da Fonte"]),
                             resp=txt(ult["Responsabilidade da Declaração"]), meta=num(ult["Meta"])))

        cod = cod_mun(ult["Município"], ult["CNPJ Beneficiário"])
        if cod == "0":
            sem_mun.add(txt(ult["Município"]) or str(ult["CNPJ Beneficiário"]))
        delib = txt(primeiro("Resultado da Deliberação"))
        cat = txt(primeiro("Categoria de Recurso"))
        cnes = num(ult["CNES"])

        rows.append([
            pol_idx[res], ind_idx[iid], cod, int(sol), int(cnes) if cnes else 0,
            pid((dia(ult["Período Monitorado De"]), dia(ult["Período Monitorado Até"]), txt(ult["Mês Monitoramento"]),
                 dia(ult["Monitoramento Finalizado em"]))), int(g["_etapa"].max()),
            num(ult["Meta"]), num(ult["Valor da Meta"]), num(ult["Resultado Apurado"]), fid(ult["Faixa de Desempenho"]),
            num(ult["Valor Apurado"]), STATUS.get(txt(ult["Status Cumprimento"]), 2),
            1 if txt(ult["Dispensa de Indicador"]) == "Sim" else 0,
            1 if (g["Ciência ou Recurso"].astype(str) == "Recurso").any() else 0,
            1 if delib == "DEFERIDO" else (0 if delib == "INDEFERIDO" else -1),
            cats.index(cat) if cat in cats else -1,
            num(primeiro("Resultado Apurado após reunião")), num(primeiro("Correção da Parcela CMA")),
            tid(primeiro("Justificativa")), tid(primeiro("Parecer e Recomendação")),
            txt(ult["Razão Social"]),
        ])

    # razão social vira índice (economiza espaço)
    benefs = sorted({r[-1] for r in rows})
    bi = {b: i for i, b in enumerate(benefs)}
    for r in rows:
        r[-1] = bi[r[-1]]

    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    out = dict(
        cols=["pol", "ind", "cod", "sol", "cnes", "per", "etapa", "meta", "vmeta", "res",
              "faixa", "vap", "st", "disp", "rec", "delib", "cat", "resPos", "corr", "just", "parecer", "benef"],
        pols=pols, inds=inds, periodos=periodos, faixas=faixas, textos=textos, cats=cats, benefs=benefs, rows=rows,
        upd=agora.strftime("%d/%m/%Y às %H:%M"),
        fin=max((p[3] for p in periodos if p[3]), default=None),
    )
    SAIDA.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"OK: {len(rows)} solicitações · {len(pols)} políticas · {len(inds)} indicadores -> {SAIDA}")
    if sem_mun:
        print(f"Atenção: sem município identificado: {sorted(sem_mun)}")


if __name__ == "__main__":
    main()
