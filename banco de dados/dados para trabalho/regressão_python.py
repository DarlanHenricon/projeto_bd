# %% [markdown]
# # Regressão Linear — Consumo de Energia × Tarifas (EPE + ANEEL)
# 
# **Objetivo:** investigar a associação entre o consumo mensal nacional de energia elétrica (EPE) e os componentes tarifários médios (ANEEL).
# 
# ## Fontes fornecidas
# - **EPE — `Dados_abertos_Consumo_Mensal_energia(1).xlsx`:** a aba `ANALISE CONS NUMCONS SAM` contém consumo mensal agregado por região para jan/2023 até set/2026. O dicionário informa que `Consumo` é medido em MWh e que a tabela SAM é agregada por região, subsistema, classe e ambiente de contratação (PDF, página 1). A planilha recebida, porém, apresenta uma tabela dinâmica regional já agregada, sem classe nessa aba.
# - **ANEEL — `tarifas-homologadas-distribuidoras-energia-eletrica(2).csv`:** tarifas homologadas, com início/fim de vigência, base tarifária, unidade, TUSD e TE.
# 
# ## Delimitação metodológica importante
# O arquivo EPE disponível nesta pasta de trabalho **não oferece, na aba regional utilizada, consumo mensal por distribuidora/UF/classe**. O CSV da ANEEL identifica a distribuidora, mas não traz uma coluna explícita de região/UF da concessão. Portanto, este notebook faz uma análise **nacional exploratória**: soma o consumo das cinco regiões por mês e compara com uma média simples nacional dos registros tarifários elegíveis.
# 
# Essa média simples não é uma tarifa efetivamente paga por um consumidor representativo: não é ponderada pelo mercado, e as tarifas podem variar por distribuidora, classe, subgrupo e posto tarifário. A regressão mede associação, não causalidade. Para um estudo regional/por classe, será necessário obter uma tabela de correspondência distribuidora–UF/região e uma série EPE com a mesma granularidade.
# 
# **Período:** interseção mensal disponível na aba EPE e na vigência tarifária: o código limita automaticamente a análise ao intervalo jan/2023–set/2026, mas meses sem tarifa compatível serão removidos.

# %% [markdown]
# ## 1. Bibliotecas e caminhos dos arquivos

# %%
# 1. Bibliotecas
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from pathlib import Path
from tkinter import Tk, filedialog

pd.set_option("display.float_format", lambda x: f"{x:,.3f}")

# 2. Localização dos arquivos
# Procura na pasta atual e, se não encontrar, abre uma janela para seleção.

def selecionar_arquivo(titulo, padrao, extensao):
    candidatos = [
        Path.cwd() / padrao,
        Path.cwd().parent / padrao,
    ]
    for caminho in candidatos:
        if caminho.exists():
            print(f"Arquivo localizado: {caminho.resolve()}")
            return caminho

    raiz = Tk()
    raiz.withdraw()
    raiz.attributes("-topmost", True)
    caminho = filedialog.askopenfilename(
        title=titulo,
        filetypes=[
            (f"Arquivo {extensao}", f"*{extensao}"),
            ("Todos os arquivos", "*.*")
        ]
    )
    raiz.destroy()

    if not caminho:
        raise FileNotFoundError(
            f"Nenhum arquivo selecionado para {padrao}. "
            "Execute novamente esta célula e selecione o arquivo."
        )
    return Path(caminho)

ARQUIVO_EPE = selecionar_arquivo(
    "Selecione a planilha de consumo mensal da EPE",
    "Dados_abertos_Consumo_Mensal_energia(1).xlsx",
    ".xlsx"
)

ARQUIVO_ANEEL = selecionar_arquivo(
    "Selecione o CSV de tarifas homologadas da ANEEL",
    "tarifas-homologadas-distribuidoras-energia-eletrica(2).csv",
    ".csv"
)

print("\\nArquivos configurados:")
print("EPE:", ARQUIVO_EPE)
print("ANEEL:", ARQUIVO_ANEEL)


# %% [markdown]
# ## 2. Leitura e inspeção dos dados EPE

