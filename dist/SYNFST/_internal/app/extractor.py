# app/extractor.py

# app/extractor.py

import os
import io
import re
from typing import List, Optional

import fitz
import pytesseract
import pandas as pd
from PIL import Image
from dotenv import load_dotenv
import numpy as np
import cv2

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_mistralai import ChatMistralAI
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from langchain_community.chat_models import ChatOllama

from .path_utils import resource_path
from .config_manager import load_config

# --- AJUSTE PARA PYINSTALLER ---
# Importa a nova função de utilidade para encontrar o caminho dos recursos
from .path_utils import resource_path
from .config_manager import load_config

# --- Configuração do Tesseract (AGORA À PROVA DE DEPLOY) ---
# Esta lógica agora tenta encontrar o Tesseract dentro do pacote do PyInstaller primeiro.
# Se não encontrar, tenta o caminho padrão do sistema. Isso garante que funcione
# tanto em modo de desenvolvimento quanto no executável distribuído.
try:
    caminho_tesseract_exe = resource_path(os.path.join("tesseract-ocr", "tesseract.exe"))
    if os.path.exists(caminho_tesseract_exe):
        pytesseract.pytesseract.tesseract_cmd = caminho_tesseract_exe
    else:
        # Fallback para a instalação padrão do sistema
        caminho_fallback = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(caminho_fallback):
            pytesseract.pytesseract.tesseract_cmd = caminho_fallback
        else:
            print("AVISO: O executável do Tesseract não foi encontrado em nenhum dos caminhos esperados.")
except Exception as e:
    print(f"AVISO: Ocorreu um erro ao configurar o caminho do Tesseract: {e}")


load_dotenv()

# --- Modelo Pydantic (Schema de Dados) ---
class CampoValor(BaseModel):
    chave: str = Field(description="O nome (chave) do campo extraído do documento.")
    valor: Optional[str] = Field(None, description="O valor correspondente ao campo.")

class NotaFiscalDetalhada(BaseModel):
    # (A estrutura Pydantic completa que definimos anteriormente)
    prestador_cnpj: Optional[str] = Field(None, description="CNPJ do prestador de serviços.")
    prestador_razao_social: Optional[str] = Field(None, description="Razão Social ou Nome do prestador de serviços.")
    prestador_municipio: Optional[str] = Field(None, description="Município (Cidade) do endereço do prestador.")
    prestador_uf: Optional[str] = Field(None, description="UF (sigla do estado com 2 letras) do endereço do prestador.")
    tomador_cnpj: Optional[str] = Field(None, description="CNPJ do tomador de serviços.")
    tomador_razao_social: Optional[str] = Field(None, description="Razão Social ou Nome do tomador de serviços.")
    tomador_municipio: Optional[str] = Field(None, description="Município (Cidade) do endereço do tomador.")
    tomador_uf: Optional[str] = Field(None, description="UF (sigla do estado com 2 letras) do endereço do tomador.")
    numero_nf: Optional[str] = Field(None, description="Número da Nota Fiscal.")
    data_emissao: Optional[str] = Field(None, description="Data de emissão da nota (formato original do documento).")
    codigo_servico: Optional[str] = Field(None, description="Código do serviço prestado (CNAE ou LC 116).")
    valor_total: Optional[str] = Field(None, description="Valor total da nota, também conhecido como Valor Líquido.")
    base_calculo_iss: Optional[str] = Field(None, description="Valor da Base de Cálculo do ISS.")
    aliquota_iss: Optional[str] = Field(None, description="Alíquota do ISS (ex: '5,00%').")
    valor_iss: Optional[str] = Field(None, description="Valor do ISS Retido ou devido.")
    aliquota_pis: Optional[str] = Field(None, description="Alíquota do PIS em porcentagem. Ex: '0,65%'")
    valor_pis: Optional[str] = Field(None, description="Valor do PIS retido.")
    aliquota_cofins: Optional[str] = Field(None, description="Alíquota da COFINS em porcentagem. Ex: '3,00%'")
    valor_cofins: Optional[str] = Field(None, description="Valor da COFINS retida.")
    aliquota_csll: Optional[str] = Field(None, description="Alíquota da CSLL em porcentagem. Ex: '1,00%'")
    valor_csll: Optional[str] = Field(None, description="Valor da CSLL retida.")
    valor_ir: Optional[str] = Field(None, description="Valor do Imposto de Renda (IR) retido.")
    valor_inss: Optional[str] = Field(None, description="Valor do INSS retido.")
    discriminacao_servicos: Optional[str] = Field(None, description="Descrição detalhada dos serviços prestados.")
    observacoes_nf: Optional[str] = Field(None, description="Qualquer texto livre nos campos 'Observações' ou 'Dados Adicionais'.")
    todos_os_campos: List[CampoValor] = Field(default_factory=list, description="Uma lista de pares chave/valor que NÃO foram mapeados para os outros campos.")

