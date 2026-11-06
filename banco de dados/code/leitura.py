import pandas as pd
from tkinter import Tk, filedialog

# Abrir janela para selecionar o arquivo
Tk().withdraw()
caminho = filedialog.askopenfilename(
    title="Selecione o arquivo Excel",
    filetypes=[("Arquivos Excel", "*.xlsx *.xls")]
)

# Listar o nome de todas as planilhas
arquivo = pd.ExcelFile(caminho)

print("Planilhas encontradas:")
for planilha in arquivo.sheet_names:
    print(planilha)

    '''
CONSUMO E NUMCONS SAM UF - regiao, subsistema, classe, consumidor, consumo e num de consumidores, Uf
SETOR INDUSTRIAL POR RG
SETOR INDUSTRIAL POR UF
CONSUMO_BEN_RG_1970-1989
CONSUMO_ELETROBRAS_1990-2003
ANALISE CONS NUMCONS SAM
ANALISE CONS NUMCONS SAM UF
ANALISE SETOR IND POR RG
ANALISE SETOR IND POR UF'''