# %%
# A aba recebida é uma tabela dinâmica: linha 0 contém o título,
# linha 1 contém as datas e as linhas seguintes contêm as regiões.
epe_raw = pd.read_excel(
    ARQUIVO_EPE,
    sheet_name="ANALISE CONS NUMCONS SAM",
    header=None
)

display(epe_raw.iloc[:7, :6])
print("Dimensão da aba:", epe_raw.shape)

# %%
# Extrai as datas da primeira linha de cabeçalho e as cinco regiões.
datas = pd.to_datetime(epe_raw.iloc[1, 1:], errors="coerce")
epe_largo = epe_raw.iloc[2:, :].copy()
epe_largo = epe_largo.iloc[:, :len(datas) + 1]
epe_largo.columns = ["Regiao"] + list(datas)
epe_largo = epe_largo.dropna(subset=["Regiao"])

# Converte a tabela de formato largo para formato longo.
epe = epe_largo.melt(
    id_vars="Regiao",
    var_name="Data",
    value_name="Consumo_MWh"
)
epe["Data"] = pd.to_datetime(epe["Data"], errors="coerce")
epe["Consumo_MWh"] = pd.to_numeric(epe["Consumo_MWh"], errors="coerce")
epe = epe.dropna(subset=["Data", "Consumo_MWh"])
epe["Mes"] = epe["Data"].dt.to_period("M")

# Consumo nacional: soma das cinco regiões em cada mês.
epe_mensal = (
    epe.groupby("Mes", as_index=False)
       .agg(Consumo_MWh=("Consumo_MWh", "sum"))
)
display(epe_mensal.head())
display(epe_mensal.tail())
print("Regiões encontradas:", sorted(epe["Regiao"].unique()))

# %% [markdown]
# ## 3. Leitura e tratamento das tarifas ANEEL

# %%
# CSV usa ponto e vírgula como separador e vírgula como decimal.
aneel = pd.read_csv(
    ARQUIVO_ANEEL,
    sep=";",
    decimal=",",
    encoding="utf-8-sig",
    low_memory=False
)

colunas_necessarias = [
    "DatInicioVigencia", "DatFimVigencia", "DscBaseTarifaria",
    "DscUnidadeTerciaria", "DscClasse", "DscSubGrupo",
    "DscModalidadeTarifaria", "NomPostoTarifario", "VlrTUSD", "VlrTE"
]
display(aneel[colunas_necessarias].head())
print("Dimensão ANEEL:", aneel.shape)

# %%
# Converte datas e valores, tratando eventuais strings.
for col in ["DatInicioVigencia", "DatFimVigencia"]:
    aneel[col] = pd.to_datetime(aneel[col], dayfirst=True, errors="coerce")