# ==============================================================================
# NOVA FUNÇÃO: Pré-processamento de Imagem com OpenCV para Melhorar o OCR
# ==============================================================================
def _corrigir_inclinacao(img_cv):
    """Alinha a imagem para corrigir rotações de digitalização (deskew)."""
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = img_cv.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(img_cv, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(255,255,255))
    return rotated ()

def _pre_processar_imagem_para_ocr(img: Image.Image) -> Image.Image:
    """
    Aplica uma série de filtros do OpenCV para limpar a imagem,
    melhorando a precisão do Tesseract em documentos digitalizados.
    """
    # Converte a imagem PIL para o formato que o OpenCV usa (numpy array)
    img_cv = np.array(img)
    
    # 1. Converte para escala de cinza (essencial para OCR)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # 2. Binarização: Transforma a imagem em apenas preto e branco.
    #    O threshold adaptativo é excelente para documentos com iluminação irregular.
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY, 11, 2)
    
    # 3. Remoção de Ruído (opcional, mas bom para digitalizações de baixa qualidade)
    denoised = cv2.medianBlur(binary, 3)
    
    # Converte a imagem de volta para o formato PIL para o Pytesseract
    return Image.fromarray(denoised)

# --- Motores de Extração de Texto (Função principal alterada) ---
def _extrair_texto_localmente(caminho_arquivo: str, paginas: List[int] = None) -> str:
    print(f"Iniciando extração de texto LOCAL para: {caminho_arquivo} (Páginas: {paginas or 'Todas'})")
    texto_completo = ""
    # Define a configuração do Tesseract que usaremos
    tesseract_config = '--psm 6'

    try:
        extensao = os.path.splitext(caminho_arquivo)[1].lower()
        if extensao == '.pdf':
            with fitz.open(caminho_arquivo) as doc:
                paginas_a_processar = paginas if paginas else range(1, len(doc) + 1)
                for num_pagina in paginas_a_processar:
                    if num_pagina > len(doc): continue
                    pagina = doc.load_page(num_pagina - 1)
                    texto_completo += pagina.get_text("text", sort=True) + "\n\n"
            
            if len(texto_completo.strip()) < 300:
                print("Texto extraído é curto. Acionando OCR forçado para PDF...")
                texto_ocr = ""
                with fitz.open(caminho_arquivo) as doc:
                    paginas_a_processar = paginas if paginas else range(1, len(doc) + 1)
                    for i, num_pagina in enumerate(paginas_a_processar):
                        if num_pagina > len(doc): continue
                        print(f"  - Processando página {num_pagina} com OCR aprimorado...")
                        pagina = doc.load_page(num_pagina - 1)
                        pix = pagina.get_pixmap(dpi=300)
                        img_pil = Image.open(io.BytesIO(pix.tobytes()))
                        img_processada = _pre_processar_imagem_para_ocr(img_pil)
                        
                        # --- CORREÇÃO APLICADA AQUI ---
                        texto_ocr += pytesseract.image_to_string(img_processada, lang='por', config=tesseract_config) + "\n\n"
                texto_completo = texto_ocr

        elif extensao in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
            print("Processando arquivo de imagem com OCR aprimorado...")
            img_pil = Image.open(caminho_arquivo)
            img_processada = _pre_processar_imagem_para_ocr(img_pil)
            
            # --- CORREÇÃO APLICADA AQUI ---
            texto_completo = pytesseract.image_to_string(img_processada, lang='por', config=tesseract_config)

        return texto_completo.strip()
    except Exception as e:
        print(f"Erro na extração local: {e}")
        return f"ERRO_NA_EXTRACAO_LOCAL: {e}"


