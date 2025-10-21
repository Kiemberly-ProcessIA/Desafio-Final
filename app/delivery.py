import os
import pandas as pd
import shutil
import zipfile
import re
from datetime import datetime
from dotenv import load_dotenv

from .config_manager import load_config
from langchain_google_vertexai import ChatVertexAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_mistralai import ChatMistralAI
from langchain_groq import ChatGroq
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

load_dotenv()

# --- FUNÇÕES AUXILIARES DE LIMPEZA E FORMATAÇÃO (sem alterações) ---

def _limpar_cnpj(cnpj_str: str) -> str:
    """Remove caracteres não numéricos de uma string de CNPJ."""
    if not isinstance(cnpj_str, str):
        return ""
    return re.sub(r'\D', '', cnpj_str)

def _formatar_data_br(data_str: str) -> str | None:
    """Tenta converter uma data em vários formatos para DD/MM/AAAA."""
    if not data_str or not isinstance(data_str, str):
        return None
    # Formatos a serem tentados, do mais específico para o mais geral
    formatos_data = [
        '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d',
        '%d/%m/%y', '%d-%m-%y', '%y-%m-%d'
    ]
    # Remove qualquer informação de horário que possa ter sido extraída junto com a data.
    data_limpa = data_str.strip().split(' ')[0]

    for fmt in formatos_data:
        try:
            return datetime.strptime(data_limpa, fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    # Se nenhum formato funcionou, retorna a string original se parecer uma data
    if re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', data_limpa):
        return data_limpa
    return None

def _limpar_e_converter_valor(valor) -> float | None:
    """Limpa e converte uma string de valor monetário para float."""
    if valor is None:
        return None
    valor_str = str(valor).strip()
    # Remove 'R$', espaços, e troca vírgula por ponto
    valor_str = valor_str.replace('R$', '').strip()
    # Remove separadores de milhar (ponto)
    valor_str = valor_str.replace('.', '')
    # Troca a vírgula decimal por ponto
    valor_str = valor_str.replace(',', '.')
    try:
        return float(valor_str)
    except (ValueError, TypeError):
        return None

def _limpar_e_converter_aliquota(valor) -> float | None:
    """Limpa e converte uma string de alíquota para float, removendo '%'."""
    if valor is None:
        return None
    valor_str = str(valor).strip().replace('%', '').strip()
    # Troca a vírgula decimal por ponto para conversão
    valor_str = valor_str.replace(',', '.')
    try:
        return float(valor_str)
    except (ValueError, TypeError):
        return None

# --- NOVAS FUNÇÕES AUXILIARES DE FORMATAÇÃO ---

def _formatar_valor_brl(valor) -> str:
    """Converte um valor para float e formata para o padrão monetário brasileiro (ex: 1.234,56)."""
    valor_float = _limpar_e_converter_valor(valor)
    if valor_float is None:
        return ""
    # Usa f-string formatting para adicionar separadores de milhar (_) e duas casas decimais.
    # Depois, substitui os caracteres para o padrão brasileiro.
    return f'{valor_float:_.2f}'.replace('.', ',').replace('_', '.')

def _formatar_aliquota_brl(valor) -> str:
    """Converte uma alíquota para float e formata com vírgula decimal (ex: 5,00)."""
    valor_float = _limpar_e_converter_aliquota(valor)
    if valor_float is None:
        return ""
    # Alíquotas geralmente não precisam de separador de milhar.
    return f'{valor_float:.2f}'.replace('.', ',')

# --- FUNÇÕES DE GERAÇÃO DE ARQUIVOS ---

def renomear_e_mover_arquivos(estado_do_lote: dict, caminho_saida_lote: str) -> list:
    """
    Renomeia os arquivos de nota fiscal com base nos dados extraídos e os move para a pasta de saída.
    Formato: <CNPJ_PRESTADOR>_<NUMERO_NF>_<DATA_EMISSAO>.ext
    """
    arquivos_renomeados = []
    for id_nota, dados_nota in estado_do_lote.items():
        if dados_nota.get("status") != "Aprovado":
            continue

        dados = dados_nota["dados_extraidos"]
        info_arquivo = dados_nota["info_arquivo"]
        caminho_original = info_arquivo["caminho"]
        
        # --- CORREÇÃO: Usando CNPJ do PRESTADOR ---
        cnpj = _limpar_cnpj(dados.get("prestador_cnpj", "SEM_CNPJ"))
        numero_nf = dados.get("numero_nf", "SEM_NUM").replace("/", "-")
        data = dados.get("data_emissao", "SEM_DATA").replace("/", "-")
        
        _, extensao = os.path.splitext(info_arquivo["nome_original"])
        
        # Garante que a extensão seja minúscula e válida
        extensao = extensao.lower() if extensao else ".pdf"

        # Limpa caracteres inválidos para nomes de arquivo
        numero_nf_limpo = re.sub(r'[\\/*?:"<>|]', "-", str(numero_nf))
        data_limpa = re.sub(r'[\\/*?:"<>|]', "-", str(data))

        novo_nome = f"{cnpj}_{numero_nf_limpo}_{data_limpa}{extensao}"
        novo_caminho = os.path.join(caminho_saida_lote, novo_nome)
        
        try:
            # Copia a nota inteira se não houver páginas, ou recria o PDF apenas com as páginas certas
            paginas = info_arquivo.get("paginas")
            if paginas and caminho_original.lower().endswith(".pdf"):
                with fitz.open(caminho_original) as doc_origem:
                    with fitz.open() as doc_destino:
                        # fitz é 0-indexado, nossas páginas são 1-indexadas
                        paginas_para_inserir = [p - 1 for p in paginas]
                        doc_destino.insert_pdf(doc_origem, from_page=min(paginas_para_inserir), to_page=max(paginas_para_inserir))
                        doc_destino.save(novo_caminho)
            else:
                shutil.copy(caminho_original, novo_caminho)

            arquivos_renomeados.append(novo_caminho)
        except Exception as e:
            print(f"Erro ao mover/recriar o arquivo {caminho_original}: {e}")
            
    return arquivos_renomeados


def gerar_planilhas_importacao(estado_do_lote: dict, caminho_saida_lote: str) -> dict:
    """
    Gera as planilhas .xlsx e .csv no padrão de importação (Domínio), com ajustes no CSV.
    """
    lista_para_df = []
    for id_nota, dados_nota in estado_do_lote.items():
        if dados_nota.get("status") != "Aprovado":
            continue
            
        dados = dados_nota["dados_extraidos"]

        # Formata a data para o padrão DD/MM/AAAA
        data_formatada = _formatar_data_br(dados.get("data_emissao"))

        linha = {
            "Data Emissão": data_formatada,
            "Número": dados.get("numero_nf"),
            "Cód.": dados.get("codigo_servico"),
            "Item": dados.get("item", ""), # Usa o valor que foi pré-preenchido e validado pelo usuário
            "Acum": dados.get("acum", ""), # Usa o valor salvo pelo usuário, se houver
            "Aliq.(%)": _formatar_aliquota_brl(dados.get("aliquota_iss")),
            "Base(R$)": _formatar_valor_brl(dados.get("base_calculo_iss")),
            "ISS": _formatar_valor_brl(dados.get("valor_iss")),
            "CR": _formatar_valor_brl(dados.get("valor_crf")), # CRF (PIS+COFINS+CSLL) calculado automaticamente
            "IR": _formatar_valor_brl(dados.get("valor_ir")),
            "INSS": _formatar_valor_brl(dados.get("valor_inss")),
            "Valor(R$)": _formatar_valor_brl(dados.get("valor_total")),
            "CNPJ Prest.": _limpar_cnpj(dados.get("prestador_cnpj", "")),
            "Razão Prest.": dados.get("prestador_razao_social"),
            "UF": dados.get("prestador_uf"),
        }
        lista_para_df.append(linha)

    if not lista_para_df:
        # Se não houver dados, cria arquivos vazios com cabeçalho para não dar erro no download
        colunas_importacao = [
            "Data Emissão", "Número", "Cód.", "Item", "Acum", "Aliq.(%)", "Base(R$)", "ISS", "CR", "IR", "INSS", 
            "Valor(R$)", "CNPJ Prest.", "Razão Prest.", "UF"
        ]
        df = pd.DataFrame(columns=colunas_importacao)
    else:
        df = pd.DataFrame(lista_para_df)

    caminho_base = os.path.join(caminho_saida_lote, "planilha_importacao_dominio")
    caminho_xlsx = f"{caminho_base}.xlsx"
    caminho_csv = f"{caminho_base}.csv"
    
    df.to_excel(caminho_xlsx, index=False)
    # Os dados já estão como strings formatadas, então não precisamos do parâmetro 'decimal'.
    df.to_csv(caminho_csv, index=False, sep=';', encoding='utf-8')
    
    return {"xlsx_importacao": caminho_xlsx, "csv_importacao": caminho_csv}

# ==============================================================================
# NOVA FUNÇÃO 1: CONVERSÃO DE CSV PARA TXT
# ==============================================================================
def gerar_txt_de_csv(caminho_csv: str | None, caminho_saida_lote: str) -> str | None:
    """
    Lê um arquivo .csv e o salva como .txt.
    """
    if not caminho_csv or not os.path.exists(caminho_csv):
        return None
        
    caminho_base = os.path.splitext(os.path.basename(caminho_csv))[0]
    caminho_txt = os.path.join(caminho_saida_lote, f"{caminho_base}.txt")
    
    # Simplesmente copia o conteúdo, pois o CSV já está formatado com ponto e vírgula
    shutil.copy(caminho_csv, caminho_txt)
    
    return caminho_txt

# ==============================================================================
# FUNÇÃO DE MAPEAMENTO DE COLUNAS COM IA
# ==============================================================================
def _mapear_colunas_com_ia(colunas_extras: list, colunas_padrao: list) -> dict:
    """Usa um LLM para mapear colunas extras para colunas padrão."""
    try:
        print("Agente de Entrega: Usando IA para normalizar cabeçalhos de auditoria...")
        config = load_config()
        provider = config.get("provider")
        model_name_config = config.get("custom_model", "").strip() or config.get("model")

        model = None
        if provider == 'google':
            model = ChatVertexAI(model_name=model_name_config, project=os.getenv("GCP_PROJECT"), temperature=0.0)
        elif provider == 'openai':
            model = ChatOpenAI(model_name=model_name_config, temperature=0.0, api_key=os.getenv("OPENAI_API_KEY"))
        elif provider == 'anthropic':
            model = ChatAnthropic(model_name=model_name_config, temperature=0.0, api_key=os.getenv("ANTHROPIC_API_KEY"))
        elif provider == 'mistral':
            model = ChatMistralAI(model_name=model_name_config, temperature=0.0, api_key=os.getenv("MISTRAL_API_KEY"))
        elif provider == 'groq':
            model = ChatGroq(model_name=model_name_config, temperature=0.0, api_key=os.getenv("GROQ_API_KEY"))
        elif provider == 'ollama':
            model = ChatOllama(model=model_name_config, base_url=os.getenv("OLLAMA_BASE_URL"), temperature=0.0)

        if not model:
            raise ValueError(f"Provedor '{provider}' não suportado para mapeamento de colunas.")

        parser = JsonOutputParser()
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Você é um especialista em normalização de esquemas de dados. Sua tarefa é analisar uma lista de nomes de colunas ('colunas a mapear') e consolidá-los, mapeando sinônimos e variações para um único nome de coluna canônico e padronizado. O objetivo é reduzir a redundância.

Regras:
1.  **Mapeamento para Padrão**: Primeiro, tente mapear cada coluna de 'colunas a mapear' para a melhor correspondência semântica na lista de 'colunas padrão'. Ex: 'Valor Líquido' -> 'VALOR_TOTAL'.
2.  **Consolidação de Sinônimos**: Para as colunas que NÃO têm correspondência em 'colunas padrão', identifique grupos de sinônimos entre elas. Crie um único nome canônico para cada grupo. O nome canônico deve ser claro, conciso e no formato MAIÚSCULAS_COM_UNDERLINE. Ex: 'LOCAL_DA_PRESTAO' e 'LOCAL_DA_PRESTAO_DO_SERVIO' devem ser mapeados para 'LOCAL_PRESTACAO_SERVICO'.
3.  **Colunas Únicas**: Se uma coluna não tiver correspondência padrão nem sinônimos na lista, normalize-a para o formato MAIÚSCULAS_COM_UNDERLINE.
4.  **Formato de Saída**: O resultado deve ser um dicionário JSON, onde as chaves são as colunas originais de 'colunas a mapear' e os valores são os nomes canônicos de destino.

Exemplo de Consolidação:
- Colunas Padrão: ["TOMADOR_RAZAO_SOCIAL", "VALOR_TOTAL"]
- Colunas a Mapear: ["Nome do Cliente", "Valor Líquido", "LOCAL_DA_PRESTAO", "LOCAL_DA_PRESTAO_DO_SERVIO", "Data de Vencimento"]
- Resultado JSON Esperado: {{
    "Nome do Cliente": "TOMADOR_RAZAO_SOCIAL",
    "Valor Líquido": "VALOR_TOTAL",
    "LOCAL_DA_PRESTAO": "LOCAL_PRESTACAO_SERVICO",
    "LOCAL_DA_PRESTAO_DO_SERVIO": "LOCAL_PRESTACAO_SERVICO",
    "Data de Vencimento": "DATA_VENCIMENTO"
  }}
"""),
            ("human", """Mapeie as seguintes colunas:
Colunas Padrão: {colunas_padrao}
Colunas a Mapear: {colunas_extras}

Responda apenas com o dicionário JSON resultante.""")
        ])
        
        chain = prompt | model | parser
        mapping = chain.invoke({"colunas_padrao": colunas_padrao, "colunas_extras": colunas_extras})
        print("Agente de Entrega: Normalização de cabeçalhos concluída.")
        return mapping
    except Exception as e:
        print(f"AVISO: Falha na normalização de colunas com IA. Usando nomes originais. Erro: {e}")
        fallback_mapping = {}
        for chave in colunas_extras:
             fallback_mapping[chave] = re.sub(r'[^A-Z0-9_]', '', chave.upper().replace(" ", "_"))
        return fallback_mapping

# ==============================================================================
# FUNÇÃO 2: GERAR EXCEL COM DADOS COMPLETOS E NORMALIZADOS
# ==============================================================================
def gerar_excel_completo(estado_do_lote: dict, caminho_saida_lote: str) -> str | None:
    """
    Gera uma planilha Excel com todos os dados extraídos, normalizando colunas e
    formatando valores monetários e alíquotas para auditoria.
    """
    ordem_colunas_padrao = [
        "ID_NOTA_INTERNO", "ARQUIVO_ORIGINAL", "NUMERO_NF", "DATA_EMISSAO",
        "PRESTADOR_CNPJ", "PRESTADOR_RAZAO_SOCIAL", "PRESTADOR_MUNICIPIO", "PRESTADOR_UF",
        "TOMADOR_CNPJ", "TOMADOR_RAZAO_SOCIAL", "TOMADOR_MUNICIPIO", "TOMADOR_UF",
        "VALOR_TOTAL", "BASE_CALCULO_ISS", "ALIQUOTA_ISS", "VALOR_ISS",
        "ALIQUOTA_PIS", "VALOR_PIS", "ALIQUOTA_COFINS", "VALOR_COFINS", "ALIQUOTA_CSLL", "VALOR_CSLL",
        "VALOR_CRF", "VALOR_IR", "VALOR_INSS", "CODIGO_SERVICO", "ITEM", "ACUM",
        "DISCRIMINACAO_SERVICOS", "OBSERVACOES_NF"
    ]
    # O campo "CR" da planilha de importação é mapeado para "VALOR_CRF" aqui.
    # Definimos as colunas que precisam de formatação específica.
    colunas_monetarias = [
        "VALOR_TOTAL", "BASE_CALCULO_ISS", "VALOR_ISS", "VALOR_PIS", "VALOR_COFINS",
        "VALOR_CSLL", "VALOR_CRF", "VALOR_IR", "VALOR_INSS"
    ]
    colunas_aliquota = [
        "ALIQUOTA_ISS", "ALIQUOTA_PIS", "ALIQUOTA_COFINS", "ALIQUOTA_CSLL"
    ]

    # 1. Coletar todas as chaves únicas dos campos extras
    chaves_extras_unicas = set()
    for dados_nota in estado_do_lote.values():
        if dados_nota.get("status") == "Aprovado":
            dados = dados_nota.get("dados_extraidos", {})
            for campo in dados.get("todos_os_campos", []):
                chave_bruta = str(campo.get("chave", "")).strip()
                if chave_bruta:
                    chaves_extras_unicas.add(chave_bruta)

    # 2. Usar IA para obter o mapeamento de colunas
    mapeamento_colunas = {}
    if chaves_extras_unicas:
        mapeamento_colunas = _mapear_colunas_com_ia(list(chaves_extras_unicas), ordem_colunas_padrao)

    # 3. Construir a lista de dados para o DataFrame usando o mapeamento
    lista_para_df_completo = []
    for id_nota, dados_nota in estado_do_lote.items():
        if dados_nota.get("status") == "Aprovado":
            dados = dados_nota["dados_extraidos"]
            info_arquivo = dados_nota["info_arquivo"]
            
            linha_base = {
                "ID_NOTA_INTERNO": id_nota,
                "ARQUIVO_ORIGINAL": info_arquivo.get("nome_original", ""),
            }
            
            for chave, valor in dados.items():
                if chave != "todos_os_campos":
                    linha_base[chave.upper()] = valor
            
            for campo in dados.get("todos_os_campos", []):
                chave_bruta = str(campo.get("chave", "")).strip()
                valor_campo = campo.get("valor")
                
                if chave_bruta in mapeamento_colunas:
                    chave_mapeada = mapeamento_colunas[chave_bruta]
                    if chave_mapeada not in linha_base or pd.isna(linha_base.get(chave_mapeada)) or str(linha_base.get(chave_mapeada,"")).strip() == "":
                         linha_base[chave_mapeada] = valor_campo
            
            lista_para_df_completo.append(linha_base)
            
    # 4. Criar e reordenar o DataFrame
    if not lista_para_df_completo:
        df_completo = pd.DataFrame(columns=ordem_colunas_padrao)
    else:
        df_completo = pd.DataFrame(lista_para_df_completo)
        colunas_existentes_padrao = [col for col in ordem_colunas_padrao if col in df_completo.columns]
        colunas_extras_mapeadas = sorted([col for col in df_completo.columns if col not in colunas_existentes_padrao])
        df_completo = df_completo[colunas_existentes_padrao + colunas_extras_mapeadas]

    # 5. Aplicar formatação monetária e de alíquota nas colunas relevantes
    for col in colunas_monetarias:
        if col in df_completo.columns:
            df_completo[col] = df_completo[col].apply(_formatar_valor_brl)

    for col in colunas_aliquota:
        if col in df_completo.columns:
            df_completo[col] = df_completo[col].apply(_formatar_aliquota_brl)

    caminho_xlsx_completo = os.path.join(caminho_saida_lote, "extracao_completa_auditoria.xlsx")
    df_completo.to_excel(caminho_xlsx_completo, index=False)
    
    return caminho_xlsx_completo

def criar_zip_das_notas(caminho_saida_lote: str, lista_arquivos_renomeados: list) -> str | None:
    """
    Cria um arquivo .zip contendo todas as notas fiscais renomeadas.
    Retorna o caminho para o arquivo .zip ou None se não houver arquivos para compactar.
    """
    if not lista_arquivos_renomeados:
        return None

    caminho_zip = os.path.join(caminho_saida_lote, "notas_fiscais_renomeadas.zip")
    
    with zipfile.ZipFile(caminho_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for caminho_arquivo in lista_arquivos_renomeados:
            if os.path.exists(caminho_arquivo):
                zipf.write(caminho_arquivo, os.path.basename(caminho_arquivo))
    
    return caminho_zip

# ==============================================================================
# NOVA FUNÇÃO ORQUESTRADORA
# ==============================================================================
def agente_entrega_final(estado_do_lote: dict, caminho_saida_lote: str) -> dict:
    """
    Orquestra todas as etapas de entrega: renomear, gerar planilhas, converter e compactar.
    Esta é a única função que o main.py precisará chamar.
    """
    # 1. Renomear e mover arquivos
    arquivos_renomeados = renomear_e_mover_arquivos(estado_do_lote, caminho_saida_lote)
    
    # 2. Gerar planilhas de importação (XLSX e CSV com vírgula)
    caminhos_planilhas_imp = gerar_planilhas_importacao(estado_do_lote, caminho_saida_lote)
    
    # 3. Gerar .txt a partir do .csv
    caminho_txt = gerar_txt_de_csv(caminhos_planilhas_imp.get("csv_importacao"), caminho_saida_lote)
    
    # 4. A geração do excel de auditoria foi removida conforme solicitado.
    # caminho_xlsx_completo = gerar_excel_completo(estado_do_lote, caminho_saida_lote)
    
    # 5. Criar ZIP das notas renomeadas
    caminho_zip = criar_zip_das_notas(caminho_saida_lote, arquivos_renomeados)
    
    # 6. Retornar um dicionário com todos os caminhos dos arquivos gerados
    return {
        "xlsx_importacao": caminhos_planilhas_imp.get("xlsx_importacao"),
        "csv_importacao": caminhos_planilhas_imp.get("csv_importacao"),
        "txt_importacao": caminho_txt,
        "zip_notas": caminho_zip
    }