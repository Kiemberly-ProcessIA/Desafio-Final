# SYNFST.spec

# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

a = Analysis(
    ['run.py'],  # Ponto de entrada da aplicação
    pathex=[],
    binaries=[],
    datas=[
        # --- CORREÇÃO CRUCIAL ---
        # Copia a pasta 'tesseract-ocr' da raiz do projeto para dentro do pacote.
        ('tesseract-ocr', 'tesseract-ocr'),
        
        # Inclui pastas de dados necessárias para a aplicação
        ('dados/config', 'dados/config'),
        ('app', 'app')
    ] 
    # Coleta automática de arquivos de dados de bibliotecas críticas
    + collect_data_files('gradio', include_py_files=True)
    + collect_data_files('gradio_client', include_py_files=True)
    + collect_data_files('pydantic', include_py_files=True)
    + collect_data_files('langchain_core')
    + collect_data_files('langchain')
    + collect_data_files('langgraph')
    + collect_data_files('fastapi')
    + collect_data_files('uvicorn')
    + collect_data_files('safehttpx')
    + collect_data_files('cv2')
    + collect_data_files('groovy'), # <--- CORREÇÃO: Adiciona os dados do Groovy

    hiddenimports=[
        'langchain_google_genai',
        'langchain_openai',
        'langchain_anthropic',
        'langchain_mistralai',
        'langchain_groq',
        'langchain_community.chat_models',
        'tiktoken_ext.openai_public',
        'pydantic.v1',
        'rarfile',
        'openpyxl'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SYNFST',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # False para não abrir um terminal junto com a interface
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SYNFST',
)