def enriquecer_dados_acum(dados_extraidos: dict, caminho_planilha_map: str) -> dict:
    if not caminho_planilha_map or not os.path.exists(caminho_planilha_map):
        return dados_extraidos
    codigo_servico_nf = dados_extraidos.get("codigo_servico")
    if not codigo_servico_nf:
        return dados_extraidos
    try:
        print(f"Enriquecendo dados com a planilha: {caminho_planilha_map}")
        df_map = pd.read_excel(caminho_planilha_map, dtype={'Referência': str})
        df_map.columns = df_map.columns.str.strip()
        if 'Referência' not in df_map.columns or 'ACUMULADOR TOMADOS' not in df_map.columns:
            print(f"AVISO: A planilha de mapeamento não contém as colunas 'Referência' e 'ACUMULADOR TOMADOS'.")
            return dados_extraidos
        codigo_servico_nf_str = str(codigo_servico_nf).strip()
        resultado = pd.DataFrame()
        if not codigo_servico_nf_str.isspace() and codigo_servico_nf_str:
             resultado = df_map.loc[df_map['Referência'].str.strip() == codigo_servico_nf_str]
        if resultado.empty:
            df_map['Referencia_Normalizada'] = df_map['Referência'].astype(str).str.replace(r'\D', '', regex=True)
            codigo_servico_normalizado = re.sub(r'\D', '', codigo_servico_nf_str)
            if codigo_servico_normalizado:
                resultado = df_map.loc[df_map['Referencia_Normalizada'] == codigo_servico_normalizado]
        if not resultado.empty:
            valor_acum = resultado['ACUMULADOR TOMADOS'].iloc[0]
            if pd.isna(valor_acum):
                dados_extraidos['acum'] = ""
                print(f"AVISO: Código '{codigo_servico_nf}' encontrado, mas o valor 'ACUM' está vazio.")
            else:
                dados_extraidos['acum'] = str(int(valor_acum))
                print(f"Campo 'acum' preenchido com '{dados_extraidos['acum']}' para o código '{codigo_servico_nf}'.")
    except Exception as e:
        print(f"AVISO: Não foi possível processar a planilha de mapeamento 'Acum'. Erro: {e}")
    return dados_extraidos

def agente_extrator(caminho_arquivo: str, paginas: Optional[List[int]] = None) -> dict:
    """Orquestra o processo de extração e estruturação de dados de um arquivo."""
    load_dotenv(override=True)
    print("--- Agente Extrator Acionado ---")
    config = load_config()
    provider = config.get("provider")
    model_name_config = config.get("custom_model", "").strip() or config.get("model")

    texto_bruto = _extrair_texto_localmente(caminho_arquivo, paginas=paginas)

    if not texto_bruto or texto_bruto.startswith("ERRO"):
        return {"erro": "Falha na etapa de extração de texto.", "detalhes": texto_bruto}

    # ==============================================================================
    # PONTO DE DEBUG: Imprime o texto bruto enviado ao LLM
    # ==============================================================================
    print("\n" + "="*50)
    print(f"TEXTO BRUTO EXTRAÍDO DE '{os.path.basename(caminho_arquivo)}' (ENVIADO AO LLM):")
    print("="*50)
    print(texto_bruto)
    print("="*50 + "\n")
    # ==============================================================================

    print(f"Extração de texto concluída. Estruturando com: {provider}/{model_name_config}")
    try:
        model = None
        if provider == 'google':
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("A chave de API do Google (GOOGLE_API_KEY) não foi encontrada.")
            # --- LÓGICA ALTERADA ---
            model = ChatGoogleGenerativeAI(
                model=model_name_config, 
                google_api_key=api_key,
                temperature=0.0)
        elif provider == 'openai':
            model = ChatOpenAI(model_name=model_name_config, temperature=0.0, api_key=os.getenv("OPENAI_API_KEY"))
        elif provider == 'anthropic':
            model = ChatAnthropic(model_name=model_name_config, temperature=0.0, api_key=os.getenv("ANTHROPIC_API_KEY"))
        elif provider == 'mistral':
            model = ChatMistralAI(model_name=model_name_config, temperature=0.0, api_key=os.getenv("MISTRAL_API_KEY"))
        elif provider == 'groq':
            model = ChatGroq(model_name=model_name_config, temperature=0.0, api_key=os.getenv("GROQ_API_KEY"))
        elif provider == 'ollama':
            base_url = os.getenv("OLLAMA_BASE_URL")
            if not base_url:
                raise ValueError("A variável OLLAMA_BASE_URL não está definida.")
            model = ChatOllama(model=model_name_config, base_url=base_url, temperature=0.0)
        
        if not model:
            raise ValueError(f"Provedor '{provider}' não suportado.")

        parser = PydanticOutputParser(pydantic_object=NotaFiscalDetalhada)
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", """Você é um sistema de Processamento Inteligente de Documentos (IDP) ultrapreciso, focado em extrair dados de UMA ÚNICA NOTA FISCAL de serviço do Brasil por vez. Sua única função é analisar o texto, que pode ser ruidoso e vir de um OCR, e preencher a estrutura JSON com exatidão.

