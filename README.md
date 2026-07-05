# Enterprise Agentic RAG

A production-grade RAG system built with **LangGraph**, **NeMo Guardrails**, **Portkey LLM Gateway**, **RAGAS Evals**, and **Google Cloud Platform**. Deployed as four independent microservices on Cloud Run.

> 📊 **Live architecture, animated**: see [`project_flow_animated.html`](project_flow_animated.html) for an interactive, tabbed diagram of the query flow, the full LangGraph agent graph, and the event-driven ingestion pipeline — generated from the actual deployed code/infra, kept in sync as the system evolves.

---

## Key Features

- **Agentic Intelligence** — LangGraph cyclic graph: Planner → Retriever → Grade Documents → (Rewriter / Web Search) → Context Guard → Responder → Output Guard, with a Clarify escape and a Retrieval-Failure fallback, and persistent memory across sessions
- **Four-Gate Safety** — Gate 1: NeMo Guardrails (blocks jailbreak/off-topic); Gate 2: Redis Semantic Cache (serves cached answers in ~50ms); Gate 3: Retrieval Guard + Context Sanitization (strips prompt-injection from retrieved docs, isolates untrusted context); Gate 4: Output Guard (PII redaction + policy/toxicity validation)
- **Persistent Memory** — LangGraph `PostgresSaver` on Cloud SQL Postgres 15 (`rag-postgres` / `rag_memory`) — conversation history survives container restarts and scale-to-zero; falls back to in-process `MemorySaver` automatically if the pool is unavailable
- **LLM Gateway** — Portkey routes all LLM calls through a **saved gateway config** (`pc-enterp-edad02` — this Portkey org enforces saved-only configs) bundling automatic fallback (Llama 3.3 70B → Llama 3.1 8B), semantic caching, and retries, with cache status readable via the `x-portkey-cache-status` response header
- **Enterprise Search** — Qdrant Cloud vector search + FlashRank local reranker
- **Event-Driven Ingestion** — Upload a file to GCS → Eventarc fires → Ingestion service auto-parses, embeds, and indexes. No manual steps. Verified end-to-end.
- **Evaluation Suite** — RAGAS (5 metrics) + Jaccard Tool Correctness. GCS-persisted history. Deployed as its own Cloud Run service.
- **Full Observability** — Pydantic Logfire + LangSmith traces across every agent node and eval run

---

## Deployment Status (current)

| Service | Cloud Run | Access | Notes |
|---|---|---|---|
| `rag-api` | ✅ live | authenticated (IAM) | backend + LangGraph agent; Postgres + Redis wired and verified |
| `rag-ui` | ✅ live | authenticated (IAM) | Streamlit chat UI; org policy blocks public `allUsers` binding — use `gcloud run services proxy rag-ui --region=us-central1` for local access |
| `rag-evals` | ✅ live | authenticated (IAM) | eval dashboard, kept internal by design |
| `rag-ingestion` | ✅ live | authenticated (IAM) | Eventarc-triggered webhook only, not meant to be called directly |

| Infra | State |
|---|---|
| Cloud SQL Postgres 15 (`rag-postgres`) | ✅ `RUNNABLE` — connected from Cloud Run via `/cloudsql/...` unix socket |
| Memorystore Redis (`rag-redis-cache`) | ✅ `READY` — private IP, reached via Direct VPC Egress on `rag-vpc` |
| Eventarc trigger (`rag-ingestion-trigger`) | ✅ verified — GCS upload → parse → chunk → embed → Qdrant index, confirmed live |
| Portkey saved config (`pc-enterp-edad02`) | ✅ in use — fallback + semantic cache + retry bundled server-side |

*(This table reflects infrastructure provisioned via direct `gcloud` calls this session — not yet reflected in the Terraform state below. See [Known Gotchas](DOCS/12_KNOWN_GOTCHAS.md) if reconciling.)*

---

## Architecture

### Monolithic (v1)

The original single-process application — all components in one container, in-memory state, manual ingestion.

```mermaid
graph TD
    User((User)) --> UI[Streamlit UI]
    UI --> API[FastAPI /query]
    API --> Guard{NeMo Guardrails}
    Guard -->|Blocked| UI
    Guard -->|Pass| Planner{Planner Node}
    Planner -->|Conversational| Responder[Responder Node]
    Planner -->|Technical| Retriever[Retriever Node]
    Retriever --> Reranker[FlashRank Reranker]
    Reranker --> Responder
    Responder --> UI
    Responder -.-> Memory[(LangGraph MemorySaver\nin-process RAM)]
```

### Scalable Enterprise (v2 — current)

Four independent microservices, event-driven ingestion, persistent memory, semantic caching. Live infra was provisioned directly via `gcloud` this session; Terraform definitions exist in `terraform/` but reconciliation with live state is pending.

