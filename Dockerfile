# The API: FastAPI, the LangGraph agent and the embedding model, on CPU.

# Requirements come from poetry.lock, exported once so the final image doesn't need Poetry.
FROM python:3.11-slim AS requirements
RUN pip install --no-cache-dir "poetry>=2,<3" poetry-plugin-export
COPY pyproject.toml poetry.lock ./
RUN poetry export --without-hashes -o requirements.txt

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    HF_HOME=/opt/huggingface
WORKDIR /app

# PyTorch is the CPU build: the default one brings several GB of CUDA libraries the API
# never uses.
COPY --from=requirements requirements.txt /tmp/requirements.txt
RUN grep -E '^torch==' /tmp/requirements.txt | cut -d ';' -f 1 > /tmp/torch.txt \
    && pip install -r /tmp/torch.txt --index-url https://download.pytorch.org/whl/cpu \
    && grep -vE '^(torch|triton|nvidia-|cuda-)' /tmp/requirements.txt > /tmp/requirements-cpu.txt \
    && pip install -r /tmp/requirements-cpu.txt \
    && rm /tmp/*.txt

# The embedding model is part of the image, so the API starts without downloading it.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
ENV HF_HUB_OFFLINE=1

COPY accounts ./accounts
COPY agent ./agent
COPY api ./api
COPY ingestion ./ingestion
COPY interactions ./interactions
COPY retrieval ./retrieval
COPY scripts ./scripts
COPY corpus ./corpus

EXPOSE 8010
# On a first start the documents are ingested into Qdrant; after that they're left as they are.
CMD ["sh", "-c", "python scripts/ingest.py --if-empty && exec uvicorn api.main:app --host 0.0.0.0 --port 8010"]
