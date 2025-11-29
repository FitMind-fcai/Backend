from groq import Groq
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from datetime import datetime
from local_exercise_db import LocalExerciseDB
from exercise_helper import ai_search_with_function_calling  # Updated to use function calling

# Load Groq client
client = Groq(api_key="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")

# Initialize local exercise database
exercise_db = LocalExerciseDB("cleaned_fitness_exercises.csv")

# Create markdown file for output
output_file = f"fitness_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
md_content = []

# Same embedding model
embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2')

# Load existing vectorstore (no re-embedding)
vectorstore = Chroma(
    collection_name="fitness_test",
    embedding_function=embeddings,
    persist_directory="chroma_db"
)

print("✅ Loaded existing Chroma database!\n")

# Add header to markdown
md_content.append("# 🏋️ Personalized Fitness Consultation Results\n")
md_content.append(f"**Report Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
md_content.append("---\n")

# User Profile - Medical conditions, injuries, and sensitivities
user_profile = {
    "name": "Sara",
    "age": 40,
    "medical_conditions": [
        "Chronic lower back pain",
        "Mild knee sensitivity"
    ],
    "allergies": [],
    "injuries": [
        "Previous shoulder injury (recovered)"
    ],
    "fitness_level": "Beginner",
    "goals": "Build muscle while protecting joints",
    "restrictions": [
        "Avoid heavy deadlifts",
        "Limited overhead pressing"
    ]
}

def generatePdfReport(txt):
    pass 


# Placeholder for potential PDF generation logic
# Format user profile for context
user_context_display = f"""
USER PROFILE:
- Name: {user_profile['name']}, Age: {user_profile['age']}
- Fitness Level: {user_profile['fitness_level']}
- Goals: {user_profile['goals']}
- Medical Conditions: {', '.join(user_profile['medical_conditions']) if user_profile['medical_conditions'] else 'None'}
- Previous Injuries: {', '.join(user_profile['injuries']) if user_profile['injuries'] else 'None'}
- Allergies: {', '.join(user_profile['allergies']) if user_profile['allergies'] else 'None'}
- Exercise Restrictions: {', '.join(user_profile['restrictions']) if user_profile['restrictions'] else 'None'}
"""

print("👤 User Profile Loaded:")
print(user_context_display)

# Add user profile to markdown
md_content.append("## 👤 User Profile\n")
md_content.append(f"- **Name:** {user_profile['name']}\n")
md_content.append(f"- **Age:** {user_profile['age']}\n")
md_content.append(f"- **Fitness Level:** {user_profile['fitness_level']}\n")
md_content.append(f"- **Goals:** {user_profile['goals']}\n")
md_content.append(f"- **Medical Conditions:** {', '.join(user_profile['medical_conditions']) if user_profile['medical_conditions'] else 'None'}\n")
md_content.append(f"- **Previous Injuries:** {', '.join(user_profile['injuries']) if user_profile['injuries'] else 'None'}\n")
md_content.append(f"- **Allergies:** {', '.join(user_profile['allergies']) if user_profile['allergies'] else 'None'}\n")
md_content.append(f"- **Exercise Restrictions:** {', '.join(user_profile['restrictions']) if user_profile['restrictions'] else 'None'}\n")
md_content.append("\n---\n")

# Multiple fitness-related queries (Mix of Arabic and English)
queries = [
    "عايزة اتخلص من ترهلات بعد الولادة"   
]

for idx, query in enumerate(queries, 1):
    print("="*70)
    print(f"🔍 Query #{idx}: {query}")
    print("="*70)
    
    # Add query to markdown
    md_content.append(f"\n## 🔍 Question {idx}\n")
    md_content.append(f"**{query}**\n")
    
    # Search similar docs from fitness handbook
    results = vectorstore.similarity_search(query, k=3)
    context = "\n".join([r.page_content for r in results])
    
    print("\n📚 Top 3 Retrieved Context from Handbook:")
    for i, doc in enumerate(results, 1):
        preview = doc.page_content[:100].replace('\n', ' ')
        print(f"{i}. {preview}...")
    
    # AI-powered exercise search with function calling
    print("\n🔍 AI searching exercises using function calling...")
    
    # Use AI function calling to intelligently search exercises
    all_exercises = ai_search_with_function_calling(query, exercise_db, client, user_profile)
    
    if all_exercises:
        # Format for LLM
        exercise_context = exercise_db.format_exercises_for_llm(all_exercises)  # Limit to 6 exercises
    
    else:
        exercise_context = "No specific exercises found in the database for this query."
        print("   ⚠️ No exercises found in database")
        
    # Ask LLM
    print("\n🤖 Generating personalized answer with exercise recommendations...")
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": f"""You are an experienced personal fitness coach with years of training experience. 

CRITICAL: You must respond in the SAME LANGUAGE as the user's question.
- If the question is in English, respond in English.
- If the question is in Arabic, respond in Arabic (Egyptian dialect).

CLIENT PROFILE:
- Name: {user_profile['name']}, Age: {user_profile['age']}
- Fitness Level: {user_profile['fitness_level']}
- Medical Conditions: {', '.join(user_profile['medical_conditions']) if user_profile['medical_conditions'] else 'None'}
- Previous Injuries: {', '.join(user_profile['injuries']) if user_profile['injuries'] else 'None'}
- Exercise Restrictions: {', '.join(user_profile['restrictions']) if user_profile['restrictions'] else 'None'}

YOUR APPROACH:
- Speak as a coach, NOT as someone reading from a book or manual
- Never mention "the handbook", "according to the guide", "the fitness manual" or similar references
- Give advice based on YOUR professional experience and expertise
- Be conversational, encouraging, and supportive like a real trainer
- Always consider the client's medical conditions and restrictions
- Provide safe alternatives and modifications when needed
- Use specific exercise names, rep ranges, and practical tips
- Be direct and actionable - give clear steps they can follow today And be direct; don't use "Hi, user, let's go..." or whatever; just be direct.

Remember: You're their trusted coach who knows their limitations and is here to help them succeed safely.

IMPORTANT: I will provide you with specific exercises from a professional database. Use these exercises in your recommendations when relevant. Include exercise names, instructions, and explain why each exercise is suitable for the client's profile."""},
            {"role": "user", "content": f"""Reference information from fitness knowledge:
{context}

Available exercises from professional database:
{exercise_context}

Question: {query}

Give me your professional advice as my coach, considering my profile and limitations. Use the specific exercises from the database when relevant, and explain why they're good choices for my situation. Be practical and specific."""}
        ],
        model="openai/gpt-oss-120b",
        temperature=0,
        max_tokens=2000,
    )
    
    answer = chat_completion.choices[0].message.content
    print("✅ Answer generated and saved to markdown file\n")
    
    # Add answer to markdown
    md_content.append("\n### 💡 Coach's Answer\n")
    md_content.append(f"{answer}\n")
    md_content.append("\n---\n")

# Write all content to markdown file
with open(output_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(md_content))


print("="*70)
print(f"✅ Testing Complete! Processed {len(queries)} fitness queries")
print(f"📄 Results saved to: {output_file}")
print("="*70)