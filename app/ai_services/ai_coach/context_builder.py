"""
ContextBuilder — RAG-grounded safety rule synthesizer.

Role in the pipeline
--------------------
Runs BEFORE the main plan generator, in a parallel thread alongside the DB
food/exercise fetch.  It does two things:

  1. Issues targeted per-condition/injury/allergy/medication RAG queries in
     parallel against the knowledge base (not one broad query).

  2. Feeds all retrieved KB chunks + the user's raw health profile to a fast
     LLM that synthesizes concrete, numbered rules (EXCLUDE / LIMIT / REQUIRE /
     SAFE ALTERNATIVE).

The result replaces Channel C in the main prompt.  The main generator no
longer needs to "recall" rules from training — it just applies them.
The main prompt also drops Channel A (general RAG) because the context builder
already extracts the relevant evidence into the rules block.
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from app.ai_services.ai_coach.dtos import UserProfileDTO
from app.ai_services.ai_coach.llm_client import LLMClient
from app.ai_services.ai_coach.vector_db_service import VectorDBService, get_vector_db_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Query templates
# ---------------------------------------------------------------------------

# Each template receives a single keyword (condition / injury / allergen /
# medication name) via .format(term=...).

_NUTRITION_QUERY_TEMPLATES = [
    "{term} dietary restrictions food contraindications",
    "{term} nutrition guidelines foods to avoid",
    "{term} drug food interaction dietary safety",
    "{term} allergy hidden sources cross contamination",
]

_WORKOUT_QUERY_TEMPLATES = [
    "{term} exercise contraindications movements to avoid",
    "{term} rehabilitation exercise safe alternatives",
    "{term} injury exercise restrictions physical activity",
    "{term} exercise intensity limits RPE safe range",
]

# ---------------------------------------------------------------------------
# System / user prompts for the synthesizer LLM
# ---------------------------------------------------------------------------

_KB_USAGE_RULES = """
HOW TO USE THE RETRIEVED KNOWLEDGE BASE — READ CAREFULLY:
The "RETRIEVED KNOWLEDGE BASE" section was filled by an automated search and may
contain chunks that do NOT correspond to anything in this user's actual profile.
The profile fields are the ONLY source of truth for what conditions/injuries/
allergies/medications this user actually has.

Before using ANY retrieved chunk, verify it explicitly:
1. Name the exact condition/injury/allergy/medication that chunk claims to be about.
2. Confirm that exact term (or a clear synonym) appears in the USER HEALTH PROFILE fields.
3. If it does not appear in the profile, DISCARD that chunk entirely — do not
   reference it, do not produce a rule from it, even if it looks medically
   plausible or well-written.
4. If a profile field's value is "None", "N/A", "Not applicable", or empty,
   treat that field as having NO condition — produce zero rules for it,
   regardless of what was retrieved.

Do not let the presence of retrieved text imply relevance. Retrieval is a
keyword/embedding match, not a guarantee that the content applies to this user.
"""

_NUTRITION_SYSTEM = """You are a clinical dietitian and pharmacist safety rule extractor.

Given a user's health profile and retrieved scientific guidelines, produce a
structured, numbered list of CONCRETE nutrition safety rules the meal-plan
generator MUST follow.
""" + _KB_USAGE_RULES + """
Output format — plain text only, NO JSON, NO markdown headers:

EXCLUDE: [exact food, ingredient, or category] — [one-line reason]
LIMIT: [food/nutrient] to [threshold] — [one-line reason]
REQUIRE: [food/nutrient/approach] — [one-line reason]
INTERACTION: [food] + [medication] — [one-line mechanism and action]

Rules must be specific enough that a chef reading them can comply without
needing medical knowledge.  If the knowledge base does not cover a condition
that IS confirmed present in the profile, still output rules from your
clinical training but prefix them with [TRAINING].
Output maximum 25 rules.  If no conditions/medications/allergies are confirmed
present in the profile, output exactly: NO_RESTRICTIONS"""

_WORKOUT_SYSTEM = """You are a sports medicine physician and clinical physiotherapist safety rule extractor.

Given a user's health profile and retrieved scientific guidelines, produce a
structured, numbered list of CONCRETE exercise safety rules the workout-plan
generator MUST follow.
""" + _KB_USAGE_RULES + """
Output format — plain text only, NO JSON, NO markdown headers:

EXCLUDE: [exact exercise or movement pattern] — [one-line reason]
LIMIT: [exercise parameter] to [threshold] — [one-line reason]
REQUIRE: [mandatory element e.g. warm-up / safety cue / monitoring] — [one-line reason]
SAFE ALTERNATIVE: instead of [excluded exercise] use [specific safe substitute]

