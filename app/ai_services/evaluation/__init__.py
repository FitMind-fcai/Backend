"""
AI Coach — Evaluation Package
==============================
Evaluates the RAG + prompt engineering pipeline accuracy using an LLM-as-judge
approach.  Import and run via:

    from app.ai_services.evaluation.runner import run_evaluation
    run_evaluation(num_samples=100)

Or use the CLI entry point:

    python3 scripts/evaluate_rag_pipeline.py --samples 100
"""
