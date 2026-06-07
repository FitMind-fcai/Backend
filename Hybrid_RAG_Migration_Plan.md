# Migration Plan: Standard RAG → Hybrid Retrieval RAG for AI Fitness Coach

## Objective

Upgrade the current RAG pipeline from:

```text
User Query
    ↓
Embedding
    ↓
ChromaDB Vector Search
    ↓
Top-K Chunks
    ↓
LLM
```

to:

```text
User Query
    ↓
Dense Retrieval (ChromaDB)
          +
Sparse Retrieval (BM25)
    ↓
RRF Fusion
    ↓
Cross-Encoder Reranking
    ↓
Top Context Chunks
    ↓
LLM
```

---

# Phase 0 – Baseline Assessment

## Current Architecture

Document the current implementation:

- Embedding model
- Chunking strategy
- Chunk size and overlap
- ChromaDB configuration
- LLM provider
- Retrieval Top-K value
- Prompt template

## Metrics to Capture

Before making changes, measure:

- Retrieval precision
- Answer relevance
- Hallucination rate
- Average latency
- Cost per request

Create a benchmark set of 50–100 fitness-related questions covering:

- Nutrition
- Supplements
- Training
- Injury prevention
- Weight loss
- Muscle gain

---

# Phase 1 – Add Sparse Retrieval (BM25)

## Goal

Introduce keyword-based retrieval alongside vector search.

## Recommended Libraries

### Option A

```bash
pip install rank-bm25
```

### Option B (future scaling)

- Elasticsearch
- OpenSearch

## Implementation

Build a BM25 index from the same chunked documents already stored in ChromaDB.

Workflow:

```text
Query
   ↓
BM25 Search
   ↓
Top 20 Results
```

## Expected Benefit

Improved retrieval for:

- Supplement names
- Exercise names
- Fitness abbreviations
- Technical terminology

Examples:

- Creatine Monohydrate
- PPL Split
- RPE
- VO2 Max
- Hypertrophy

---

# Phase 2 – Hybrid Retrieval

## Goal

Retrieve candidates from both systems.

### Dense Retrieval

```text
Query
   ↓
Embedding
   ↓
ChromaDB
   ↓
Top 20 Dense Results
```

### Sparse Retrieval

```text
Query
   ↓
BM25
   ↓
Top 20 Sparse Results
```

Combine both candidate sets.

---

# Phase 3 – RRF Fusion

## Goal

Merge Dense and BM25 results using Reciprocal Rank Fusion.

Formula:

```text
RRF Score = Σ 1 / (k + rank)
```

Typical:

```text
k = 60
```

## Output

Generate:

```text
Top 30 Fused Candidates
```

## Expected Benefit

Combines:

- Semantic similarity
- Exact keyword matching

without needing score normalization.

---

# Phase 4 – Cross-Encoder Reranking

## Goal

Improve final document ranking.

## Recommended Models

### Fast

```text
BAAI/bge-reranker-base
```

### Higher Accuracy

```text
BAAI/bge-reranker-large
```

## Workflow

Input:

```text
(Query, Chunk)
```

Example:

```text
How much protein should I eat while cutting?
```

paired with each candidate chunk.

Output:

```text
Relevance Score
```

Keep:

```text
Top 5–10 Chunks
```

## Expected Benefit

Significantly higher precision before context reaches the LLM.

---

# Phase 5 – Context Builder Optimization

## Goal

Construct cleaner prompts.

Recommendations:

- Remove duplicate chunks
- Remove near-duplicates
- Respect token budget
- Preserve source metadata

Suggested metadata:

```json
{
  "source": "nutrition_guide.pdf",
  "section": "protein",
  "chunk_id": 42
}
```

---

# Phase 6 – Evaluation

Compare:

## Baseline

Current RAG

vs

## Hybrid System

Dense + BM25 + RRF + Reranker

Measure:

- Retrieval Recall@K
- Precision@K
- Context Relevance
- Answer Accuracy
- Latency
- Cost

Target improvements:

| Metric | Goal |
|----------|----------|
| Retrieval Quality | +15–30% |
| Context Relevance | +20–40% |
| Hallucinations | Reduced |
| Fitness Terminology Matching | Significant Improvement |

---

# Phase 7 – Production Rollout

## Deployment Strategy

### Week 1

Internal testing.

### Week 2

10% traffic.

### Week 3

50% traffic.

### Week 4

100% traffic.

Monitor:

- Response quality
- Retrieval latency
- User satisfaction

---

# Recommended Final Architecture

```text
User Question
        ↓
   Query Processing
        ↓
 ┌─────────────────┐
 │ Dense Retrieval │
 └─────────────────┘
        +
 ┌─────────────────┐
 │ Sparse Retrieval│
 └─────────────────┘
        ↓
      RRF
        ↓
 Cross Encoder
   Reranker
        ↓
 Context Builder
        ↓
      LLM
        ↓
 Fitness Coach Answer
```

---

# Priority Order

If implementation time is limited:

1. Add BM25
2. Add RRF Fusion
3. Add Cross-Encoder Reranker
4. Optimize Context Builder
5. Evaluate and tune Top-K values

This order provides the highest return on engineering effort.
