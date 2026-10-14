# Monitoramento Regionalizado SES-MG

Painel da SES-MG com **pagamentos** a municípios, consórcios e entidades e o **monitoramento das políticas** (estratégias de saúde), por macro, micro e URS.

## Como a atualização funciona

1. O e-mail diário do BO chega e o fluxo do Power Automate salva a planilha **BOPAINEL.csv** no SharePoint, sempre no mesmo arquivo.
2. Todo dia às **06:17** e às **12:17** (Brasília), o GitHub Actions:
   - baixa a planilha pelo link guardado no segredo `BOPAINEL_URL`;
   - roda `scripts/gerar_dados.py`, que gera o `dados.json` sem nenhum dado bancário;
   - publica o site.
3. A página lê o `dados.json` ao abrir, então mostra sempre a última versão.

Para atualizar na hora, use a aba **Actions › Atualizar painel › Run workflow**.

## Monitoramento das políticas (aba Políticas)

- **Fonte:** o relatório exportado do sistema de monitoramento (.xlsx), aba **`relatorio 1`**. O script usa os nomes de abas e colunas exatamente como o sistema exporta.
- **Script:** `scripts/gerar_monitoramento.py` transforma o relatório em `monitoramento.json`.
  - Cada **ID Solicitação** vira uma unidade monitorada, com a etapa mais avançada que ela alcançou.
  - O município é identificado pelo nome (regionalização PDR/MG) ou, se o nome não casar, pelo CNPJ do fundo municipal.
- **Como atualizar** (escolha um):
  1. **Automático:** salve o relatório sempre no mesmo arquivo do SharePoint e crie o segredo `MONITORAMENTO_URL` com o link "Qualquer pessoa com o link".
  2. **Manual:** suba o relatório novo como `dados/relatorio_monitoramento.xlsx` (Add file › Upload files). O site é republicado sozinho.
- **Duas medidas de desempenho** (botão "Medir pelo"):
  - **% do valor apurado** = soma do *Valor Apurado* ÷ soma do *Valor da Meta* (valor previsto). É o padrão.
  - **Situação no sistema** = itens com *Status Cumprimento* "Atingiu" ÷ (Atingiu + Não Atingiu).
- **Cards clicáveis:** todo card com "detalhar ›" abre uma tabela por política, município, URS ou indicador.
- **Filtro de etapa:** na página da política, o card "Até onde o monitoramento chegou" filtra os itens pela etapa mais avançada.

## Ligação pagamentos × políticas

O BO não traz a resolução da política (o "Num Ref" é a resolução do pagamento). A ligação é feita pela tabela **`scripts/depara_politica_programa.csv`**:
- cada linha liga um *Nº Resolução* da política a uma *Unid Programação Gasto* do BO, com a coluna **Confiança** (alta, media, a confirmar, sem correspondência);
- o painel soma, por município, o que foi pago em 2026 nesses programas e mostra como **"Pago em 2026 (BO)"**;
- para corrigir ou incluir uma ligação, edite o CSV (separador `;`) e suba de novo. O site é republicado sozinho.

## Análise para intervenção (aba Análise)

- **Antes × depois da CMA:**
  - *antes* = Valor Apurado na coleta;
  - *depois* = aplica a **Correção da Parcela CMA** dos pedidos de recurso já decididos, limitada ao Valor da Meta. O botão "Quando" troca entre os dois em todo o painel.
- **Matriz de priorização:** cada indicador posicionado pela participação no recurso total × desempenho. O quadrante vermelho reúne os indicadores com muito recurso e baixo desempenho.
- **Regiões mais frágeis:** macro, URS ou micro ordenadas pelo desempenho, com municípios críticos (abaixo do corte), políticas abaixo do corte, valor não apurado e as piores políticas.
- **Disparidades:** amplitude, em pontos percentuais, entre a melhor e a pior macrorregião em cada política.
- **Lista de prioridades:** município × política abaixo do limiar, ordenada pelo valor não apurado. Pode ser baixada em CSV para os planos de intervenção.

## Configuração (uma vez)

1. **Settings › Pages › Source: GitHub Actions.**
2. **Link da planilha:**
   - No SharePoint, abra o menu do arquivo que o fluxo sobrescreve e escolha **Compartilhar › Qualquer pessoa com o link › Pode exibir**.
   - Copie o link.
3. **Segredo:** em **Settings › Secrets and variables › Actions › New repository secret**, crie o segredo:
   - nome: `BOPAINEL_URL`;
   - valor: o link copiado.
4. **Primeira execução:** vá em **Actions › Atualizar painel › Run workflow** e confira se a execução termina verde.

> O link só funciona enquanto o fluxo **sobrescrever o mesmo arquivo**. Se o fluxo criar um arquivo novo por dia, com a data no nome, o link muda todo dia e o download falha.

## Opcional: atualizar assim que o e-mail chegar

No fluxo do Power Automate, depois da ação que salva a planilha, adicione a ação **GitHub › Create a repository dispatch event**. O conector GitHub é padrão, não premium. Preencha assim:
- repositório: `cmir-ses-mg/monitoramento-regionalizado`;
- event_type: `bopainel-atualizado`.

## Arquivos

| Arquivo | O que é |
|---|---|
| `index.html` | a página (sem dados embutidos) |
| `dados.json` | dados gerados pelo script. Esta cópia é a reserva, usada se o download falhar |
| `mapas/*.topojson` | mapas de MG (IBGE) com macro, micro e URS do PDR/MG 2026 |
| `scripts/gerar_dados.py` | transforma a planilha do BO em `dados.json` |
| `monitoramento.json` | dados das políticas gerados pelo script. Esta cópia é a reserva |
| `scripts/gerar_monitoramento.py` | transforma o relatório de monitoramento (aba `relatorio 1`) em `monitoramento.json` |
| `scripts/depara_politica_programa.csv` | ligação política (resolução) × programa do BO (Unid Programação Gasto) |
| `scripts/regionalizacao.csv` | municípios × URS × micro × macro × população (PDR/MG 2026) |
| `.github/workflows/atualizar-painel.yml` | agenda e publicação automática |