```mermaid
graph TB
    subgraph UI ["Interface Layer"]
        CHAT["Streamlit Chat UI\n(Cloud Run — IAM-authenticated)"]
        EAPP["Streamlit Eval App\n(Cloud Run — IAM-authenticated)"]
    end

    subgraph BACKEND ["Backend API — Cloud Run (IAM-authenticated)"]
        API["⚡ FastAPI /query"]
        G1{"🛡️ Gate 1\nNeMo Guardrails"}
        G2{"⚡ Gate 2\nRedis Semantic Cache\n~50ms HIT"}
        subgraph AGENT ["LangGraph Agent (Gate 3)"]
            PL["🗺️ Planner"]
            CL["❓ Clarify → END"]
            RT["🔍 Retriever"]
            RF["🚫 Retrieval Failure → END"]
            GD["📊 Grade Documents"]
            RW["✏️ Rewriter"]
            WS["🌐 Web Search"]
            CG{"🛡️ Context Guard\nsanitization"}
            RS["💬 Responder"]
            OG{"🛡️ Gate 4\nOutput Guard\nPII + Policy"}
        end
        MEM[("💾 PostgresSaver\nCloud SQL Postgres 15\nunix socket, persists across restarts")]
    end

    subgraph INGEST ["Ingestion — Cloud Run (IAM-authenticated, Eventarc target)"]
        EA["📡 Eventarc\nobject.finalized"]
        SVC["Ingestion Service\nPOST /ingest"]
        DOCAI["Google Document AI"]
        VEMB["Vertex AI\ntext-embedding-004"]
    end

    subgraph EVALS ["Evals — Cloud Run (IAM-authenticated)"]
        RAGAS["RAGAS Metrics\n5 experiments"]
        TC["Tool Correctness\nJaccard"]
        HIST[("💾 GCS\nEval History")]
    end

    subgraph GCP ["GCP Private Network (rag-vpc, Direct VPC Egress)"]
        REDIS[("🔴 Redis Memorystore\nprivate IP — semantic cache")]
        SQL[("🐘 Cloud SQL\nunix socket")]
        QD[("🗄️ Qdrant Cloud\nVector DB")]
        GCS1[("☁️ GCS Raw Bucket")]
        GCS2[("☁️ GCS Processed Bucket")]
    end

    subgraph GATEWAY ["LLM Gateway"]
        PK["🔀 Portkey\nsaved config pc-enterp-edad02\nfallback + cache + retry"]
        LLM1["Groq Llama 3.3 70B"]
        LLM2["Groq Fallback 8B"]
    end

    CHAT -->|query| API
    EAPP -->|BACKEND_URL| API
    API --> G1 --> G2
    G2 -->|HIT| CHAT
    G2 -->|MISS| PL
    PL -->|CLARIFY| CL
    PL -->|CONVERSATIONAL| RS
    PL -->|TECHNICAL| RT
    RT -->|ok| GD
    RT -->|failed| RF
    RT --> QD --> RT
    GD -->|rewrite| RW --> RT
    GD -->|websearch| WS --> CG
    GD -->|relevant| CG
    CG --> RS --> OG --> PK --> LLM1
    PK -.->|fallback| LLM2
    OG --> MEM --> PL
    OG -->|cache| G2
    G2 --- REDIS

    GCS1 -->|event| EA --> SVC
    SVC --> DOCAI --> SVC
    SVC --> VEMB --> QD
    SVC --> GCS2

    EAPP --> RAGAS --> HIST
    EAPP --> TC --> HIST

    MEM --- SQL
```

---

## Project Structure