REGRAS DE OURO:
1.  **FOCO NA TAREFA**: Você receberá o texto de apenas uma nota fiscal. Extraia os dados contidos APENAS neste texto.
2.  **EXTRAÇÃO LITERAL**: Extraia os valores exatamente como aparecem. Não calcule, formate ou altere os dados (ex: se o valor é "R$ 1.233,38", extraia exatamente isso). A formatação será feita depois.
3.  **SEJA RESILIENTE AO OCR**: O texto pode estar mal formatado. "Razão Social/Nome:" pode estar em uma linha e o valor "EMPRESA ABC" em outra. Seu trabalho é conectar a etiqueta ao valor correto, mesmo que estejam distantes.
4.  **PREENCHIMENTO COMPLETO**: Preencha TODOS os campos do JSON. Se um campo não for encontrado no texto, o valor DEVE ser `null`.
5.  **DISCRIMINAÇÃO DO SERVIÇO**: O campo `discriminacao_servicos` deve conter APENAS a descrição textual dos serviços, sem repetir valores que já pertencem a outros campos (como valor total, impostos, etc.).
6.  **APRENDA COM OS EXEMPLOS**: Use os exemplos abaixo como seu guia principal para entender como mapear textos variados e ruidosos para a estrutura JSON correta.

{format_instructions}

--- EXEMPLO 1 (Layout de Campinas, mais direto) ---
[INÍCIO DO TEXTO DE EXEMPLO 1]
PREFEITURA MUNICIPAL DE CAMPINAS
Data e hora de emissão 01/09/2025 16:32:17
EMITENTE PRESTADOR DO SERVIÇO
CPF/CNPJ/NIF 51.304.798/0001-04
Nome / Nome Empresarial UNIODONTO DE CAMPINAS COOPERATIVA ODONTOLOGICA
Endereço AVENIDA BRASIL 200 VL ITAPURA
Municipio CAMPINAS/SP
TOMADOR DO SERVIÇO
CPF/CNPJ/NIF 20.468.244/0001-00
Nome / Nome Empresarial DAFLA APOIO ADMINISTRATIVO LTDA
DESCRIÇÃO DO SERVIÇO PRESTADO
MENSALIDADE
Serviço 04.22-PLANOS DE MEDICINA DE GRUPO OU INDIVIDUAL
Valor total da NFSe Campinas (R$) 528,20
Base de cálculo do ISSQN (R$) 528,20
Aliq. (%) 5,000000
Valor do ISSQN (R$) 26,41
[FIM DO TEXTO DE EXEMPLO 1]

[INÍCIO DO JSON DE EXEMPLO 1]
{{
  "prestador_cnpj": "51.304.798/0001-04",
  "prestador_razao_social": "UNIODONTO DE CAMPINAS COOPERATIVA ODONTOLOGICA",
  "prestador_municipio": "CAMPINAS",
  "prestador_uf": "SP",
  "tomador_cnpj": "20.468.244/0001-00",
  "tomador_razao_social": "DAFLA APOIO ADMINISTRATIVO LTDA",
  "numero_nf": null,
  "data_emissao": "01/09/2025",
  "codigo_servico": "04.22",
  "valor_total": "528,20",
  "base_calculo_iss": "528,20",
  "aliquota_iss": "5,000000",
  "valor_iss": "26,41",
  "discriminacao_servicos": "MENSALIDADE"
}}
[FIM DO JSON DE EXEMPLO 1]

--- EXEMPLO 2 (Layout de Mogi Guaçu, com "Optante do Simples") ---
[INÍCIO DO TEXTO DE EXEMPLO 2]
PREFEITURA MUNICIPAL DE MOGI GUAÇU
NOTA FISCAL ELETRÔNICA DE SERVIÇOS
Número da Nota - Série 000000004593 - E
Data de Emissão 29/09/2025
PRESTADOR DE SERVIÇOS
Nome/Razão Social: PROATIVA ASSESSORIA E CONSULTORIA TECNICA LTDA
CPF/CNPJ:18.023.902/0001-09
Endereço: RUA NUNES PEDROSA, 466 SALA 01, Mogi Guaçu - SP
TOMADOR DE SERVIÇOS
Nome/Razão Social: DAFLA APOIO ADMINISTRATIVO LTDA
CPF/CNPJ:20.468.244/0001-00
DISCRIMINAÇÃO DOS SERVIÇOS
PRESTAÇÃO DE SERVIÇO
Documento Emitido por Optante do Simples Nacional
Código do Serviço 1702-Datilografia, digitação...
Base de cálculo (R$) 2.454,40
Aliquota (%) 4,8712%
Vr do ISS (R$) 119,56
VALOR TOTAL DA NOTA = R$ 2.454,40
[FIM DO TEXTO DE EXEMPLO 2]