for col in ["VlrTUSD", "VlrTE"]:
    if aneel[col].dtype == "object":
        aneel[col] = (
            aneel[col].astype(str)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
    aneel[col] = pd.to_numeric(aneel[col], errors="coerce")

# Recorte conceitual para comparar tarifas de energia por MWh:
# Tarifa de Aplicação e unidade MWh. Mantemos todas as classes/modalidades
# e calculamos uma média simples exploratória por mês de vigência.
tarifas = aneel[
    (aneel["DscBaseTarifaria"].astype(str).str.strip() == "Tarifa de Aplicação") &
    (aneel["DscUnidadeTerciaria"].astype(str).str.strip() == "MWh")
].copy()

tarifas = tarifas.dropna(subset=["DatInicioVigencia", "DatFimVigencia", "VlrTUSD", "VlrTE"])
tarifas["Tarifa_Total_R_MWh"] = tarifas["VlrTUSD"] + tarifas["VlrTE"]

print("Registros tarifários após filtros:", len(tarifas))
display(tarifas[[
    "DatInicioVigencia", "DatFimVigencia", "DscClasse",
    "DscModalidadeTarifaria", "VlrTUSD", "VlrTE", "Tarifa_Total_R_MWh"
]].head())

# %% [markdown]
# ## 4. Transformar vigências tarifárias em observações mensais

# %%
# Para cada mês da EPE, seleciona registros ANEEL cuja vigência
# intersecta aquele mês. Calcula média simples nacional dos registros.
meses = sorted(epe_mensal["Mes"].unique())
linhas = []

for mes in meses:
    inicio_mes = mes.to_timestamp(how="start")
    fim_mes = mes.to_timestamp(how="end")

    vigentes = tarifas[
        (tarifas["DatInicioVigencia"] <= fim_mes) &
        (tarifas["DatFimVigencia"] >= inicio_mes)
    ]

    if not vigentes.empty:
        linhas.append({
            "Mes": mes,
            "Media_TUSD_R_MWh": vigentes["VlrTUSD"].mean(),
            "Media_TE_R_MWh": vigentes["VlrTE"].mean(),
            "Media_Tarifa_Total_R_MWh": vigentes["Tarifa_Total_R_MWh"].mean(),
            "Qtd_Registros_Tarifarios": len(vigentes)
        })

tarifa_mensal = pd.DataFrame(linhas)
print("Meses com tarifa compatível:", len(tarifa_mensal))
display(tarifa_mensal.head())

# %% [markdown]
# ## 5. Integração EPE + ANEEL

# %%
base = epe_mensal.merge(tarifa_mensal, on="Mes", how="inner")
base = base.sort_values("Mes").reset_index(drop=True)
base["Data"] = base["Mes"].dt.to_timestamp()
base["Ano"] = base["Data"].dt.year
base["Numero_Mes"] = base["Data"].dt.month

print("Observações integradas:", len(base))
print("Período:", base["Data"].min(), "até", base["Data"].max())
display(base.head(10))
display(base.isna().sum())

# %% [markdown]
# ### Checagens antes de modelar
# 
# A regressão só deve continuar se houver observações suficientes e variação nas variáveis. A média tarifária nacional aqui é **não ponderada**: cada linha tarifária tem o mesmo peso, mesmo que distribuidoras tenham tamanhos muito diferentes. A quantidade de registros por mês ajuda a auditar a cobertura, mas não é peso de mercado.

# %%
if len(base) < 12:
    raise ValueError("Há menos de 12 meses integrados. Revise os filtros e a cobertura tarifária.")

display(base[[
    "Consumo_MWh", "Media_TUSD_R_MWh", "Media_TE_R_MWh",
    "Media_Tarifa_Total_R_MWh", "Qtd_Registros_Tarifarios"
]].describe())

fig, ax = plt.subplots(figsize=(13, 4))
ax.plot(base["Data"], base["Consumo_MWh"], marker="o")
ax.set_title("Consumo mensal nacional de energia — EPE")
ax.set_xlabel("Mês")
ax.set_ylabel("Consumo (MWh)")
ax.grid(alpha=.3)
plt.show()

# %% [markdown]
# ## 6. Análise exploratória da relação entre tarifa e consumo

# %%
fig, axes = plt.subplots(1, 2, figsize=(13, 4))
sns.scatterplot(data=base, x="Media_Tarifa_Total_R_MWh", y="Consumo_MWh", ax=axes[0])
axes[0].set_title("Consumo × tarifa média total")
axes[0].set_xlabel("Tarifa média (R$/MWh)")
axes[0].set_ylabel("Consumo (MWh)")

sns.lineplot(data=base, x="Data", y="Media_Tarifa_Total_R_MWh", ax=axes[1], label="Tarifa")
axes[1].set_title("Evolução da tarifa média")
axes[1].set_xlabel("Mês")
axes[1].set_ylabel("R$/MWh")
axes[1].tick_params(axis="x", rotation=45)
plt.tight_layout()
plt.show()

display(base[[
    "Consumo_MWh", "Media_TUSD_R_MWh", "Media_TE_R_MWh",
    "Media_Tarifa_Total_R_MWh"
]].corr())

# %% [markdown]
# ## 7. Regressão Linear Múltipla — modelo exploratório
# 
# **Variável-alvo (y):** consumo mensal nacional (MWh).
# 
# **Variáveis explicativas (X):** média mensal de TUSD e TE (R$/MWh).
# 
# O modelo não inclui tendência, sazonalidade, temperatura, renda, atividade econômica ou população. Assim, os resultados são uma primeira exploração e podem sofrer confundimento e autocorrelação temporal.

# %%
X = base[["Media_TUSD_R_MWh", "Media_TE_R_MWh"]]
y = base["Consumo_MWh"]

modelo = LinearRegression()
modelo.fit(X, y)

base["Consumo_Previsto"] = modelo.predict(X)
print("Intercepto:", modelo.intercept_)
print("Coeficientes:")
display(pd.DataFrame({
    "Variavel": X.columns,
    "Coeficiente": modelo.coef_
}))
print("R² na amostra completa:", modelo.score(X, y))

# %% [markdown]
# ## 8. Avaliação temporal (treino no passado, teste no período mais recente)

# %%
# Não embaralhamos a série temporal. Os 20% finais ficam para teste.
n_teste = max(3, int(np.ceil(len(base) * 0.20)))
if len(base) - n_teste < 6:
    raise ValueError("Poucos meses para separar treino e teste temporal.")

X_treino, X_teste = X.iloc[:-n_teste], X.iloc[-n_teste:]
y_treino, y_teste = y.iloc[:-n_teste], y.iloc[-n_teste:]

modelo_teste = LinearRegression()
modelo_teste.fit(X_treino, y_treino)
previsoes = modelo_teste.predict(X_teste)

metricas = pd.DataFrame({
    "Métrica": ["R²", "MAE (MWh)", "RMSE (MWh)"],
    "Valor": [
        r2_score(y_teste, previsoes),
        mean_absolute_error(y_teste, previsoes),
        mean_squared_error(y_teste, previsoes) ** 0.5
    ]
})
display(metricas)

resultado_teste = pd.DataFrame({
    "Data": base["Data"].iloc[-n_teste:].values,
    "Consumo_Real_MWh": y_teste.values,
    "Consumo_Previsto_MWh": previsoes
})
display(resultado_teste)

# %%
plt.figure(figsize=(12, 5))
plt.plot(base["Data"].iloc[-n_teste:], y_teste.values, marker="o", label="Real")
plt.plot(base["Data"].iloc[-n_teste:], previsoes, marker="o", label="Previsto")
plt.title("Consumo real × previsto — conjunto de teste temporal")
plt.xlabel("Mês")
plt.ylabel("Consumo (MWh)")
plt.legend()
plt.grid(alpha=.3)
plt.show()

# %% [markdown]
# ## 9. Diagnóstico e interpretação
# 
# - **Coeficiente positivo:** associação positiva condicional às outras variáveis do modelo.
# - **Coeficiente negativo:** associação negativa condicional às outras variáveis.
# - **R²:** proporção da variação do consumo explicada pelo modelo na amostra avaliada.
# - **MAE/RMSE:** erro médio das previsões, em MWh.
# 
# Não interprete coeficientes como efeito causal. TUSD e TE podem ser correlacionadas entre si; o consumo também depende de clima, renda, atividade econômica, calendário e tendências. Como a série é curta e temporal, uma regressão simples pode capturar tendências comuns em vez de uma relação econômica real.

# %% [markdown]
# ## 10. Próximas melhorias recomendadas
# 
# 1. Obter EPE mensal em formato tabular por **região/UF, classe e tipo de consumidor**, e não apenas a tabela dinâmica agregada usada nesta primeira versão.
# 2. Relacionar cada distribuidora ANEEL à sua área de concessão (UF/municípios) e calcular tarifas compatíveis com a geografia EPE.
# 3. Selecionar modalidade, classe, subgrupo e posto tarifário coerentes com cada grupo de consumo.
# 4. Ponderar tarifas pelo número de consumidores ou mercado atendido, quando houver dados adequados.
# 5. Deflacionar tarifas nominais para reais constantes e incluir variáveis de controle (temperatura, renda, atividade econômica e sazonalidade).
# 6. Validar com janela temporal e comparar com modelos de referência (por exemplo, previsão sazonal ingênua).
# 
# **Nota sobre o dicionário EPE:** páginas 1–2 descrevem as tabelas SAM agregadas por região e por UF; páginas 3–6 descrevem o consumo dos 37 setores industriais, disponível desde jan/2012. A aba regional utilizada nesta primeira análise é uma tabela dinâmica de consumo total, não a tabela detalhada por classe.


