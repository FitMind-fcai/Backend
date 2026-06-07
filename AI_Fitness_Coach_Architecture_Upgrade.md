# AI Fitness Coach Architecture Upgrade Plan

## Objective

Move from a pure RAG-centered generation approach to a structured planning architecture that combines:

- User Profile Data
- PostgreSQL Workout Library
- PostgreSQL Meal Library
- Scientific Knowledge Base (RAG)
- Planning Engine
- LLM Refinement Layer

The goal is to generate more consistent, explainable, and higher-quality fitness plans.

---

# Current Architecture

```text
User Context
      +
Workout Records (PostgreSQL)
      +
Meal Records (PostgreSQL)
      +
Scientific Knowledge (Vector DB)
      ↓
LLM
      ↓
Generated Plan
```

## Current Strengths

- Uses real scientific context.
- Uses centralized workout and meal libraries.
- Personalized to the user.

## Current Limitation

The LLM is responsible for too many planning decisions:

- Macro allocation
- Workout selection
- Meal selection
- Plan structure
- Scientific reasoning

This can reduce consistency between generations.

---

# Target Architecture

```text
User Input
      │
      ▼

Profile Analyzer
      │
      ▼

Planning Engine
      │
      ├── Workout Retrieval
      │
      ├── Meal Retrieval
      │
      └── Knowledge Retrieval
      │
      ▼

Structured Draft Plan
      │
      ▼

LLM Refinement Layer
      │
      ▼

Final Fitness Plan
```

---

# Phase 1 – Build a Planning Engine

## Goal

Move major planning decisions outside the LLM.

The Planning Engine should determine:

### Nutrition

- Daily calories
- Protein target
- Fat target
- Carbohydrate target
- Number of meals

### Training

- Training frequency
- Split selection
- Volume targets
- Exercise constraints

Output:

```json
{
  "goal": "fat_loss",
  "calories": 2200,
  "protein": 180,
  "fat": 60,
  "carbs": 220,
  "training_days": 4,
  "split": "upper_lower"
}
```

---

# Phase 2 – Improve Workout Retrieval

## Current

Filtering by:

- Goal
- Calories
- User criteria

## Upgrade

Add ranking after filtering.

Workflow:

```text
SQL Filter
      ↓
Candidate Workouts
      ↓
Ranking
      ↓
Top Workouts
```

## Suggested Ranking Factors

| Factor | Weight |
|----------|----------|
| Goal Match | High |
| Experience Match | High |
| Equipment Match | Medium |
| Injury Compatibility | High |
| Volume Compatibility | Medium |

Output:

```text
Top 5-10 Workout Candidates
```

---

# Phase 3 – Improve Meal Retrieval

## Current

SQL filtering.

## Upgrade

Add scoring.

Workflow:

```text
SQL Filter
      ↓
Candidate Meals
      ↓
Meal Scoring
      ↓
Top Meals
```

## Scoring Factors

| Factor | Weight |
|----------|----------|
| Calorie Match | High |
| Protein Match | High |
| Goal Match | High |
| Meal Type Match | Medium |
| Variety Score | Medium |

Output:

```text
Top 20-50 Meal Candidates
```

---

# Phase 4 – Upgrade Scientific Knowledge Retrieval

## Current

Dense Retrieval Only

```text
Embedding
     ↓
Vector Search
```

## Upgrade

Hybrid Retrieval

```text
Dense Retrieval
       +
BM25
       ↓
RRF Fusion
       ↓
Reranker
```

---

## Step 4.1 – Add BM25

Recommended:

```bash
pip install rank-bm25
```

Retrieve:

```text
Top 20 Dense Results
Top 20 BM25 Results
```

---

## Step 4.2 – Add RRF Fusion

Combine both retrieval methods.

Output:

```text
Top 30 Candidates
```

---

## Step 4.3 – Add Cross Encoder Reranking

Recommended Models:

### Fast

```text
BAAI/bge-reranker-base
```

### Higher Accuracy

```text
BAAI/bge-reranker-large
```

Output:

```text
Top 5 Scientific Chunks
```

---

# Phase 5 – Structured Draft Plan Generation

## Goal

Generate a structured plan BEFORE asking the LLM for final formatting.

Example:

```json
{
  "nutrition": {
    "calories": 2200,
    "protein": 180
  },
  "workout_split": "upper_lower",
  "selected_workouts": [...],
  "selected_meals": [...]
}
```

This becomes the foundation of the final answer.

---

# Phase 6 – LLM Refinement Layer

## Input

### User Profile

- Age
- Weight
- Height
- Goal
- Experience

### Planning Engine Output

- Macros
- Calories
- Split
- Selected workouts
- Selected meals

### Scientific Context

Retrieved from Hybrid RAG.

---

## Responsibilities of the LLM

The LLM should:

- Explain decisions
- Organize the plan
- Personalize recommendations
- Provide coaching guidance
- Provide scientific reasoning

The LLM should NOT:

- Recalculate macros
- Search all meals
- Search all workouts
- Decide the entire structure from scratch

---

# Phase 7 – Evaluation

Measure:

## Consistency

Generate plans multiple times for the same profile.

Check:

- Same calorie target
- Same macro target
- Similar workout selection

---

## Retrieval Quality

Evaluate:

### Workout Retrieval

- Relevant workout selection

### Meal Retrieval

- Relevant meal selection

### Knowledge Retrieval

- Relevant scientific evidence

---

# Recommended Final Architecture

```text
User Profile
      │
      ▼

Profile Analyzer
      │
      ▼

Planning Engine
      │
      ├── PostgreSQL Workout Retrieval
      │        ↓
      │     Ranking
      │
      ├── PostgreSQL Meal Retrieval
      │        ↓
      │     Ranking
      │
      └── Hybrid RAG
               ↓
      BM25 + Dense + Reranker

      ▼

Structured Draft Plan
      ▼

LLM Refinement
      ▼

Final Fitness Plan
```

---

# Priority Order

1. Build Planning Engine
2. Add Workout Ranking
3. Add Meal Ranking
4. Add BM25 to RAG
5. Add RRF Fusion
6. Add Reranker
7. Evaluate Consistency

This order is optimized specifically for a fitness coach that generates complete meal and workout plans rather than answering standalone questions.
