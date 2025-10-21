import gradio as gr
import os
import uuid
import shutil
from datetime import datetime
import re
import pandas as pd
import fitz
from PIL import Image
import io
import sys
import pytesseract

# ==============================================================================
# HOOK PARA PYINSTALLER - PONTO CRÍTICO PARA O EXECUTÁVEL FUNCIONAR
# ==============================================================================
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
    bundle_dir = sys._MEIPASS
    tesseract_path_in_bundle = os.path.join(bundle_dir, 'tesseract-ocr', 'tesseract.exe')
    if os.path.exists(tesseract_path_in_bundle):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path_in_bundle
else:
    application_path = os.getcwd()
    bundle_dir = os.path.join(os.getcwd(), "app")

# --- Redefinição de Caminhos ---
SAIDA_DIR = os.path.join(application_path, "dados", "saida")
TEMP_DIR = os.path.join(application_path, "dados", "temporario")
CONFIG_DATA_DIR = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd(), "dados", "config")
# ==============================================================================

# --- Arquitetura Modular ---
from app.workflow import app_workflow
from app.graph_state import LoteState

# --- Módulos de Suporte ---
from app.delivery import agente_entrega_final
from app.config_manager import (
    AVAILABLE_MODELS, load_config, save_config, 
    get_env_vars, save_env_vars, is_config_valid
)

