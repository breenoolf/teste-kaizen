# Kaizen Pokémon – Aplicação ETL + Dashboard

Este repositório contém uma aplicação em Python que:

- Consome a API Pokémon protegida por JWT.
- Executa um ETL para extrair e tratar dados de Pokémons e combates.
- Gera arquivos CSV prontos para análise.
- Exibe um dashboard interativo em Streamlit com métricas e gráficos.

## 1. Pré-requisitos

- **Python** 3.10 ou superior instalado no sistema.
- Acesso à internet para consumir a API.
- Opcional: navegador para visualizar o dashboard (aberto automaticamente pelo Streamlit).

No Windows, os comandos abaixo assumem o uso do **PowerShell**.

---

## 2. Clonar o repositório

Em um diretório de sua preferência, execute:

```powershell
git clone https://github.com/breenoolf/teste-kaizen
cd teste-kaizen
```

---

## 3. Criar ambiente virtual e instalar dependências

Na pasta do projeto:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Isso criará um ambiente virtual na pasta `.venv` e instalará as bibliotecas necessárias (`requests`, `python-dotenv`, `pandas`, `streamlit`, etc.).

---

## 4. Configurar variáveis de ambiente (`.env`)

O projeto utiliza um arquivo `.env` na raiz para carregar a URL da API e credenciais.

1. Copie o arquivo de exemplo:

```powershell
Copy-Item .env.example .env
```

2. Edite o arquivo `.env` e preencha com as informações da API:

```env
BASE_URL=SEU_ENDPOINT_DA_API
API_USERNAME=SEU_USUARIO
API_PASSWORD=SUA_SENHA
MAX_COMBATS=3000
FORCE_REFRESH=0
```

**Campos principais:**

- `BASE_URL`: URL base da API Pokémon
- `API_USERNAME` / `API_PASSWORD`: credenciais da API.
- `MAX_COMBATS`: limite aproximado de combates a serem baixados (útil para acelerar o ETL).
- `FORCE_REFRESH`:
	- `0` → usa arquivos brutos já baixados em `data/raw` (mais rápido).
	- `1` → força nova extração completa da API.

> **Importante:** o arquivo `.env` real **não** deve ser versionado. Ele é ignorado por padrão via `.gitignore`.

---

## 5. Executar o ETL

O ETL extrai dados da API, salva JSONs em `data/raw/` e gera CSVs em `data/processed/`.

Com o ambiente virtual ativo:

```powershell
.\.venv\Scripts\Activate.ps1
py -m src.etl
```

Ao final, você deverá ver uma mensagem semelhante a:

```text
ETL concluído:
- pokemon: data\processed\pokemon.csv
- combats: data\processed\combats.csv
- stats: data\processed\pokemon_stats.csv
- by_type: data\processed\pokemon_by_type.csv
```

Arquivos gerados em `data/processed/`:

- `pokemon.csv` – atributos dos Pokémons (stats, tipos, etc.).
- `combats.csv` – histórico de combates.
- `pokemon_stats.csv` – vitórias, derrotas e taxa de vitória por Pokémon.
- `pokemon_by_type.csv` – distribuição de Pokémons por tipo.

Se quiser apenas atualizar os CSVs sem rebaixar tudo da API, mantenha `FORCE_REFRESH=0`.

---

## 6. Executar o Dashboard (Streamlit)

Com o ETL já executado e o ambiente virtual ativo, rode:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run streamlit_app.py
```

O Streamlit abrirá o navegador em algo como:

```text
http://localhost:8501
```

Se não abrir automaticamente, copie o endereço exibido no terminal e acesse pelo navegador.

### Funcionalidades do dashboard

- **Indicadores (cards):**
	- Total de Pokémons.
	- Pokémons que aparecem em combates.
	- Total de combates.

- **Filtros na barra lateral:**
	- Tipo do Pokémon.
	- Atributos numéricos: `Attack`, `Defense`, `HP`, `Speed`.
	- Incluir ou não lendários.
	- Mínimo de combates por Pokémon.

- **Tabelas:**
	- Lista de Pokémons filtrada.
	- Top 10 vencedores.
	- Top 10 perdedores.
	- Tabela completa com vitórias, derrotas, total de combates e taxa de vitória.

- **Gráficos e análises:**
	- Taxa de vitória média por tipo.
	- Correlação entre atributos (Attack, Defense, HP, Speed) e taxa de vitória.
	- Distribuição de Pokémons por tipo.

- **Sugestão de equipe:**
	- Seleção automática de 6 Pokémons com alta taxa de vitória e diversidade de tipos.

- **Downloads:**
	- Botões para baixar os CSVs filtrados de Pokémons e estatísticas diretamente do dashboard.

---

## 7. Estrutura dos principais arquivos

- `src/api_client.py`
	- Responsável por autenticar na API (`/login`) e paginar os endpoints `/pokemon`, `/pokemon/{id}` e `/combats`.
	- Implementa lógica de **retry** e espera em caso de `429 Too Many Requests`.

- `src/etl.py`
	- Orquestra o fluxo de ETL:
		- Extrai dados brutos da API para `data/raw/` com cache e modo incremental.
		- Transforma e agrega os dados, gerando CSVs em `data/processed/`.

- `streamlit_app.py`
	- Carrega os CSVs processados.
	- Aplica filtros interativos e exibe as análises em um dashboard Streamlit.

- `api_smoke_test.py`
	- Script simples para testar rapidamente a autenticação na API e o acesso ao endpoint de Pokémons.

---

## 8. Problemas comuns

- **Erro 401 – Invalid credentials**
	- Verifique se `API_USERNAME` e `API_PASSWORD` no `.env` estão corretos.
	- Confirme se não há espaços extras antes/depois dos valores.

- **Erro 429 – Too Many Requests**
	- A API possui limite de requisições.
	- Use valores menores em `MAX_COMBATS`.
	- Evite rodar o ETL muitas vezes em sequência.

- **Dashboard sem dados**
	- Verifique se o ETL foi executado com sucesso e se os arquivos em `data/processed/` existem.

Caso precise reproduzir o fluxo completo em outro ambiente, basta seguir as seções 2 a 6 deste README.

