# Optimization Plan for the Current AI Coach Implementation

## Objective

Improve the current implementation so the AI coach produces plans that feel:

- personalized like a real human coach made them
- more reliable and consistent
- safer
- easier to scale and maintain
- easier to improve later with validation, scoring, memory, and adaptation

This plan assumes you want to **keep the current architecture as a base** and evolve it gradually rather than rewrite everything.

---

# 1. Current Architecture Summary

Your current system already has a solid base:

- `PlanGenerationService` orchestrates generation and saving
- `AICoachService` handles prompting, RAG, LLM calls, and DTO parsing
- repositories provide allowed exercises and foods
- nutrition macros are recomputed from DB records
- plans are generated as drafts before save
- existing plans can be used as regeneration context

This is a good starting point for a production AI planning system.

---

# 2. Main Architectural Principle Going Forward

The best long-term design is **hybrid**:

- **LLM** for personalization, composition, human-like planning, and natural decision making
- **RAG** for evidence, guidance, and domain context
- **structured feature extraction** for consistent personalization inputs
- **DB candidate filtering** for grounded exercise/food selection
- **rule/safety layer** only for non-negotiable guardrails
- **validator/critic layer** for output review
- **scoring/ranking** for choosing the best candidate
- **memory/adaptation** for long-term coach-like behavior

Do **not** rely on:
- prompts alone
- hardcoded personalization logic
- training your own model at this stage

---

# 3. Main Problems in the Current Implementation

## 3.1 Personalization is mostly prompt-based
Right now most personalization is passed as:
- raw profile context string
- raw preferences context string

This works, but it is weak because the LLM is doing too much interpretation from raw text.

### Why this is a problem
- messy user data is not normalized first
- retrieval queries are not as strong as they could be
- candidate filtering is not driven by deeper features
- later validation/scoring becomes harder

---

## 3.2 Candidate pools are still too shallow
You already filter:
- exercises by equipment/focus/difficulty
- foods by diet/allergies/exclusions

That is good, but it should become smarter.

### Missing filters
#### Workout
- injury-safe movement filtering
- medical restrictions
- volume tolerance
- time-cap fit
- movement pattern compatibility

#### Nutrition
- medical diet suitability
- prep-time suitability
- cuisine compatibility
- sodium-related filtering
- protein density
- food practicality

---

## 3.3 The system generates one plan and trusts it too early
Right now generation is mostly:
- generate one plan
- parse
- validate DTO
- return draft

This is fine for early versions, but not ideal for high-quality personalization.

### Why this is a problem
A real coach does not usually choose the first idea automatically.
They implicitly compare options.

---

## 3.4 Safety rules and personalization logic are mixed together
Some hardcoded rules are useful for safety, but hardcoded logic should not control the creative/personalized parts of planning.

### Correct use of hardcoded rules
- allergies
- contraindications
- medication-food exclusions
- non-negotiable safety rules

### Wrong use of hardcoded rules
- meal creativity
- exercise variety style
- progression style
- adherence personalization
- coaching style

---

## 3.5 No feature layer exists yet
You currently convert objects to string/JSON context for prompts, but there is no proper middle layer that turns user information into structured planning features.

That should be the next major improvement.

---

# 4. Recommended Optimization Roadmap

---

# Phase 1 — Strengthen the Current System

## 4.1 Add a Feature Extraction Layer

Create a service that transforms:
- profile
- preferences
- existing plan
- later: user history, feedback, adherence

into compact structured planning features.

## Why
This will improve:
- personalization consistency
- retrieval quality
- DB filtering
- future scoring
- future validation
- future memory integration

## Deliverables
- `WorkoutFeaturesDTO`
- `NutritionFeaturesDTO`
- `CoachingFeatureService`

## Example outputs
### Workout features
- primary goal
- experience level
- workout days per week
- session time cap
- equipment access
- injuries
- medical flags
- exercise exclusions
- preferred focus areas
- training style preference

### Nutrition features
- primary goal
- calorie target
- macro targets
- diet style
- cuisine preference
- allergies
- excluded ingredients
- medical diet flags
- meals per day
- prep-time preference

---

## 4.2 Pass Structured Features into the AI Coach

Update `AICoachService` so it receives:
- raw DTO context
- structured features
- allowed candidate pool
- existing plan context

## Why
The LLM should receive:
- concise structured planning facts
- human nuance
- grounded candidate options

instead of only raw textual context.

## Prompt pattern
Include a compact feature block such as:

```json
{
  "primary_goal": "build muscle",
  "experience_level": "intermediate",
  "training_days_per_week": 4,
  "session_time_cap": 60,
  "injuries": ["right_shoulder_impingement"],
  "exercise_exclusions": ["overhead_press", "upright_row"],
  "diet_style": "balanced",
  "cuisine_preference": "Mediterranean",
  "target_calories": 2400
}