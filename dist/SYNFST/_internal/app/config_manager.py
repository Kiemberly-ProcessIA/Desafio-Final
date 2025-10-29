# config_manager.py

import json
import os
from dotenv import dotenv_values, set_key

# --- Constantes ---
CONFIG_FILE = 'config.json'
ENV_FILE = '.env'

# ==============================================================================
# ATUALIZAÇÃO 1: Adicionado o provedor 'ollama'
# ==============================================================================
AVAILABLE_MODELS = {
    "google": {
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"], # Nomes para a nova API
        "api_key_name": "GOOGLE_API_KEY",
        "extra_vars": []  # <--- LINHA ALTERADA: Não exige mais o GCP_PROJECT
    },
    "openai": {
        "models": ["gpt-4o", "gpt-4-turbo"],
        "api_key_name": "OPENAI_API_KEY",
        "extra_vars": []
    },
    "anthropic": {
        "models": ["claude-3-5-sonnet-20240620", "claude-3-opus-20240229"],
        "api_key_name": "ANTHROPIC_API_KEY",
        "extra_vars": []
    },
    "mistral": {
        "models": ["mistral-large-latest", "open-mistral-nemo"],
        "api_key_name": "MISTRAL_API_KEY",
        "extra_vars": []
    },
    "groq": {
        "models": ["llama3-70b-8192", "mixtral-8x7b-32768"],
        "api_key_name": "GROQ_API_KEY",
        "extra_vars": []
    },
    # --- NOVO PROVEDOR: OLLAMA ---
    "ollama": {
        "models": ["llama3", "phi3", "mistral"], # Modelos comuns como exemplo
        "api_key_name": None, # Ollama local não requer chave de API
        "extra_vars": ["OLLAMA_BASE_URL"] # A URL do servidor é a configuração principal
    }
}

DEFAULT_CONFIG = {
    "provider": "google",
    "model": "gemini-2.5-flash",
    "custom_model": "",
    "acum_mapping_file": None
}

# --- Funções de Gerenciamento ---

def load_config() -> dict:
    # (Função sem alterações, apenas ajustada para usar o novo default)
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Garante que as chaves mais recentes existam no arquivo de config
            for key, value in DEFAULT_CONFIG.items():
                config.setdefault(key, value)
            return config
    except (json.JSONDecodeError, FileNotFoundError):
        return DEFAULT_CONFIG.copy()

def save_config(provider: str, model: str, custom_model: str = "", acum_mapping_file: str = None):
    # (Função sem alterações)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({"provider": provider, "model": model, "custom_model": custom_model, "acum_mapping_file": acum_mapping_file}, f, indent=2)

def get_env_vars() -> dict:
    # (Função sem alterações)
    if not os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'w') as f: pass
    return dotenv_values(ENV_FILE)

def save_env_vars(vars_to_save: dict):
    # (Função sem alterações)
    for key, value in vars_to_save.items():
        if value is not None and value.strip() != "":
            set_key(ENV_FILE, key, value)
    print(f"Variáveis de ambiente salvas em {ENV_FILE}")

# ==============================================================================
# ATUALIZAÇÃO 2: Lógica de validação genérica e à prova de futuro
# ==============================================================================
def is_config_valid() -> bool:
    """
    Verifica se a configuração atual é válida para o provedor selecionado,
    checando a chave de API e quaisquer variáveis extras necessárias.
    """
    config = load_config()
    env_vars = get_env_vars()
    
    provider = config.get("provider")
    if not provider or provider not in AVAILABLE_MODELS:
        return False
        
    provider_info = AVAILABLE_MODELS[provider]
    
    # 1. Verifica a chave de API principal, se o provedor exigir uma.
    api_key_name = provider_info.get("api_key_name")
    if api_key_name and not env_vars.get(api_key_name):
        return False
        
    # 2. Verifica TODAS as variáveis extras necessárias (ex: GCP_PROJECT, OLLAMA_BASE_URL)
    for extra_var in provider_info.get("extra_vars", []):
        if not env_vars.get(extra_var):
            return False
            
    return True