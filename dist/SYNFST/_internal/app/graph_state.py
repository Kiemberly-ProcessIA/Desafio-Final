# app/graph_state.py

from typing import List, Dict, TypedDict, Optional

# ==============================================================================
# DEFINIÇÃO DO ESTADO DO GRAFO
# ==============================================================================
# Usamos TypedDict para ter um 'contrato' claro sobre quais dados cada agente
# pode esperar encontrar. Isso funciona como um guardrail, pois o editor de código
# (VS Code) nos avisará se tentarmos acessar uma chave que não existe,
# minimizando erros de digitação.
# ==============================================================================

class LoteState(TypedDict):
    """
    Representa o 'contêiner de dados' que flui através do nosso grafo de agentes.
    Ele carrega todas as informações sobre um lote de processamento, desde o início até o fim.
    """
    
    # --- Identificadores do Lote ---
    # O UUID único gerado para este lote de processamento.
    id_lote: str
    
    # O caminho para a pasta temporária onde os arquivos deste lote estão armazenados.
    caminho_lote: str
    
    # --- Estado dos Arquivos ---
    # Uma lista dos dicionários retornados pelo 'agente_guardiao'.
    # Contém informações sobre os arquivos validados, seus nomes originais e padronizados.
    unidades_de_processamento: List[Dict]
    
    # --- Resultados do Processamento ---
    # Um dicionário para armazenar os resultados da extração da IA para cada nota.
    # A chave será o ID interno da nota (ex: 'NF_01') e o valor será o JSON extraído.
    resultados_extracao: Dict[str, Dict]
    
    # --- Controle de Fluxo e Erros (Guardrails) ---
    # Uma mensagem de status geral que pode ser atualizada por cada agente.
    status_geral: str
    
    # Uma lista para acumular mensagens de erro não fatais.
    # Ex: se uma única nota falhar na extração, podemos registrar o erro aqui sem parar o lote inteiro.
    erros: List[str]