[INÍCIO DO JSON DE EXEMPLO 2]
{{
  "prestador_cnpj": "18.023.902/0001-09",
  "prestador_razao_social": "PROATIVA ASSESSORIA E CONSULTORIA TECNICA LTDA",
  "prestador_municipio": "Mogi Guaçu",
  "prestador_uf": "SP",
  "tomador_cnpj": "20.468.244/0001-00",
  "tomador_razao_social": "DAFLA APOIO ADMINISTRATIVO LTDA",
  "numero_nf": "000000004593",
  "data_emissao": "29/09/2025",
  "codigo_servico": "1702",
  "valor_total": "2.454,40",
  "base_calculo_iss": "2.454,40",
  "aliquota_iss": "4,8712%",
  "valor_iss": "119,56",
  "discriminacao_servicos": "PRESTAÇÃO DE SERVIÇO",
  "observacoes_nf": "Documento Emitido por Optante do Simples Nacional"
}}
[FIM DO JSON DE EXEMPLO 2]

--- EXEMPLO 3 (Layout de Osasco, baseado em tabelas e texto de OCR) ---
[INÍCIO DO TEXTO DE EXEMPLO 3]
Nota No.: 8226472
Emitido em: 17/09/2025
PRESTADOR DE SERVIÇOS
Razão Social/Nome: EBAZAR.COM.BR.LTDA
CNPJ/CPF: 03.007.331/0001-41
Município: Osasco UF: SP
TOMADOR DO SERVIÇO
Razão Social/Nome: CASA BRANCA ORGANICA LTDA
CNPJ/CPF: 45.791.858/0001-5
Cód. Serviço 10.02 Agenciamento, corretagem...
DESCRIÇÃO DOS SERVIÇOS E OUTRAS INFORMAÇÕES:
Intermediação de negócios
Valor Serviço Base de Cálculo Aliq. (%): Valor ISS
1.233,38 1.233,38 2,00 24,67
IR (R$): Cofins (R$): CSLL (R$): Valor Total da Nota
INSS (RS): Pis/Pasep (R$): Outros (R$): 1.233,38
[FIM DO TEXTO DE EXEMPLO 3]

[INÍCIO DO JSON DE EXEMPLO 3]
{{
  "prestador_cnpj": "03.007.331/0001-41",
  "prestador_razao_social": "EBAZAR.COM.BR.LTDA",
  "prestador_municipio": "Osasco",
  "prestador_uf": "SP",
  "tomador_cnpj": "45.791.858/0001-5",
  "tomador_razao_social": "CASA BRANCA ORGANICA LTDA",
  "numero_nf": "8226472",
  "data_emissao": "17/09/2025",
  "codigo_servico": "10.02",
  "valor_total": "1.233,38",
  "base_calculo_iss": "1.233,38",
  "aliquota_iss": "2,00",
  "valor_iss": "24,67",
  "valor_pis": null,
  "valor_cofins": null,
  "valor_csll": null,
  "discriminacao_servicos": "Intermediação de negócios"
}}
[FIM DO JSON DE EXEMPLO 3]
"""),
    ("human", "Agora, analise e estruture o seguinte texto extraído de uma nota fiscal:\n\n---\n{texto_documento}\n---")
])
        chain = prompt_template | model | parser
        resultado = chain.invoke({"texto_documento": texto_bruto, "format_instructions": parser.get_format_instructions()})
        resultado_dict = resultado.dict()

        if resultado_dict.get("codigo_servico"):
            codigo_servico_bruto = str(resultado_dict["codigo_servico"])
            codigo_numerico = re.sub(r'\D', '', codigo_servico_bruto)
            codigo_limpo = str(int(codigo_numerico)) if codigo_numerico else ""
            resultado_dict["codigo_servico"] = codigo_limpo
            print(f"Código de serviço normalizado para: '{codigo_limpo}'")

        print("Estruturação com IA concluída com sucesso.")
        return resultado_dict
    except Exception as e:
        print(f"Erro durante a chamada da IA de estruturação: {e}")
        return {"erro": f"Falha na comunicação com a API de IA: {e}"}

# --- Bloco de teste ---
if __name__ == '__main__':
    arquivo_para_teste = "caminho/para/seu/arquivo_de_teste.pdf"
    if os.path.exists(arquivo_para_teste):
        dados_estruturados = agente_extrator(arquivo_para_teste)
        print("\n--- DADOS ESTRUTURADOS (JSON) ---\n")
        print(json.dumps(dados_estruturados, indent=2, ensure_ascii=False))
    else:
        print(f"Arquivo de teste '{arquivo_para_teste}' não encontrado.")