from rag_api.services.query_understanding import QueryPlanner, analyze_question, canonical_key_phrase


def test_analyze_question_extracts_generic_fields_without_domain_intents() -> None:
    analysis = analyze_question("Is there any info about overtime?")

    assert analysis.detected_language == "en"
    assert analysis.answer_type == "specific_fact"
    assert analysis.main_intent is None
    assert "overtime" in analysis.important_entities
    assert analysis.semantic_queries == ()
    assert analysis.keyword_queries
    assert analysis.expected_evidence_type == "direct_text_evidence"


def test_analyze_question_keeps_unknown_question_generic() -> None:
    analysis = analyze_question("What does the architecture diagram show?")

    assert analysis.original_question == "What does the architecture diagram show?"
    assert analysis.answer_type == "explanation"
    assert analysis.search_queries[0] == "What does the architecture diagram show?"
    assert "architecture" in analysis.important_entities
    assert "diagram" in analysis.important_entities


def test_canonical_key_phrase_is_dynamic_repeated_ngram() -> None:
    text = "thesis title main focus project thesis title objective"

    assert canonical_key_phrase(text) == "thesis title"


def test_query_planner_merges_llm_generated_queries_without_static_domain_rules() -> None:
    import asyncio

    class FakePlanningLlm:
        async def plan_queries(self, **kwargs):
            return {
                "original_question": kwargs["question"],
                "detected_language": "en",
                "answer_type": "definition",
                "important_entities": ["thesis", "project focus"],
                "rewritten_question": "definition answer about thesis title and project focus",
                "semantic_queries": [
                    "diploma work name objective",
                    "project goal research focus",
                    "main purpose of developed system",
                ],
                "keyword_queries": ["thesis title main project focus"],
                "expected_evidence_type": "direct_text_evidence",
            }

    analysis = asyncio.run(
        QueryPlanner(llm=FakePlanningLlm()).plan("What was the name of the thesis and the main focus of the project?")
    )

    assert analysis.rewritten_question == "definition answer about thesis title and project focus"
    assert "diploma work name objective" in analysis.semantic_queries
    assert "thesis title main project focus" in analysis.keyword_queries
    assert "project focus" in analysis.important_entities
