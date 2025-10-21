# app/guardian.py
import os
import zipfile
import rarfile
import shutil

# --- AJUSTE PARA PYINSTALLER ---
# Importa a função de utilidade para encontrar o caminho dos recursos
from .path_utils import resource_path
# Adiciona o caminho do executável UnRAR ao PATH para que 'rarfile' o encontre.
os.environ["PATH"] += os.pathsep + resource_path('bin')

# --- MELHORIA 1: Expandida a lista de extensões válidas ---
EXTENSOES_VALIDAS = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp']

def _descompactar_zip(caminho_completo_zip, caminho_lote):
    """Função auxiliar para descompactar arquivos .zip de forma segura."""
    try:
        with zipfile.ZipFile(caminho_completo_zip, 'r') as zip_ref:
            zip_ref.extractall(caminho_lote)
        os.remove(caminho_completo_zip)
        print(f"Arquivo '{os.path.basename(caminho_completo_zip)}' descompactado com sucesso.")
        return True
    except Exception as e:
        print(f"Erro ao descompactar '{os.path.basename(caminho_completo_zip)}': {e}")
        return False

# --- NOVA FUNÇÃO: Suporte para arquivos .rar ---
def _descompactar_rar(caminho_completo_rar, caminho_lote):
    """Função auxiliar para descompactar arquivos .rar de forma segura."""
    try:
        with rarfile.RarFile(caminho_completo_rar, 'r') as rar_ref:
            rar_ref.extractall(caminho_lote)
        os.remove(caminho_completo_rar)
        print(f"Arquivo '{os.path.basename(caminho_completo_rar)}' descompactado com sucesso.")
        return True
    except rarfile.BadRarFile:
        print(f"Erro: Arquivo '{os.path.basename(caminho_completo_rar)}' não é um RAR válido ou está corrompido.")
        return False
    except Exception as e:
        print(f"Erro inesperado ao descompactar '{os.path.basename(caminho_completo_rar)}': {e}")
        return False

def agente_guardiao(caminho_lote: str) -> dict:
    """
    Processa todos os arquivos em um diretório de lote para validação, descompressão e padronização.
    Agora com suporte a .rar e mais formatos de imagem.
    """
    caminho_quarentena = os.path.join(caminho_lote, "quarentena")
    os.makedirs(caminho_quarentena, exist_ok=True)
    
    # --- MELHORIA 2: Lógica de descompressão primeiro ---
    # Garante que todos os arquivos sejam extraídos antes da validação.
    houve_descompressao = True
    while houve_descompressao:
        houve_descompressao = False
        arquivos_no_lote = os.listdir(caminho_lote)
        for nome_arquivo in arquivos_no_lote:
            caminho_completo = os.path.join(caminho_lote, nome_arquivo)
            if not os.path.isfile(caminho_completo):
                continue

            if nome_arquivo.lower().endswith('.zip'):
                if _descompactar_zip(caminho_completo, caminho_lote):
                    houve_descompressao = True
            elif nome_arquivo.lower().endswith('.rar'):
                if _descompactar_rar(caminho_completo, caminho_lote):
                    houve_descompressao = True
    
    # Segunda passagem: Validar e renomear todos os arquivos após descompressão
    arquivos_validados = []
    arquivos_em_quarentena = []
    contador_validos = 1

    for nome_arquivo in os.listdir(caminho_lote):
        caminho_original_completo = os.path.join(caminho_lote, nome_arquivo)
        if not os.path.isfile(caminho_original_completo):
            continue

        nome_base, extensao = os.path.splitext(nome_arquivo)
        extensao = extensao.lower()

        if extensao in EXTENSOES_VALIDAS:
            novo_nome = f"nota_original_{contador_validos:03d}{extensao}"
            novo_caminho_completo = os.path.join(caminho_lote, novo_nome)
            
            os.rename(caminho_original_completo, novo_caminho_completo)
            
            arquivos_validados.append({
                "nome_original": nome_arquivo,
                "nome_padronizado": novo_nome,
                "caminho": novo_caminho_completo
            })
            contador_validos += 1
        else:
            shutil.move(caminho_original_completo, os.path.join(caminho_quarentena, nome_arquivo))
            arquivos_em_quarentena.append(nome_arquivo)

    return {
        "validados": arquivos_validados,
        "quarentena": arquivos_em_quarentena
    }