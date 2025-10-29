# app/workflow.py

import fitz
import re
from typing import List
from langgraph.graph import StateGraph, END

# --- NOVOS IMPORTS para o OCR dentro do Segmentador ---
import pytesseract
from PIL import Image
import io

from .graph_state import LoteState
from .guardian import agente_guardiao
from .extractor import agente_extrator, enriquecer_dados_acum
from .config_manager import load_config

# ==============================================================================
# NOVA FUNÇÃO AUXILIAR: Extração de texto confiável por página
# ==============================================================================
def _get_texto_confiavel_da_pagina(pagina: fitz.Page) -> str:
    """
    Extrai o texto de uma única página. Se o texto direto for insuficiente,
    aciona o OCR para garantir uma leitura de alta qualidade.
    """
    texto_direto = pagina.get_text("text", sort=True)
    texto_lower = texto_direto.lower()

    # Se o texto for curto ou não contiver palavras fiscais, use OCR
    if len(texto_lower.strip()) < 150 or not any(kw in texto_lower for kw in ["cnpj", "valor", "nota", "r$"]):
        try:
            pix = pagina.get_pixmap(dpi=200) # DPI otimizado para velocidade/precisão
            img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            # Não precisamos do pré-processamento pesado do OpenCV aqui, o Tesseract é suficiente para detecção
            return pytesseract.image_to_string(img_pil, lang='por')
        except Exception as e:
            print(f"  - AVISO: Falha no OCR da página {pagina.number + 1}. Erro: {e}")
            return "" # Retorna vazio em caso de erro no OCR
    return texto_direto

# --- NÓS DO GRAFO ---

def no_guardiao(state: LoteState) -> LoteState:
    print("--- NÓ DO GRAFO: EXECUTANDO AGENTE GUARDIÃO ---")
    resultado_guardian = agente_guardiao(state['caminho_lote'])
    state['unidades_de_processamento'] = resultado_guardian["validados"]
    return state

# ==============================================================================
# NÓ SEGMENTADOR ATUALIZADO
# ==============================================================================
def no_segmentador(state: LoteState) -> LoteState:
    """
    Nó determinístico APRIMORADO. Usa OCR por página se necessário para garantir a
    detecção correta do início de cada nota fiscal em PDFs de múltiplas páginas.
    """
    print("--- NÓ DO GRAFO: EXECUTANDO AGENTE SEGMENTADOR (COM OCR) ---")
    tarefas_de_extracao = []
    arquivos_do_guardiao = state['unidades_de_processamento']

    PALAVRAS_CHAVE_INICIO_NF = [
        "nota fiscal de serviços eletrônica", "nfs-e", "prefeitura municipal de",
        "danfse", "documento auxiliar da nota fiscal"
    ]

    for arquivo_info in arquivos_do_guardiao:
        caminho_arquivo = arquivo_info["caminho"]
        if not caminho_arquivo.lower().endswith(".pdf"):
            tarefas_de_extracao.append({"info_arquivo_original": arquivo_info, "paginas": None})
            continue

        with fitz.open(caminho_arquivo) as doc:
            if len(doc) <= 1:
                tarefas_de_extracao.append({"info_arquivo_original": arquivo_info, "paginas": None})
                continue
            
            print(f"PDF multipágina detectado: {arquivo_info['nome_original']}. Segmentando com OCR sob demanda...")
            paginas_iniciais = [1]

            for i in range(1, len(doc)):
                print(f"  - Analisando página {i + 1}...")
                pagina = doc.load_page(i)
                # Usa a nova função para garantir que temos um texto bom para análise
                texto_pagina = _get_texto_confiavel_da_pagina(pagina).lower()
                
                # Se a página tiver mais de 100 caracteres e uma palavra-chave, é uma nova nota
                if len(texto_pagina.strip()) > 100 and any(keyword in texto_pagina for keyword in PALAVRAS_CHAVE_INICIO_NF):
                    if (i + 1) not in paginas_iniciais:
                        paginas_iniciais.append(i + 1)
            
            print(f"Segmentação encontrou inícios de notas nas páginas: {paginas_iniciais}")

            if len(paginas_iniciais) == 1:
                # Se apenas a página 1 foi encontrada, trate o documento todo como uma unidade
                tarefas_de_extracao.append({
                    "info_arquivo_original": arquivo_info,
                    "paginas": list(range(1, len(doc) + 1))
                })
            else:
                for i, start_page in enumerate(paginas_iniciais):
                    end_page = paginas_iniciais[i+1] - 1 if i + 1 < len(paginas_iniciais) else len(doc)
                    paginas_da_tarefa = list(range(start_page, end_page + 1))
                    tarefas_de_extracao.append({
                        "info_arquivo_original": arquivo_info,
                        "paginas": paginas_da_tarefa
                    })

    state["unidades_de_processamento"] = tarefas_de_extracao
    return state