# --- Criação de Diretórios ---
os.makedirs(SAIDA_DIR, exist_ok=True)
os.makedirs(CONFIG_DATA_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# --- Constante Central para o Formulário de Edição ---
FORM_FIELD_KEYS = [
    "data_emissao", "numero_nf", "codigo_servico",
    "prestador_cnpj", "prestador_razao_social", "prestador_municipio", "prestador_uf",
    "tomador_cnpj", "tomador_razao_social", "tomador_municipio", "tomador_uf",
    "valor_total", "base_calculo_iss", "aliquota_iss", "valor_iss",
    "aliquota_pis", "valor_pis", "aliquota_cofins", "valor_cofins",
    "aliquota_csll", "valor_csll", "valor_ir", "valor_inss", "valor_crf",
    "item", "acum", "cr",
    "discriminacao_servicos", "observacoes_nf"
]

# --- Funções de Lógica ---

def load_app_state():
    config = load_config()
    env_vars = get_env_vars()
    provider = config.get("provider", "google")
    models = AVAILABLE_MODELS.get(provider, {}).get("models", [])
    model = config.get("model", models[0] if models else None)
    custom_model = config.get("custom_model", "")
    acum_map_path = config.get("acum_mapping_file")
    acum_map_display = os.path.basename(acum_map_path) if acum_map_path and os.path.exists(acum_map_path) else "Nenhum arquivo configurado."
    
    ui_configs = [
        provider, gr.update(choices=models, value=model), custom_model,
        env_vars.get("GCP_PROJECT", ""), env_vars.get("GOOGLE_API_KEY", ""),
        env_vars.get("OPENAI_API_KEY", ""), env_vars.get("ANTHROPIC_API_KEY", ""),
        env_vars.get("MISTRAL_API_KEY", ""), env_vars.get("GROQ_API_KEY", ""),
        env_vars.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        acum_map_display, None
    ]
    
    initial_tab = gr.Tabs(selected=1) if is_config_valid() else gr.Tabs(selected=0)
    return *ui_configs, initial_tab

def atualizar_modelos_disponiveis(provider: str):
    models = AVAILABLE_MODELS.get(provider, {}).get("models", [])
    return gr.Dropdown(choices=models, value=models[0] if models else None, interactive=True)

def salvar_configuracoes(provider, model, custom_model, gcp_project, google_key, openai_key, anthropic_key, mistral_key, groq_key, ollama_url, acum_map_file):
    acum_map_path = load_config().get("acum_mapping_file")
    if acum_map_file is not None:
        caminho_destino = os.path.join(CONFIG_DATA_DIR, os.path.basename(acum_map_file.name))
        shutil.copy(acum_map_file.name, caminho_destino)
        acum_map_path = caminho_destino
    save_config(provider, model, custom_model, acum_mapping_file=acum_map_path)
    env_vars_to_save = {"GCP_PROJECT": gcp_project, "GOOGLE_API_KEY": google_key, "OPENAI_API_KEY": openai_key, "ANTHROPIC_API_KEY": anthropic_key, "MISTRAL_API_KEY": mistral_key, "GROQ_API_KEY": groq_key, "OLLAMA_BASE_URL": ollama_url}
    save_env_vars(env_vars_to_save)
    acum_map_display = os.path.basename(acum_map_path) if acum_map_path and os.path.exists(acum_map_path) else "Nenhum arquivo configurado."
    return "Configurações salvas com sucesso!", acum_map_display, None

def excluir_mapa_acum():
    config = load_config()
    caminho_arquivo_map = config.get("acum_mapping_file")
    if caminho_arquivo_map and os.path.exists(caminho_arquivo_map):
        try:
            os.remove(caminho_arquivo_map)
        except OSError as e:
            print(f"Erro ao excluir o arquivo: {e}")
    save_config(provider=config.get("provider"), model=config.get("model"), custom_model=config.get("custom_model"), acum_mapping_file=None)
    return "Nenhum arquivo configurado.", "Arquivo de mapeamento removido."

def atualizar_dashboard(dados_do_lote: dict):
    if not dados_do_lote: return pd.DataFrame()
    lista_para_df = []
    for id_nota, dados_nota in dados_do_lote.items():
        dados_extraidos = dados_nota.get("dados_extraidos", {})
        info_arquivo = dados_nota.get("info_arquivo", {})
        linha = {"ID da Nota": id_nota, "Arquivo Original": info_arquivo.get("nome_original", "N/A"), "Status": dados_nota.get("status", "N/A"), "CNPJ Prestador": dados_extraidos.get("prestador_cnpj", "Não encontrado"), "Valor Total": dados_extraidos.get("valor_total", "Não encontrado")}
        lista_para_df.append(linha)
    df = pd.DataFrame(lista_para_df)
    if not df.empty:
        df['Status'] = pd.Categorical(df['Status'], ["Aguardando Validação", "Aprovado", "Erro"])
        df = df.sort_values('Status')
    return df

def exibir_detalhes_nota(estado_do_lote: dict, df_visivel: pd.DataFrame, evt: gr.SelectData):
    try:
        num_campos = len(FORM_FIELD_KEYS)
        if evt is None or not estado_do_lote:
            return [None] + [""] * num_campos + [gr.update(visible=False), None]
        id_nota_selecionada = df_visivel.iloc[evt.index[0]]["ID da Nota"]
        dados_completos_nota = estado_do_lote[id_nota_selecionada]
        caminho_arquivo = dados_completos_nota["info_arquivo"]["caminho"]
        imagem_para_exibir = None
        if caminho_arquivo.lower().endswith(".pdf"):
            doc = fitz.open(caminho_arquivo)
            pagina = doc.load_page(0)
            pix = pagina.get_pixmap(dpi=150)
            imagem_para_exibir = Image.open(io.BytesIO(pix.tobytes("png")))
            doc.close()
        else:
            imagem_para_exibir = Image.open(caminho_arquivo)
        dados_extraidos = dados_completos_nota.get("dados_extraidos", {})
        form_values = [dados_extraidos.get(key, "") for key in FORM_FIELD_KEYS]
        return [imagem_para_exibir] + form_values + [gr.update(visible=True), id_nota_selecionada]
    except Exception as e:
        print(f"Erro ao exibir detalhes: {e}")
        return [None] + [""] * len(FORM_FIELD_KEYS) + [gr.update(visible=False), None]

def _limpar_e_converter_valor_para_calculo(valor) -> float:
    if valor is None: return 0.0
    if isinstance(valor, (int, float)): return float(valor)
    valor_str = str(valor).strip()
    if not valor_str: return 0.0
    valor_limpo = re.sub(r'[^\d,.-]', '', valor_str).replace('.', '').replace(',', '.')
    try:
        return float(valor_limpo)
    except (ValueError, TypeError):
        return 0.0

def atualizar_campos_dominio(codigo_servico: str):
    """
    Atualiza dinamicamente os campos 'Item' e 'Acum' com base no 'Código de Serviço'.
    """
    # 1. Atualizar o campo 'Item'
    novo_item = ""
    if codigo_servico:
        codigo_numerico = re.sub(r'[^0-9]', '', str(codigo_servico))
        if codigo_numerico:
            novo_item = f"SERV.{codigo_numerico}"

    # 2. Atualizar o campo 'Acum'
    novo_acum = ""
    config = load_config()
    caminho_map_acum = config.get("acum_mapping_file")

    if caminho_map_acum and os.path.exists(caminho_map_acum) and codigo_servico:
        try:
            df_map = pd.read_excel(caminho_map_acum, dtype=str)
            df_map.columns = [str(c).strip() for c in df_map.columns]
            
            if 'Referência' in df_map.columns and 'ACUMULADOR TOMADOS' in df_map.columns:
                codigo_servico_str = str(codigo_servico).strip()
                
                # Normaliza ambos os lados para comparação (apenas dígitos)
                df_map['Referencia_Normalizada'] = df_map['Referência'].str.replace(r'\D', '', regex=True)
                codigo_servico_normalizado = re.sub(r'\D', '', codigo_servico_str)

                if codigo_servico_normalizado:
                    resultado = df_map.loc[df_map['Referencia_Normalizada'] == codigo_servico_normalizado]
                    if not resultado.empty:
                        valor_acum = resultado['ACUMULADOR TOMADOS'].iloc[0]
                        if valor_acum and not pd.isna(valor_acum):
                            novo_acum = str(int(float(valor_acum)))
        except Exception as e:
            print(f"AVISO: Falha ao buscar 'Acum' dinamicamente. Erro: {e}")
    return gr.update(value=novo_item), gr.update(value=novo_acum)

def salvar_e_aprovar(estado_do_lote, id_nota, *campos_formulario):
    if not id_nota or not estado_do_lote:
        return estado_do_lote, atualizar_dashboard(estado_do_lote), gr.update(interactive=False)
    dados_atualizados = dict(zip(FORM_FIELD_KEYS, campos_formulario))
    valor_pis_num = _limpar_e_converter_valor_para_calculo(dados_atualizados.get("valor_pis"))
    valor_cofins_num = _limpar_e_converter_valor_para_calculo(dados_atualizados.get("valor_cofins"))
    valor_csll_num = _limpar_e_converter_valor_para_calculo(dados_atualizados.get("valor_csll"))
    crf_calculado = valor_pis_num + valor_cofins_num + valor_csll_num
    dados_atualizados["valor_crf"] = f"{crf_calculado:.2f}".replace('.', ',')
    dados_originais = estado_do_lote[id_nota]["dados_extraidos"]
    dados_atualizados["todos_os_campos"] = dados_originais.get("todos_os_campos", [])
    estado_do_lote[id_nota]["dados_extraidos"] = dados_atualizados
    estado_do_lote[id_nota]["status"] = "Aprovado"
    df_atualizado = atualizar_dashboard(estado_do_lote)
    todas_aprovadas = all(v['status'] == 'Aprovado' for v in estado_do_lote.values())
    botao_finalizar_update = gr.update(interactive=todas_aprovadas)
    return estado_do_lote, df_atualizado, gr.update(visible=False), None, botao_finalizar_update

def finalizar_processamento(estado_do_lote):
    id_lote_folder_name = os.path.basename(os.path.dirname(next(iter(estado_do_lote.values()))["info_arquivo"]["caminho"]))
    caminho_saida_lote = os.path.join(SAIDA_DIR, id_lote_folder_name)
    os.makedirs(caminho_saida_lote, exist_ok=True)
    caminhos_finais = agente_entrega_final(estado_do_lote, caminho_saida_lote)
    return "Lote finalizado com sucesso! Faça o download abaixo.", gr.update(visible=True), gr.update(value=caminhos_finais.get("xlsx_importacao"), visible=True), gr.update(value=caminhos_finais.get("csv_importacao"), visible=True), gr.update(value=caminhos_finais.get("txt_importacao"), visible=True), gr.update(value=caminhos_finais.get("zip_notas"), visible=True)

# ==============================================================================
# FUNÇÃO 'processar_lote' CORRIGIDA E COMPLETA
# ==============================================================================
def processar_lote(arquivos, progress=gr.Progress(track_tqdm=True)):
    if not arquivos:
        return "Erro: Nenhum arquivo foi selecionado.", {}, pd.DataFrame(), gr.update(visible=False), gr.update(visible=False), gr.update(interactive=False)
    try:
        progress(0, desc="Iniciando e criando lote...")
        
        # --- BLOCO DE CÓDIGO RESTAURADO ---
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        id_lote_uuid = str(uuid.uuid4())
        nome_pasta_lote = f"lote_{timestamp}_{id_lote_uuid[:8]}"
        caminho_lote = os.path.join(TEMP_DIR, nome_pasta_lote)
        os.makedirs(caminho_lote, exist_ok=True)
        for arquivo_temp in arquivos:
            shutil.copy(arquivo_temp.name, os.path.join(caminho_lote, os.path.basename(arquivo_temp.name)))
        # --- FIM DO BLOCO RESTAURADO ---

        initial_state = LoteState(id_lote=id_lote_uuid, caminho_lote=caminho_lote, unidades_de_processamento=[], resultados_extracao={}, status_geral="Iniciado", erros=[])
        
        print(f"\n🚀 INVOCANDO WORKFLOW (STREAM) PARA O LOTE: {id_lote_uuid} 🚀\n")
        
        total_tarefas = 0
        final_state = {}
        
        # Usando .stream() para receber atualizações em tempo real
        for event in app_workflow.stream(initial_state, {"recursion_limit": 50}):
            node_name, node_output = next(iter(event.items()))
            print(f"--- NÓ CONCLUÍDO: {node_name} ---")

            if node_name == "segmentador":
                total_tarefas = len(node_output.get('unidades_de_processamento', []))
                progress(0.3, desc=f"Segmentação concluída. {total_tarefas} notas identificadas.")
            
            if node_name == "extrator":
                # No stream, o extrator pode ser chamado várias vezes, mas o estado é cumulativo.
                # A cada passo, atualizamos o progresso com base no tamanho atual dos resultados.
                tarefas_concluidas = len(node_output.get('resultados_extracao', {}))
                progresso_extracao = 0.3 + (tarefas_concluidas / total_tarefas) * 0.6 if total_tarefas > 0 else 0.9
                progress(progresso_extracao, desc=f"Agente Extrator: {tarefas_concluidas}/{total_tarefas} notas processadas.")

            if node_name == "enriquecimento":
                progress(0.95, desc="Agente de Enriquecimento: Finalizando dados...")

            # Sempre guardamos o estado mais recente
            final_state = node_output
        
        print(f"\n🏁 WORKFLOW (STREAM) FINALIZADO PARA O LOTE: {id_lote_uuid} 🏁\n")
        
        dados_do_lote = final_state.get('resultados_extracao', {})
        erros_ocorridos = final_state.get('erros', [])
        
        status_messages = [f"Processamento concluído! {len(dados_do_lote)} notas prontas para validação."]
        if erros_ocorridos:
            status_messages.append("\n--- AVISOS / ERROS ---")
            status_messages.extend(erros_ocorridos)
        
        mensagem_final = "\n".join(status_messages)
        df_para_exibir = atualizar_dashboard(dados_do_lote)
        
        return mensagem_final, dados_do_lote, df_para_exibir, gr.update(visible=True), gr.update(visible=False), gr.update(interactive=False)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Erro crítico: {e}", {}, pd.DataFrame(), gr.update(visible=False), gr.update(visible=False), gr.update(interactive=False)

# --- Construção da Interface com Gradio ---
with gr.Blocks(title="SYNFST - Automação Fiscal", theme=gr.themes.Soft()) as demo:
    estado_do_lote = gr.State({})
    id_nota_selecionada_state = gr.State(None)

    gr.Markdown("# SYNFST - Sistema de Automação de Escrituração Fiscal")
    
    with gr.Tabs() as tabs_main:
        with gr.TabItem("Configurações", id=0):
            gr.Markdown("## Configurações do Provedor de IA e Mapeamentos")
            with gr.Row():
                cfg_provider = gr.Dropdown(label="Provedor de IA", choices=list(AVAILABLE_MODELS.keys()))
                cfg_model = gr.Dropdown(label="Modelo")
            cfg_custom_model = gr.Textbox(label="Ou insira um nome de modelo customizado", info="Se preenchido, este modelo será usado no lugar da seleção acima.")
            gr.Markdown("### Chaves de API e Configurações")
            with gr.Group():
                gr.Markdown("#### Google / Vertex AI")
                cfg_gcp_project = gr.Textbox(label="Google Cloud Project ID")
                cfg_google_key = gr.Textbox(label=f"Chave de API Google", type="password")
            with gr.Group():
                gr.Markdown("#### OpenAI")
                cfg_openai_key = gr.Textbox(label=f"Chave de API OpenAI", type="password")
            with gr.Group():
                gr.Markdown("#### Anthropic")
                cfg_anthropic_key = gr.Textbox(label=f"Chave de API Anthropic", type="password")
            with gr.Group():
                gr.Markdown("#### Mistral AI")
                cfg_mistral_key = gr.Textbox(label=f"Chave de API Mistral", type="password")
            with gr.Group():
                gr.Markdown("#### Groq")
                cfg_groq_key = gr.Textbox(label=f"Chave de API Groq", type="password")
            with gr.Group():
                gr.Markdown("#### Ollama (Local)")
                cfg_ollama_url = gr.Textbox(label="Ollama Server Base URL", info="Ex: http://localhost:11434")
            gr.Markdown("### Mapeamento 'De/Para' (Opcional)")
            with gr.Group():
                gr.Markdown("Faça o upload de uma planilha Excel (.xlsx) com as colunas `CODIGO_SERVICO` e `ACUM` para preenchimento automático.")
                with gr.Row():
                    cfg_acum_map_display = gr.Textbox(label="Arquivo de Mapeamento 'Acum' Configurado", interactive=False, scale=4)
                    btn_excluir_mapa = gr.Button("Excluir", variant="stop", scale=1, size="sm")
                cfg_acum_map_upload = gr.File(label="Upload de novo arquivo de mapeamento", file_types=[".xlsx"])
            btn_salvar_cfg = gr.Button("Salvar e Continuar", variant="primary")
            cfg_status = gr.Textbox(label="Status", interactive=False)

        with gr.TabItem("Processamento de Lote", id=1):
            with gr.Row():
                with gr.Column(scale=2):
                    gr.Markdown("### 1. Enviar Arquivos")
                    arquivos_input = gr.File(label="Selecione as Notas Fiscais", file_count="multiple")
                    btn_processar = gr.Button("Iniciar Processamento", variant="primary")
                    output_status = gr.Textbox(label="Status do Processamento", interactive=False, lines=8)
                
                with gr.Column(scale=3, visible=False) as dashboard_col:
                    gr.Markdown("### 2. Validar Dados")
                    df_display = gr.DataFrame(label="Notas Processadas", interactive=True)
                    with gr.Accordion("Editar Nota Selecionada", visible=False) as details_accordion:
                        with gr.Row():
                            image_display = gr.Image(label="Imagem da Nota", interactive=False, height=600, type="pil")
                            with gr.Column():
                                with gr.Group():
                                    gr.Markdown("##### Informações da Nota")
                                    with gr.Row():
                                        form_data_emissao = gr.Textbox(label="Data de Emissão")
                                        form_numero_nf = gr.Textbox(label="Número NF")
                                        form_codigo_servico = gr.Textbox(label="Cód. Serviço")
                                with gr.Group():
                                    gr.Markdown("##### Prestador")
                                    with gr.Row():
                                        form_prestador_cnpj = gr.Textbox(label="CNPJ Prestador")
                                        form_prestador_razao_social = gr.Textbox(label="Razão Social")
                                    with gr.Row():
                                        form_prestador_municipio = gr.Textbox(label="Município")
                                        form_prestador_uf = gr.Textbox(label="UF")
                                with gr.Group():
                                    gr.Markdown("##### Tomador")
                                    with gr.Row():
                                        form_tomador_cnpj = gr.Textbox(label="CNPJ Tomador")
                                        form_tomador_razao_social = gr.Textbox(label="Razão Social")
                                    with gr.Row():
                                        form_tomador_municipio = gr.Textbox(label="Município")
                                        form_tomador_uf = gr.Textbox(label="UF")
                                with gr.Group():
                                    gr.Markdown("##### Valores Municipais (ISS)")
                                    with gr.Row():
                                        form_valor_total = gr.Textbox(label="Valor Total (R$)")
                                        form_base_calculo_iss = gr.Textbox(label="Base ISS (R$)")
                                        form_aliquota_iss = gr.Textbox(label="Alíquota ISS (%)")
                                        form_valor_iss = gr.Textbox(label="Valor ISS")
                                with gr.Group():
                                    gr.Markdown("##### Retenções Federais")
                                    with gr.Row():
                                        form_aliquota_pis = gr.Textbox(label="Alíq. PIS (%)")
                                        form_valor_pis = gr.Textbox(label="Valor PIS (R$)")
                                        form_aliquota_cofins = gr.Textbox(label="Alíq. COFINS (%)")
                                        form_valor_cofins = gr.Textbox(label="Valor COFINS (R$)")
                                    with gr.Row():
                                        form_aliquota_csll = gr.Textbox(label="Alíq. CSLL (%)")
                                        form_valor_csll = gr.Textbox(label="Valor CSLL (R$)")
                                        form_valor_ir = gr.Textbox(label="Valor IR (R$)")
                                        form_valor_inss = gr.Textbox(label="Valor INSS (R$)")
                                    form_valor_crf = gr.Textbox(label="Valor CRF (PIS+COFINS+CSLL)", interactive=False, info="Calculado ao salvar")
                                with gr.Group():
                                    gr.Markdown("##### Campos Domínio")
                                    with gr.Row():
                                        form_item = gr.Textbox(label="Item")
                                        form_acum = gr.Textbox(label="Acum")
                                        form_cr = gr.Textbox(label="CR")
                                with gr.Group():
                                    gr.Markdown("##### Contexto")
                                    form_discriminacao_servicos = gr.Textbox(label="Discriminação dos Serviços", lines=4)
                                    form_observacoes_nf = gr.Textbox(label="Observações", lines=3)
                                btn_aprovar = gr.Button("Salvar e Aprovar", variant="primary")
                    
                    gr.Markdown("### 3. Finalizar e Exportar")
                    btn_finalizar = gr.Button("Finalizar Lote", variant="primary", interactive=False)
                    with gr.Column(visible=False) as download_col:
                        gr.Markdown("#### Downloads:")
                        file_xlsx_imp = gr.File(label="Baixar Planilha de Importação (.xlsx)")
                        file_csv_imp = gr.File(label="Baixar Planilha de Importação (.csv)")
                        file_txt_imp = gr.File(label="Baixar Arquivo de Importação (.txt)")
                        file_zip_notas = gr.File(label="Baixar Notas Renomeadas (.zip)")
    
    # --- Lógica de Eventos ---
    form_components = [
        form_data_emissao, form_numero_nf, form_codigo_servico, form_prestador_cnpj,
        form_prestador_razao_social, form_prestador_municipio, form_prestador_uf, form_tomador_cnpj,
        form_tomador_razao_social, form_tomador_municipio, form_tomador_uf, form_valor_total,
        form_base_calculo_iss, form_aliquota_iss, form_valor_iss,
        form_aliquota_pis, form_valor_pis, form_aliquota_cofins, form_valor_cofins,
        form_aliquota_csll, form_valor_csll, form_valor_ir, form_valor_inss, form_valor_crf,
        form_item, form_acum, form_cr,
        form_discriminacao_servicos, form_observacoes_nf
    ]
    cfg_outputs = [
        cfg_provider, cfg_model, cfg_custom_model, cfg_gcp_project, cfg_google_key, 
        cfg_openai_key, cfg_anthropic_key, cfg_mistral_key, cfg_groq_key, cfg_ollama_url,
        cfg_acum_map_display, cfg_acum_map_upload
    ]
    cfg_inputs = [
        cfg_provider, cfg_model, cfg_custom_model, cfg_gcp_project, cfg_google_key,
        cfg_openai_key, cfg_anthropic_key, cfg_mistral_key, cfg_groq_key, cfg_ollama_url,
        cfg_acum_map_upload
    ]

    # Carregamento Inicial
    demo.load(fn=load_app_state, outputs=[*cfg_outputs, tabs_main])
    
    # Eventos da Aba de Configuração
    cfg_provider.change(fn=atualizar_modelos_disponiveis, inputs=[cfg_provider], outputs=[cfg_model])
    btn_salvar_cfg.click(fn=salvar_configuracoes, inputs=cfg_inputs, outputs=[cfg_status, cfg_acum_map_display, cfg_acum_map_upload]).then(fn=lambda: gr.Tabs(selected=1), outputs=tabs_main)
    btn_excluir_mapa.click(fn=excluir_mapa_acum, inputs=None, outputs=[cfg_acum_map_display, cfg_status])

    # Eventos da Aba de Processamento
    btn_processar.click(fn=processar_lote, inputs=[arquivos_input], outputs=[output_status, estado_do_lote, df_display, dashboard_col, details_accordion, btn_finalizar])
    df_display.select(fn=exibir_detalhes_nota, inputs=[estado_do_lote, df_display], outputs=[image_display, *form_components, details_accordion, id_nota_selecionada_state])
    form_codigo_servico.change(fn=atualizar_campos_dominio, inputs=[form_codigo_servico], outputs=[form_item, form_acum])
    btn_aprovar.click(fn=salvar_e_aprovar, inputs=[estado_do_lote, id_nota_selecionada_state, *form_components], outputs=[estado_do_lote, df_display, details_accordion, id_nota_selecionada_state, btn_finalizar])
    btn_finalizar.click(fn=finalizar_processamento, inputs=[estado_do_lote], outputs=[output_status, download_col, file_xlsx_imp, file_csv_imp, file_txt_imp, file_zip_notas])


if __name__ == "__main__":
    demo.launch()