```text
├── app/
│   ├── agents/
│   │   ├── graph.py              # LangGraph graph + PostgresSaver checkpointer
│   │   ├── state.py              # AgentState schema
│   │   └── nodes/
│   │       ├── planner.py        # Intent classification node
│   │       ├── retriever.py      # Qdrant search + FlashRank reranker node
│   │       ├── context_guard.py  # Gate 3: retrieval guardrails + context sanitization
│   │       ├── output_guard.py   # Gate 4: output PII redaction + policy/toxicity check
│   │       └── responder.py      # Answer generation node
│   ├── gateway/
│   │   └── client.py             # Portkey LLM gateway — saved config (pc-enterp-edad02): fallback + cache + retry
│   ├── guardrails/
│   │   ├── rails.py              # NeMo Guardrails integration
│   │   └── colang_rules.py       # Block/allow rule definitions
│   ├── ingestion/
│   │   ├── processor.py          # Dual-mode: CLI bulk load + Eventarc webhook (POST /ingest)
│   │   ├── chunking/
│   │   │   └── splitter.py       # Text splitting strategies
│   │   └── loaders/
│   │       ├── pdf.py            # Google Document AI PDF parser
│   │       ├── html.py           # HTML parser
│   │       ├── office.py         # DOCX / PPTX parser
│   │       └── text.py           # Plain text parser
│   ├── services/
│   │   ├── gcp/
│   │   │   ├── database_service.py      # psycopg3 connection pool (unix socket)
│   │   │   └── redis_semantic_cache.py  # Cosine-distance semantic cache
│   │   └── retrieval/
│   │       ├── embedding.py      # Vertex AI text-embedding-004 (lazy-loaded)
│   │       ├── qdrant_service.py # Vector search client
│   │       └── ranking_service.py # FlashRank reranker
│   ├── config.py                 # Centralized env var management
│   └── main.py                   # FastAPI entrypoint — two gates + /query
│
├── evals/
│   ├── app.py                    # Streamlit 4-tab eval dashboard
│   ├── pipeline.py               # Phase 1 — live /query calls + Groq summarization
│   ├── metrics.py                # Phase 2 — RAGAS scoring with GoogleEmbeddings
│   ├── guardrails_eval.py        # Guardrails TP/TN/FP/FN classification
│   ├── store.py                  # GCS persistence for eval history
│   ├── data_parser.py            # Golden dataset document parser
│   └── golden_dataset.json       # 15 RAG samples + 6 guardrail test cases
│
├── ui/
│   └── app.py                    # Streamlit chat interface
│
├── docker/
│   ├── backend.Dockerfile        # FastAPI + LangGraph + Guardrails + Redis + Postgres
│   ├── ui.Dockerfile             # Streamlit only (4 packages)
│   ├── ingestion.Dockerfile      # DocAI + Qdrant + parsers
│   └── evals.Dockerfile          # RAGAS + Vertex AI + Streamlit
│
├── terraform/
│   ├── main.tf                   # VPC, GCS buckets, Redis, Eventarc SA IAM
│   ├── cloud_run.tf              # All 4 Cloud Run services + public IAM
│   ├── database.tf               # Cloud SQL Postgres 15
│   ├── ingestion.tf              # Ingestion service + Eventarc trigger (POST /ingest)
│   ├── variables.tf              # Input variable declarations
│   ├── provider.tf               # GCP + hashicorp/time providers
│   └── output.tf                 # backend_url, ui_url, evals_url, ingestion_url
│
├── notebooks/
│   ├── 01_guardrails.ipynb       # NeMo Guardrails walkthrough
│   ├── 02_llm_gateway.ipynb      # Portkey gateway exploration
│   └── 03_evals.ipynb            # RAGAS metrics walkthrough
│
├── DATA/
│   └── true_data/                # Golden documents (Kubernetes, Databricks)
│
├── DOCS/                         # 24 architectural and operational guides
├── cloudbuild.yaml               # Parallel build of all 4 Docker images
├── cloudbuild-evals.yaml         # Targeted evals-only rebuild
├── requirements.txt              # Monolith / local dev dependencies
├── requirements-backend.txt      # Backend service dependencies
├── requirements-evals.txt        # Evals service dependencies
├── requirements-ingestion.txt    # Ingestion service dependencies
└── requirements-ui.txt           # UI service dependencies (4 packages)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Orchestration | LangGraph (cyclic graph, 10 nodes incl. clarify/rewriter/web-search/retrieval-failure escapes) |
| LLMs | Groq Llama 3.3 70B + 3.1 8B via **Portkey saved gateway config** (`pc-enterp-edad02`) |
| Guardrails | NeMo Guardrails (Gate 1) |
| Semantic Cache | Redis Memorystore (private IP, Direct VPC Egress) + Vertex AI embeddings (Gate 2) |
| Persistent Memory | LangGraph `PostgresSaver` on Cloud SQL Postgres 15 — unix socket, IAM `cloudsql.client` |
| Vector DB | Qdrant Cloud |
| Reranking | FlashRank (local, zero-latency) |
| Embeddings | **Vertex AI text-embedding-004** |
| Document Parsing | Google Document AI (PDF OCR) |
| Auto-Ingestion | GCS → Eventarc → Cloud Run (internal, IAM `run.invoker` on the trigger's SA) |
| Evaluation | RAGAS (5 metrics) + Jaccard Tool Correctness |
| Eval Storage | GCS (`eval-results/` prefix, persists across restarts) |
| Observability | Pydantic Logfire + LangSmith + Portkey Dashboard (`x-portkey-cache-status` header) |
| Compute | Google Cloud Run (4 independent microservices, all IAM-authenticated) |
| IaC | Terraform definitions exist (see `terraform/`); current live infra was provisioned directly via `gcloud` this session — reconciliation pending |
| CI/CD | Google Cloud Build (parallel 4-image build) |
| Networking | Direct VPC Egress on `rag-vpc` (no VPC connector — one was provisioned then removed as redundant) |

---

## Getting Started

### Local development

```bash
python -m venv tenvv
source tenvv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
```

Create `.env` — see [DOCS/07_ENVIRONMENT_VARIABLES.md](DOCS/07_ENVIRONMENT_VARIABLES.md) for all required keys.

```bash
# Ingest documents locally
python -m app.ingestion.processor DATA/true_data

