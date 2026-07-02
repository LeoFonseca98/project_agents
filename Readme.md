# 🏗️ Agent Services

Agente de IA para montagem de listas de materiais de obra, baseado em composições SINAPI.

## Arquitetura

```
app/
├── main.py                    # Entrypoint FastAPI
├── agents/
│   └── chat_agent.py          # Loop de raciocínio com tool calling (Groq)
├── tools/
│   ├── definitions.py         # Definição das tools expostas à LLM
│   └── executor.py            # Execução das tools chamadas pela LLM
├── repositories/
│   ├── product_repository.py  # Queries de produtos
│   └── service_repository.py  # Queries de serviços e composições
├── services/
│   ├── product_service.py     # Lógica de negócio de produtos
│   └── service_service.py     # Lógica de negócio de serviços
├── schemas/
│   ├── requests.py            # Modelos de entrada
│   └── responses.py           # Modelos de saída
├── database/
│   └── connection.py          # Conexão PostgreSQL
└── frontend/
    └── index.html             # Interface do usuário
```

## Fluxo do Agente

```
Engenheiro → Lista de serviços
    ↓
Groq (tool calling) → search_services(query)
    ↓
Cards de serviço com composição SINAPI
    ↓
Engenheiro seleciona serviço
    ↓
Groq → confirm_selection(service) → search_products(insumo_1)
    ↓
Cards de produto
    ↓
Engenheiro seleciona produto → próximo insumo...
    ↓
finish_list() → Lista final exportável
```

## Setup

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar variáveis de ambiente
cp .env.example .env
# edite o .env com suas credenciais

# 3. Habilitar extensão unaccent no PostgreSQL
sudo -u postgres psql -d backup -c "CREATE EXTENSION IF NOT EXISTS unaccent;"

# 4. Rodar
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Banco de Dados

Tabelas utilizadas:
- `services` — catálogo de serviços com código SINAPI
- `compositions` — composições SINAPI vinculadas aos serviços
- `composition_supplies` — relação composição ↔ insumos
- `supplies` — insumos técnicos (SINAPI)
- `products` — catálogo de produtos comprável

Ligação: `services.sinapi` = `compositions.composition_code`