def no_extrator(state: LoteState) -> LoteState:
    print("--- NÓ DO GRAFO: EXECUTANDO AGENTE EXTRATOR ---")
    resultados = {}
    tarefas = state.get('unidades_de_processamento', [])

    for i, tarefa in enumerate(tarefas):
        info_original = tarefa["info_arquivo_original"]
        paginas = tarefa.get("paginas")
        caminho_arquivo = info_original["caminho"]
        
        dados_ia = agente_extrator(caminho_arquivo, paginas=paginas)
        
        id_nota = f"NF_{i+1:03d}"
        
        info_para_ui = info_original.copy()
        if paginas:
            # Mostra o intervalo de páginas de forma mais clara
            range_str = f"{paginas[0]}" if len(paginas) == 1 else f"{paginas[0]}-{paginas[-1]}"
            info_para_ui["nome_original"] += f" (Págs: {range_str})"
            info_para_ui["paginas"] = paginas

        status = "Aguardando Validação"
        if "erro" in dados_ia:
            status = "Erro"

        resultados[id_nota] = {
            "info_arquivo": info_para_ui,
            "dados_extraidos": dados_ia,
            "status": status
        }
    
    state['resultados_extracao'] = resultados
    return state
    
def no_enriquecimento(state: LoteState) -> LoteState:
    print("--- NÓ DO GRAFO: EXECUTANDO AGENTE DE ENRIQUECIMENTO ---")
    config = load_config()
    caminho_map_acum = config.get("acum_mapping_file")
    resultados = state.get('resultados_extracao', {})

    for id_nota, dados_nota in resultados.items():
        # Pula o enriquecimento se a extração falhou
        if dados_nota.get("status") == "Erro":
            continue

        dados_ia = dados_nota['dados_extraidos']
        
        if caminho_map_acum:
            dados_ia = enriquecer_dados_acum(dados_ia, caminho_map_acum)
            
        codigo_servico = dados_ia.get("codigo_servico", "")
        if codigo_servico and not dados_ia.get("item"):
            dados_ia['item'] = f"SERV.{re.sub(r'[^0-9]', '', str(codigo_servico))}"
            
        resultados[id_nota]['dados_extraidos'] = dados_ia

    state['resultados_extracao'] = resultados
    state['status_geral'] = "Enriquecimento finalizado."
    return state

# --- CONSTRUÇÃO DO GRAFO (sem alterações) ---
workflow = StateGraph(LoteState)
workflow.add_node("guardiao", no_guardiao)
workflow.add_node("segmentador", no_segmentador)
workflow.add_node("extrator", no_extrator)
workflow.add_node("enriquecimento", no_enriquecimento)

workflow.set_entry_point("guardiao")
workflow.add_edge("guardiao", "segmentador")
workflow.add_edge("segmentador", "extrator")
workflow.add_edge("extrator", "enriquecimento")
workflow.add_edge("enriquecimento", END)

app_workflow = workflow.compile()

# --- Bloco de visualização (sem alterações) ---
if __name__ == "__main__":
    try:
        app_workflow.get_graph().draw_png("fluxo_dos_agentes.png")
        print("\n[INFO] Um diagrama do fluxo de agentes foi salvo como 'fluxo_dos_agentes.png'\n")
    except Exception as e:
        print(f"\n[AVISO] Não foi possível gerar a imagem do grafo. Erro: {e}\n")