# Barbearia Vintage — Backend

API REST desenvolvida para o case técnico da **Insper Jr. Tech**, responsável por toda a regra de negócio, autenticação e persistência de dados da plataforma de gestão da Barbearia Vintage (clientes, serviços, agendamentos, financeiro e integração de automação via n8n).

## Stack

- **FastAPI** — framework web e geração automática de documentação (Swagger/OpenAPI)
- **SQLAlchemy** — ORM de acesso ao banco de dados
- **SQLite** — banco de dados padrão para desenvolvimento local (`barbearia.db`)
- **PostgreSQL** — suportado como alternativa via `DATABASE_URL` (driver `psycopg` já incluso no `requirements.txt`)
- **JWT** (`python-jose`) — autenticação das rotas protegidas
- **n8n** — automação de confirmação de agendamento, acionada via webhook HTTP

## Arquitetura

```
Frontend (React + Vite)
        ↓ HTTP / REST
Backend (FastAPI)
        ↓
Banco de dados (SQLite / PostgreSQL)
        ↓
Webhook
        ↓
n8n
        ↓
Automação de confirmação
```

- **Frontend**: interface web consumida pelo usuário final, responsável por interação e exibição dos dados (repositório separado, não incluído aqui).
- **Backend** (este repositório): concentra as regras de negócio, autenticação JWT, validações e acesso aos dados via API REST.
- **Banco de dados**: persiste clientes, serviços, agendamentos, usuários e despesas.
- **n8n**: recebe, via webhook, os dados de um novo agendamento e dispara a automação de confirmação (ex.: e-mail/mensagem ao cliente).

## Funcionalidades

- Autenticação de usuário administrativo via JWT
- Cadastro, consulta, atualização e remoção de clientes
- Consulta de serviços oferecidos (corte, barba, corte + barba)
- Criação, consulta, atualização, cancelamento e atualização de status de agendamentos
- Prevenção de conflito de horário na criação/edição de agendamentos
- Dashboard com indicadores operacionais (agendamentos do dia, da semana e serviço mais popular)
- Cadastro e consulta de despesas (produtos, funcionários, aluguel, impostos etc.), filtráveis por mês
- Área financeira protegida por chave de acesso adicional
- Envio automático dos dados do agendamento para um workflow do n8n via webhook

## Como executar localmente

### Pré-requisitos
- Python 3.11+ instalado

### Passo a passo

**Linux / macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

> **Sobre o `.env`:** o arquivo `.env` com as credenciais reais será fornecido separadamente junto à entrega — não é necessário criá-lo manualmente. O arquivo `.env.example` existe apenas como referência das variáveis de ambiente utilizadas pela aplicação.

## Variáveis de ambiente

Referência das variáveis presentes em `.env.example`:

| Variável | Finalidade |
|---|---|
| `DATABASE_URL` | String de conexão do banco de dados (SQLite por padrão; aceita PostgreSQL) |
| `JWT_SECRET` | Chave usada para assinar e validar os tokens JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Tempo de expiração do token de acesso, em minutos |
| `N8N_WEBHOOK_URL` | URL do webhook do n8n para onde os agendamentos são enviados |
| `CORS_ORIGINS` | Origens permitidas a consumir a API (CORS) |
| `ADMIN_EMAIL` | E-mail do usuário administrativo criado automaticamente na inicialização |
| `ADMIN_PASSWORD` | Senha do usuário administrativo criado automaticamente na inicialização |
| `FINANCE_PASSCODE` | Chave de acesso adicional exigida para liberar a área financeira |

As credenciais reais **não** estão documentadas aqui — veja a seção [Credenciais](#credenciais).

## Documentação da API

- **Servidor/API**: `http://localhost:8000`
- **Swagger (documentação interativa)**: `http://localhost:8000/docs`
- **Health check**: `http://localhost:8000/health`

> Acessar apenas `http://localhost:8000` não exibe uma página visual, pois a aplicação não possui uma rota `/`. Para visualizar e testar todos os endpoints de forma interativa, utilize o Swagger em `/docs`.

## Credenciais

As credenciais de acesso (usuário administrativo, `JWT_SECRET`, `FINANCE_PASSCODE` e demais segredos) estão disponíveis no arquivo `.env` fornecido separadamente junto à entrega.

## Financeiro

A área financeira possui uma camada de proteção adicional: além da autenticação JWT padrão, o desbloqueio exige uma chave de acesso extra, validada pelo endpoint `POST /finance/unlock`. Essa chave é definida na variável `FINANCE_PASSCODE` do `.env`.

## Integração com n8n

O arquivo JSON do workflow do n8n será fornecido separadamente junto à entrega.

1. Importar o JSON no n8n.
2. Configurar as credenciais necessárias no workflow.
3. Ativar o workflow.
4. Configurar a URL do webhook gerada pelo n8n na variável `N8N_WEBHOOK_URL` do `.env`.
5. Ao criar um novo agendamento (`POST /appointments`), o backend envia automaticamente, em segundo plano, os dados do agendamento para essa URL, disparando a automação de confirmação.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| POST | `/auth/login` | Login e emissão de token JWT |
| POST | `/auth/token` | Login via formulário OAuth2 (uso exclusivo do botão *Authorize* do Swagger) |
| GET | `/clients` | Listar clientes |
| POST | `/clients` | Criar cliente |
| PUT | `/clients/{id}` | Atualizar cliente |
| DELETE | `/clients/{id}` | Remover cliente |
| GET | `/services` | Listar serviços |
| GET | `/appointments` | Listar agendamentos |
| POST | `/appointments` | Criar agendamento |
| PUT | `/appointments/{id}` | Atualizar agendamento |
| PATCH | `/appointments/{id}/status` | Atualizar status do agendamento |
| DELETE | `/appointments/{id}` | Remover agendamento |
| GET | `/expenses` | Listar despesas |
| POST | `/expenses` | Criar despesa |
| PUT | `/expenses/{id}` | Atualizar despesa |
| DELETE | `/expenses/{id}` | Remover despesa |
| POST | `/finance/unlock` | Validar chave de acesso do financeiro |
| GET | `/dashboard` | Obter indicadores do painel |
| GET | `/health` | Verificar status da API |

## Ordem recomendada para o avaliador

1. Configurar o `.env` e iniciar o backend (`uvicorn app.main:app --reload`).
2. Verificar a API pelo Swagger em `http://localhost:8000/docs`.
3. Configurar e iniciar o frontend em outro terminal.
4. Importar e configurar o workflow do n8n, caso queira testar a automação de confirmação.
5. Manter backend e frontend rodando simultaneamente durante a avaliação.
