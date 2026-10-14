"""
Gera dados.json para o site Monitoramento Regionalizado SES-MG a partir da
planilha diária do BO (BOPAINEL.csv).

Uso:  python scripts/gerar_dados.py caminho/BOPAINEL.csv  [saida.json]

- Mantém só o necessário para o site (sem dados bancários).
- Pagamentos = OPs "Acatada pelo banco". Em transmissão = "Pendente de transmissão".
- Regionalização (URS, micro, macro, população): scripts/regionalizacao.csv (PDR/MG 2026).
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

AQUI = Path(__file__).resolve().parent
ENTRADA = Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI.parent / "BOPAINEL.csv"
SAIDA = Path(sys.argv[2]) if len(sys.argv) > 2 else AQUI.parent / "dados.json"

COL = {
    "cod": "Município Credor - Código",
    "benef": "Razão Social Credor",
    "cnpj": "CNPJ_CPF Credor - Formatado",
    "tipo_instr": "Tipo ContratoConvênio Saída-Código",
    "instr": "ContratoConvênio Saída",
    "res": "Num Ref ContratoConvênio Saída",
    "acao": "Projeto_Atividade - Descrição",
    "fonte": "Fonte Recurso - Descrição",
    "proc": "Procedência - Descrição",
    "mod": "Modalidade Aplicação - Código",
    "prog": "Unid Programação Gasto - Descrição",
    "elem": "Elemento Item Despesa - Descrição",
    "emp": "Número Empenho",
    "dt_emp": "Data Registro Doc Empenho",
    "valor": "Valor Pago Financeiro",
    "op": "Número Docto Pagamento",
    "dt_pg": "Data Pagamento",
    "sit": "Situação Ordem Pagamento - Descrição",
    "ue": "Unidade Executora - Código/Nome",
}


def ler_csv(caminho: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(caminho, dtype=str, encoding=enc, usecols=list(COL.values()))
            break
        except UnicodeDecodeError:
            continue
    df = df.fillna("")
    for c in df.columns:
        df[c] = df[c].str.strip()
    return df


def data_iso(s: pd.Series) -> pd.Series:
    d = s.str.slice(0, 10).str.replace("/", "-", regex=False)
    return d.where(~d.str.startswith("0001") & (d != ""), None)


def tipo_benef(nome: str, mod: str) -> int:
    if re.match(r"^(FUNDO MUNICIPAL|FMS|PM |PREFEITURA|MUNICIPIO)", nome.upper()):
        return 0  # Município (fundo/prefeitura)
    return 2 if mod == "50" else 1  # 2 = entidade s/ fins lucrativos, 1 = consórcio


def main():
    df = ler_csv(ENTRADA)
    # valores vêm como "76337,29" (vírgula decimal, sem separador de milhar)
    df["v"] = pd.to_numeric(df[COL["valor"]].str.replace(",", ".", regex=False), errors="coerce").fillna(0)
    df["d"] = data_iso(df[COL["dt_pg"]])
    df["de"] = data_iso(df[COL["dt_emp"]])

    pagos = df[df[COL["sit"]] == "Acatada pelo banco"].copy()
    transm = df[df[COL["sit"]].str.startswith("Pendente")].copy()
    if pagos.empty:
        sys.exit("Nenhum pagamento 'Acatada pelo banco' encontrado — conferir a planilha.")

    listas = {}

    def indexar(col, chave):
        vals = sorted(pagos[col].unique())
        listas[chave] = vals
        m = {x: i for i, x in enumerate(vals)}
        return pagos[col].map(m).astype(int)

    pagos["pi"] = indexar(COL["prog"], "progs")
    pagos["bi"] = indexar(COL["benef"], "bens")
    pagos["ai"] = indexar(COL["acao"], "acoes")
    pagos["fi"] = indexar(COL["fonte"], "fontes")
    pagos["ui"] = indexar(COL["ue"], "ues")
    pagos["ei"] = indexar(COL["elem"], "elems")

    cnpj = pagos.groupby("bi")[COL["cnpj"]].first().to_dict()
    listas["cnpj"] = [cnpj.get(i, "") for i in range(len(listas["bens"]))]
    mod = pagos.groupby(COL["benef"])[COL["mod"]].agg(lambda s: s.mode().iat[0]).to_dict()
    listas["btipo"] = [tipo_benef(b, mod.get(b, "41")) for b in listas["bens"]]

    datas = sorted(set(pagos["d"].dropna()) | set(pagos["de"].dropna()))
    di = {x: i for i, x in enumerate(datas)}
    pagos["em"] = pagos[COL["proc"]].str.contains("EMENDA").astype(int)

    rows = [
        [c, int(pi), di[d], round(float(v), 2), res, int(b), (t or "1")[0], int(a), int(f), int(u), int(e), di[de], ne, op, ins, int(em)]
        for c, pi, d, v, res, b, t, a, f, u, e, de, ne, op, ins, em in zip(
            pagos[COL["cod"]], pagos["pi"], pagos["d"], pagos["v"], pagos[COL["res"]], pagos["bi"],
            pagos[COL["tipo_instr"]], pagos["ai"], pagos["fi"], pagos["ui"], pagos["ei"], pagos["de"],
            pagos[COL["emp"]], pagos[COL["op"]], pagos[COL["instr"]], pagos["em"],
        )
        if d in di and de in di
    ]

    reg = pd.read_csv(AQUI / "regionalizacao.csv", dtype=str)
    mun = {r.cod6: [r.municipio, r.urs, r.micro, r.macro, int(float(r["pop"]))] for _, r in reg.iterrows()}
    mun["0"] = ["Consórcios (sem município)", "—", "—", "—", 0]

    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    dados = dict(
        listas,
        dates=datas,
        rows=rows,
        tr=transm.groupby(COL["cod"])["v"].sum().round(2).to_dict(),
        trDate=transm["d"].dropna().min() if transm["d"].notna().any() else None,
        mun=mun,
        upd=agora.strftime("%d/%m/%Y às %H:%M"),
        ref=pagos["d"].dropna().max(),
    )
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"OK: {len(rows)} pagamentos · R$ {pagos['v'].sum():,.2f} · até {dados['ref']} -> {SAIDA}")


if __name__ == "__main__":
    main()
