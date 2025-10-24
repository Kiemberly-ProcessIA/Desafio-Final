# SYNFST - Sistema de Processamento de Documentos Fiscais

![Licença MIT](https://img.shields.io/badge/license-MIT-green)

**Grupo:** ProcessIA  
**Participantes:** Davi | Eduardo | Eliezer | Jacson | Kimberly | Roberto

## Descrição

Desenvolvido para automatizar a extração e o processamento de dados de documentos fiscais, aceitando tanto arquivos PDF quanto imagens. O foco principal é recuperar documentos fiscais de fontes conhecidas e aplicar técnicas avançadas de reconhecimento óptico de caracteres (OCR) e processamento de linguagem natural (NLP) para identificar e extrair informações relevantes.

---

## Principais Funcionalidades

- **Recuperação de documentos fiscais:** Busca e importação de arquivos PDF ou imagens contendo notas fiscais de diferentes fontes.
- **Extração inteligente de dados:** Utiliza OCR para converter imagens em texto e NLP para interpretar e estruturar as informações extraídas dos documentos.
- **Identificação de informações fiscais:**
  - Dados do emitente e destinatário
  - Itens da nota (descrição, quantidade, valor)
  - Impostos (ICMS, IPI, PIS, COFINS, entre outros)
  - Códigos fiscais (CFOP, CST e outros)
- **Geração de relatórios e planilhas:** Exportação dos dados extraídos para formatos compatíveis com sistemas de gestão e escrituração fiscal.
- **Interface intuitiva:** Experiência simples para configuração, upload de documentos e visualização dos resultados.

---

## Público Alvo

Empresas, escritórios de contabilidade, profissionais de automação fiscal e equipes de tecnologia que precisam processar grandes volumes de documentos fiscais (notas fiscais eletrônicas) de forma automatizada, rápida e confiável. Também atende desenvolvedores e analistas que buscam integrar extração inteligente de dados fiscais em seus sistemas, facilitando a escrituração, auditoria e análise tributária.

---

## Justificativa

A crescente demanda por agilidade e precisão no processamento de documentos fiscais tornou-se indispensável em soluções automatizadas. Empresas, escritórios de contabilidade e profissionais da área fiscal enfrentam diariamente o desafio de lidar com grandes volumes de notas fiscais em diferentes formatações. O trabalho manual de extração, conferência e digitação de dados é repetitivo, sujeito a erros e consome tempo valioso que poderia ser dedicado a atividades estratégicas.

O SYNFST foi desenvolvido para transformar esse cenário, proporcionando uma automação eficiente e inteligente do processamento de documentos fiscais. Ao permitir a importação de arquivos, o sistema elimina tarefas manuais, reduz erros humanos e acelera significativamente o fluxo de trabalho. A extração automática de informações relevantes garante maior confiabilidade e facilita a integração com sistemas de gestão.

Além de aumentar a produtividade, o sistema contribui para a redução de custos operacionais, melhora o controle tributário e libera profissionais para focarem em análises e tomadas de decisão.

---

## 🛠️ Detalhamento da Solução

### Principais Funções Desenvolvidas

- 📥 **Importação de Documentos:** Permite ao usuário importar arquivos PDF ou imagens contendo documentos fiscais, diretamente pela interface web.
- ⚡ **Processamento Automático:** Após o upload, o sistema realiza a segmentação dos documentos, identifica múltiplas notas em um mesmo arquivo e prepara o conteúdo para extração.
- 🧠 **Reconhecimento Óptico de Caracteres (OCR):** Aplica OCR para converter imagens ou PDFs digitalizados em texto, garantindo que informações contidas em imagens sejam processadas corretamente.
- 🤖 **Extração Inteligente de Dados:** Utiliza modelos de IA para interpretar o texto extraído e identificar campos relevantes, como dados do emitente, destinatário, itens da nota, impostos e códigos fiscais.
- ✅ **Validação e Enriquecimento dos Dados:** Realiza validações automáticas e, quando necessário, solicita complementação ou correção de informações ao usuário.
- 📊 **Geração de Relatórios e Planilhas:** Exporta os dados extraídos em formatos compatíveis com sistemas de gestão, facilitando a escrituração fiscal e a análise tributária.
- 🛠️ **Configuração de Provedores de IA:** Permite ao usuário configurar diferentes provedores de inteligência artificial para o processamento dos documentos, tornando a solução flexível e adaptável.
- 📋 **Logs e Monitoramento:** Exibe logs detalhados no terminal e permite acompanhamento do processamento para facilitar o diagnóstico de problemas.

---

## 🖥️ Como a Solução é Operada

### Inicialização no Windows

- 💻 **Via Executável:** Navegue até a pasta `dist/SYNFST` e execute `SYNFST.exe`. O sistema abrirá automaticamente a interface web no navegador em `http://127.0.0.1:7860`.
- 🐍 **Via Código Fonte:** Abra o terminal, navegue até a pasta do projeto e execute:

  ```powershell
  python run.py
  ```

  Acesse a interface web pelo navegador em `http://127.0.0.1:7860`.

### Inicialização no Linux

- Certifique-se de ter o Python instalado e todas as dependências configuradas.
- Abra o terminal, navegue até a pasta do projeto e execute:

  ```bash
  python3 run.py
  ```

  Acesse a interface web pelo navegador em `http://127.0.0.1:7860`.

### Fluxo Operacional

1. 📤 **Upload de Documentos:** Pela interface web, selecione e envie arquivos PDF ou imagens para processamento.
2. ⚙️ **Configuração:** Configure as chaves de API dos provedores de IA e ajuste parâmetros conforme necessário.
3. 🔄 **Processamento:** O sistema realiza a extração e validação dos dados automaticamente, exibindo o progresso e os resultados na interface.
4. 📥 **Exportação:** Baixe relatórios ou planilhas com os dados extraídos, prontos para integração com outros sistemas.
5. 📝 **Acompanhamento:** Monitore logs e mensagens de status exibidos no terminal para acompanhamento e resolução de eventuais problemas.

---

## 🏗️ Arquitetura

![Diagrama da Arquitetura](docs/SYNFST.png)
---

## 🧰 Tecnologias Utilizadas

- Python 3.8+
- Gradio (interface web)
- LangGraph (orquestração de agentes IA)
- PyMuPDF (processamento de PDFs)
- Tesseract OCR (extração de texto)
- Pandas (manipulação de dados)
- PyInstaller (empacotamento)
- Modelos de IA: Google Gemini, OpenAI, Anthropic, Mistral, Groq, Ollama

---

## 📄 Licença

Este projeto está licenciado sob a Licença MIT. Consulte o arquivo [LICENSE](./LICENSE) para mais detalhes.

---

## 🤝 Como Contribuir

Contribuições são bem-vindas! Para colaborar com o projeto:

1. Faça um fork deste repositório.
2. Crie uma branch para sua feature ou correção (`git checkout -b minha-feature`).
3. Faça suas alterações e commit (`git commit -m 'Minha contribuição'`).
4. Envie um pull request explicando sua proposta.

Sugestões, melhorias e correções serão analisadas pela equipe ProcessIA.
