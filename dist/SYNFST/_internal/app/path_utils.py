# app/path_utils.py
import sys
import os

def resource_path(relative_path):
    """ Retorna o caminho absoluto para o recurso, funcionando tanto no modo de dev quanto no PyInstaller. """
    try:
        # PyInstaller cria uma pasta temporária e armazena o caminho em _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Se não estiver rodando como um bundle, o base_path é o diretório do nosso script principal
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)