# Barbearia Vintage — Backend

API REST do case técnico da Insper Jr. Tech.

## Stack
- FastAPI
- SQLAlchemy
- SQLite por padrão / PostgreSQL via `DATABASE_URL`
- JWT
- n8n por webhook

## Funcionalidades
- Login protegido por JWT
- CRUD de clientes
- CRUD de agendamentos
- Atualização de status
- Bloqueio de conflito de horário
- Serviços cadastrados no banco
- Dashboard operacional
- Disparo de webhook para n8n em novo agendamento

## Rodando localmente

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

API: `http://localhost:8000`  
Swagger: `http://localhost:8000/docs`

### Login padrão
- e-mail: `admin@barbeariavintage.com`
- senha: `admin123`

Troque as credenciais no `.env`.

## PostgreSQL

Exemplo:

```env
DATABASE_URL=postgresql+psycopg://usuario:senha@localhost:5432/barbearia
```

## Integração n8n
Importe o workflow entregue em `../n8n/barbearia-vintage-confirmation.json`, ative-o e coloque a URL do webhook em:

```env
N8N_WEBHOOK_URL=http://localhost:5678/webhook/barbearia-vintage-confirmation
```

## Endpoints
- `POST /auth/login`
- `GET/POST /clients`
- `PUT/DELETE /clients/{id}`
- `GET /services`
- `GET/POST /appointments`
- `PUT/DELETE /appointments/{id}`
- `PATCH /appointments/{id}/status`
- `GET /dashboard`