Rules must be specific enough that a trainer reading them can comply without
needing medical knowledge.  If the knowledge base does not cover a condition
that IS confirmed present in the profile, still output rules from your
clinical training but prefix them with [TRAINING].
Output maximum 25 rules.  If no conditions/injuries are confirmed present in
the profile, output exactly: NO_RESTRICTIONS"""


# ---------------------------------------------------------------------------
# ContextBuilder
# ---------------------------------------------------------------------------

class ContextBuilder:

    def __init__(
        self,
        llm_client: LLMClient,
        vector_db: Optional[VectorDBService] = None,
        rag_k_per_query: int = 2,
        max_query_workers: int = 6,
    ):
        self._llm    = llm_client
        self._vdb    = vector_db or get_vector_db_service()
        self._rag_k  = rag_k_per_query
        self._workers = max_query_workers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_nutrition_rules(self, user_profile: UserProfileDTO) -> str:
        """Return a plain-text block of KB-grounded nutrition safety rules."""
        terms = self._extract_terms(user_profile, include_injuries=False)
        if not terms:
            logger.info("ContextBuilder — no medical terms found, skipping nutrition rules")
            return ""
        return self._build_rules(terms, _NUTRITION_QUERY_TEMPLATES, _NUTRITION_SYSTEM, user_profile, "nutrition")

    def build_workout_rules(self, user_profile: UserProfileDTO) -> str:
        """Return a plain-text block of KB-grounded workout safety rules."""
        terms = self._extract_terms(user_profile, include_injuries=True)
        if not terms:
            logger.info("ContextBuilder — no medical terms found, skipping workout rules")
            return ""
        return self._build_rules(terms, _WORKOUT_QUERY_TEMPLATES, _WORKOUT_SYSTEM, user_profile, "workout")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    _PLACEHOLDER_VALUES = {
        "none", "n/a", "na", "nil", "null", "no specific preference",
        "no allergies", "no medications", "no injuries", "no medical conditions",
        "not applicable", "no known", "no known allergies", "no known conditions",
    }

    def _is_placeholder(self, term: str) -> bool:
        return term.strip().lower() in self._PLACEHOLDER_VALUES

    def _extract_terms(self, profile: UserProfileDTO, include_injuries: bool) -> List[str]:
        """Split raw profile fields into individual searchable terms."""
        raw: List[str] = []
        for field in [profile.medical_conditions, profile.medications, profile.allergies]:
            if field and not self._is_placeholder(field):
                raw.extend([t.strip() for t in field.replace(";", ",").split(",") if t.strip()])
        if include_injuries and profile.injuries and not self._is_placeholder(profile.injuries):
            raw.extend([t.strip() for t in profile.injuries.replace(";", ",").split(",") if t.strip()])
        # deduplicate preserving order, dropping any remaining placeholder fragments
        seen = set()
        unique = []
        for t in raw:
            if self._is_placeholder(t):
                continue
            low = t.lower()
            if low not in seen:
                seen.add(low)
                unique.append(t)
        return unique

    def _build_queries(self, terms: List[str], templates: List[str]) -> List[str]:
        queries = []
        for term in terms:
            for tmpl in templates:
                queries.append(tmpl.format(term=term))
        return queries

    def _fetch_all_rag(self, queries: List[str]) -> str:
        """Run all RAG queries in parallel and concatenate unique results."""
        if not queries:
            return ""

        chunks: List[str] = []
        seen_prefixes: set = set()

        with ThreadPoolExecutor(max_workers=min(self._workers, len(queries))) as pool:
            futures = {
                pool.submit(self._vdb.get_context, q, k=self._rag_k): q
                for q in queries
            }
            for future in as_completed(futures):
                try:
                    chunk = future.result()
                    if chunk:
                        # deduplicate by first 120 chars
                        prefix = chunk[:120]
                        if prefix not in seen_prefixes:
                            seen_prefixes.add(prefix)
                            chunks.append(chunk)
                except Exception as exc:
                    logger.warning("ContextBuilder RAG query failed: %s", exc)

        return "\n\n---\n\n".join(chunks)

    def _build_rules(
        self,
        terms: List[str],
        templates: List[str],
        system_prompt: str,
        profile: UserProfileDTO,
        plan_type: str,
    ) -> str:
        queries  = self._build_queries(terms, templates)
        kb_text  = self._fetch_all_rag(queries)

        logger.info(
            "ContextBuilder [%s] — %d terms → %d queries → %d KB chars",
            plan_type, len(terms), len(queries), len(kb_text),
        )

        user_prompt = (
            f"USER HEALTH PROFILE:\n{profile.to_context_string()}\n\n"
            f"RETRIEVED KNOWLEDGE BASE:\n{kb_text or '(no relevant content found)'}\n\n"
            f"Extract all safety rules for a {plan_type} plan for this specific user."
        )

        try:
            rules = self._llm.call_context_builder_llm(system_prompt, user_prompt)
            rules = (rules or "").strip()
            if rules.upper() == "NO_RESTRICTIONS":
                return ""
            logger.info("ContextBuilder [%s] produced %d chars of rules", plan_type, len(rules))
            return rules
        except Exception as exc:
            logger.warning("ContextBuilder [%s] LLM call failed, falling back to empty rules: %s", plan_type, exc)
            return ""


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_context_builder: Optional[ContextBuilder] = None
_context_builder_lock = threading.Lock()


def get_context_builder(llm_client: Optional[LLMClient] = None) -> ContextBuilder:
    global _context_builder
    if _context_builder is None:
        with _context_builder_lock:
            if _context_builder is None:
                from app.ai_services.ai_coach.ai_coach_service import get_ai_coach_service
                client = llm_client or get_ai_coach_service().llm
                _context_builder = ContextBuilder(client)
    return _context_builder