# Terminal 1 — backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — UI
streamlit run ui/app.py

# Terminal 3 — evals (optional)
streamlit run evals/app.py
```

### Cloud deployment (scalable)

See [commands_scalable.md](commands_scalable.md) for the full step-by-step. High level:

```bash
# 1. Create AR repo first
cd terraform && terraform apply -target=google_artifact_registry_repository.repo

# 2. Build all 4 Docker images in parallel
cd .. && gcloud builds submit --config cloudbuild.yaml --project=YOUR_PROJECT .

# 3. Deploy everything
cd terraform && terraform apply
```

Outputs: `backend_url`, `ui_url`, `evals_url`, `ingestion_url`

---

## Documentation Index

| # | Guide | What it covers |
|---|-------|---------------|
| 1 | [System Overview](DOCS/01_SYSTEM_OVERVIEW.md) | High-level vision and end-to-end flow |
| 2 | [Ingestion Engine](DOCS/02_INGESTION_ENGINE.md) | Document parsing and indexing pipeline |
| 3 | [Node Intelligence](DOCS/03_NODE_INTELLIGENCE.md) | Planner, Retriever, Responder internals |
| 4 | [Observability](DOCS/04_TRACING_AND_OBSERVABILITY.md) | Logfire + LangSmith tracing |
| 5 | [GCP Prod Setup](DOCS/05_GCP_PROD_SETUP.md) | Step-by-step infrastructure provisioning (monolith) |
| 6 | [Deployment Strategy](DOCS/06_DEPLOYMENT_STRATEGY.md) | Cloud Build and Cloud Run details |
| 7 | [Env Variables](DOCS/07_ENVIRONMENT_VARIABLES.md) | Complete configuration dictionary |
| 8 | [GCP Roles & Services](DOCS/08_GCP_ROLES_AND_SERVICES.md) | IAM and service breakdown |
| 9 | [Infra Architecture](DOCS/09_INFRA_ARCHITECTURE.md) | The 3-tier cloud blueprint |
| 10 | [Redis Caching](DOCS/10_REDIS_CACHING.md) | Semantic cache — cosine distance, Gate 2 design |
| 11 | [Microservices Transition](DOCS/11_MICROSERVICES_TRANSITION.md) | Scaling beyond monolith |
| 12 | [Known Gotchas](DOCS/12_KNOWN_GOTCHAS.md) | GCP quirks — Eventarc SA, HCL syntax, tfvars secrets |
| 13 | [FlashRank Reranking](DOCS/13_FLASHRANK_RERANKING.md) | Local semantic reranker deep-dive |
| 14 | [VPC Networking](DOCS/14_VPC_NETWORKING.md) | Direct VPC egress — Cloud SQL unix socket |
| 15 | [Guardrails](DOCS/15_GUARDRAILS.md) | NeMo Guardrails implementation |
| 16 | [LLM Gateway](DOCS/16_LLM_GATEWAY.md) | Portkey routing, fallback, and observability |
| 17 | [Evals](DOCS/17_EVALS.md) | RAGAS metrics theory, token budget, rate limit strategy |
| 18 | [Evals Pipeline](DOCS/18_EVALS_PIPELINE.md) | Live eval pipeline, GCS persistence, ~75 min runtime |
| 19 | [Scaling Migration](DOCS/19_SCALING_ARCHITECTURE_MIGRATION.md) | Monolith → microservices roadmap (5 phases) |
| 20 | [Postgres Memory](DOCS/20_STEP_2_POSTGRES_MEMORY.md) | PostgresSaver — unix socket, hybrid LOCAL_MODE |
| 21 | [Eventarc Ingestion](DOCS/21_STEP_3_EVENTARC_INGESTION.md) | Event-driven ingestion — feedback loop fix, IAM |
| 22 | [Semantic Cache](DOCS/22_STEP_4_SEMANTIC_CACHE.md) | Redis semantic cache — threshold tuning, business impact |
| 23 | [Microservices & Docker](DOCS/23_MICROSERVICES_AND_CONTAINERIZATION.md) | 4 Dockerfiles, split requirements, layer caching |
| 24 | [Terraform IaC](DOCS/24_INFRASTRUCTURE_AS_CODE_TERRAFORM.md) | Full Terraform reference — deployment order, gotchas |

---

*Built for High-Scale Enterprise Document Intelligence.*

---

## Author

**Akash Kar**
