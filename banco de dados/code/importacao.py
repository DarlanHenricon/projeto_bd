# Importando bibliotecas
import pandas as pd

# Criando caminhos
caminho = 'dados para trabalho/Dados_abertos_Consumo_Mensal_energia.xlsx'

# Lendo o arquivo Excel
df = pd.read_excel(caminho)
#print(df.columns)
#Index(['Data', 'DataExcel', 'Regiao', 'Sistema', 'Classe', 'TipoConsumidor','Consumo', 'Consumidores', 'DataVersao']

#Criação de variáveis pra cada coluna para analises
data_df = df['Data']
data_excel_df = df['DataExcel']
regiao_df = df['Regiao']
sistema_df = df['Sistema']
classe_df = df['Classe']
tipo_consumidor_df = df['TipoConsumidor']
consumo_df = df['Consumo']
consumidores_df = df['Consumidores']
data_versao_df = df['DataVersao']

# Entendendo tipos de dados de variáveis
print(consumidores_df.dtypes)


