# Este script é o ponto de entrada ÚNICO e OFICIAL da aplicação.
# Tanto para desenvolvimento (executando `python run.py`) quanto para o PyInstaller.
# Ele garante que o pacote 'app' seja encontrado corretamente.

from app.main import demo
import sys
import io

if __name__ == "__main__":
    # ==============================================================================
    # PATCH PARA O ERRO 'isatty' DO UVICORN NO PYINSTALLER
    # Quando console=False, stdout/stderr são None. Isso os substitui por um
    # buffer em memória para evitar que o logger do Uvicorn falhe.
    # ==============================================================================
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()

    # A variável 'demo' é a interface Gradio importada de app/main.py.
    # A chamada .launch() agora vive exclusivamente aqui.
    # --- AJUSTE FINAL PARA PYINSTALLER ---
    # inbrowser=False: Impede que o Gradio tente abrir um navegador, o que pode falhar no .exe.
    # server_name="127.0.0.1": Garante que o servidor rode apenas localmente.
    print("Iniciando servidor Gradio em http://127.0.0.1:7860")
    demo.launch(inbrowser=False, server_name="127.0.0.1")