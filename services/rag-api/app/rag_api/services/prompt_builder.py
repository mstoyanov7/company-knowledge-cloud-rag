from rag_api.ports import PromptContext
from shared_schemas import Citation, ChunkDocument
from rag_api.services.context_builder import AnswerContext, build_answer_context
from rag_api.services.evidence_profile import build_evidence_profile, format_plan_instruction
from rag_api.services.query_understanding import QuestionAnalysis, analyze_question


class PromptBuilder:
    system_instruction = (
        "ROLE: You are a OneNote retrieval assistant for company knowledge, including readable OneNote "
        "attachments. You reply like a knowledgeable teammate: polished, conversational, easy to scan. "
        ""
        "GROUNDING RULES: Answer only from the retrieved context supplied by the backend. Do not use outside "
        "knowledge, assumptions, memory, or unsupported reasoning. Use only chunks that directly answer the "
        "user's specific question; ignore chunks that are unrelated, only loosely related, or contain only "
        "titles or headings. Never answer from a title, heading, section name, or filename alone. You may "
        "interpret the user's wording using the provided internal question analysis, but do not reveal that "
        "analysis and do not expose hidden reasoning. "
        ""
        "SYNTHESIS RULES: Combine every directly relevant chunk into ONE complete answer written in your own "
        "words — as if all the knowledge came from a single source. When the answer is spread across several "
        "pages, merge their facts seamlessly; do not answer page by page and do not repeat a fact found on two "
        "pages. Content labeled with a Page and an Attached file belongs to that same OneNote page; treat them "
        "as one knowledge source. Include all directly relevant details, not only the first sentence. Do not "
        "copy raw note text unless the user explicitly asks for exact wording. "
        ""
        "FORMAT DECISION: Choose the answer format from the COLLECTED EVIDENCE and the question — never mirror "
        "the source notes' formatting. The notes' line breaks, indentation, bullet symbols, and table fragments "
        "are irrelevant; normalize everything into readable paragraphs, bullets, numbered steps, or Markdown "
        "tables, whichever fits the content best. Plain facts read best as short paragraphs. Processes read "
        "best as one numbered sequence. Commands, configuration, scripts, JSON, YAML, code, environment "
        "variables, and terminal output always go in fenced Markdown code blocks with the best language hint "
        "(bash, powershell, json, yaml, python, text); code gathered from several blocks is merged into a "
        "single coherent fenced block in logical execution order. Keep short identifiers, file paths, and "
        "variable names as inline code. For schedules, agendas, timelines, and hour-by-hour notes, include the "
        "complete sequence from earliest to latest time and format it as a clean Markdown table when practical. "
        "Start with a brief direct answer, then details. Use at most one short heading; never repeat a heading. "
        "Bold only whole words or phrases and never place ** inside a value: write **10:00**, never **10**:00 "
        "or 10:**00**. Use code formatting only for real commands, identifiers, paths, and configuration - "
        "never wrap ordinary sentences or plain phrases in backticks or code blocks. "
        ""
        "EXAMPLE A (source uses bullets, answer should not): context block: '- VPN: AnyConnect - MFA: push - "
        "Portal: Self-Service' -> good answer: 'Connect with Cisco AnyConnect and approve the MFA push; if the "
        "profile is broken, reinstall it from the Self-Service Portal. [1]' "
        "EXAMPLE B (code from two pages becomes one block): blocks [1] 'git clone ...' and [2] 'pip install -e .' "
        "-> good answer ends with one fenced bash block containing both commands in execution order, cited [1][2]. "
        ""
        "CITATIONS: Each retrieved context block is labeled with a numeric marker such as [1] or [2]. When a "
        "sentence or section relies on facts from a block, append that block's marker at the end of the "
        "sentence. Cite every block you draw facts from, and never invent a marker number that is not present "
        "in the retrieved context. Do not add a separate Source or Sources line; use only the inline [n] markers. "
        ""
        "REFUSAL: If the retrieved context does not directly contain the answer, reply exactly: "
        "I could not find that information in the available OneNote notes or readable attachments."
    )

    def build(
        self,
        question: str,
        chunks: list[ChunkDocument],
        citations: list[Citation],
        *,
        question_analysis: QuestionAnalysis | None = None,
        answer_context: AnswerContext | None = None,
        topic_name: str | None = None,
        topic_description: str | None = None,
        answer_depth: str = "normal",
        answer_style: str | None = None,
    ) -> PromptContext:
        analysis = question_analysis or analyze_question(question)
        context = answer_context or build_answer_context(
            analysis,
            chunks,
            citations,
            max_chars=_context_budget(answer_depth),
        )
        system_instruction = self.system_instruction
        system_instruction = f"{system_instruction} {_depth_instruction(answer_depth)}"
        plan_instruction = format_plan_instruction(build_evidence_profile(chunks))
        if plan_instruction:
            system_instruction = f"{system_instruction}{plan_instruction}"
        mode_instruction = _mode_instruction(analysis, answer_style)
        if mode_instruction:
            system_instruction = f"{system_instruction} {mode_instruction}"
        if answer_style:
            system_instruction = (
                f"{system_instruction} Preferred answer style: {answer_style}. Keep this style grounded in the retrieved context."
            )
        if topic_name:
            topic_context = f" Selected topic: {topic_name}."
            if topic_description:
                topic_context += f" Topic description: {topic_description}."
            topic_context += " Keep the answer inside this selected topic unless the retrieved context says there is no information."
            system_instruction = f"{system_instruction}{topic_context}"
        return PromptContext(
            system_instruction=system_instruction,
            user_question=question,
            context_blocks=list(context.context_blocks),
            citations=citations,
            question_analysis={
                "detected_language": analysis.detected_language,
                "answer_type": analysis.answer_type,
                "important_entities": list(analysis.important_entities),
                "key_phrases": list(analysis.key_phrases),
                "rewritten_question": analysis.rewritten_question,
                "semantic_queries": list(analysis.semantic_queries),
                "keyword_queries": list(analysis.keyword_queries),
                "must_have_concepts": list(analysis.must_have_concepts),
                "avoid_concepts": list(analysis.avoid_concepts),
                "expected_evidence_type": analysis.expected_evidence_type,
                "specificity": analysis.specificity,
                "selected_topic": topic_name,
                "answer_depth": answer_depth,
                "answer_style": answer_style,
            },
            source_titles=list(context.source_titles),
        )


_STEP_BY_STEP_INSTRUCTION = (
    "This is a setup, installation, or how-to question. Answer in a step-by-step structure using the retrieved context. "
    "When the context contains them, include these sections as Markdown sub-headings in this order: "
    "Direct answer, Prerequisites, Installation commands, Configuration, Run, Verification, Troubleshooting. "
    "Put every command, script, or config example in a fenced code block with a language hint. "
    "Preserve configuration file names and setting names exactly. "
    "Do not stop after the first matching sentence, do not answer from page metadata or titles alone, "
    "and do not invent steps, commands, or dependencies that are not in the context. "
    "Ignore title-only and table-of-contents-only content and never include corrupted fragments or single stray letters."
)

_CHECKLIST_INSTRUCTION = (
    "Format the answer as a checklist using Markdown checkbox bullets (\"- [ ] item\") drawn only from the retrieved context, "
    "keeping each item actionable and grounded."
)

_TROUBLESHOOTING_INSTRUCTION = (
    "This is a troubleshooting question. For each relevant issue in the context, present it as: "
    "Problem, Possible cause, Fix, and Verification when available. "
    "Preserve exact error names, commands, and file names, and do not invent fixes that are not in the context."
)


def _mode_instruction(analysis: QuestionAnalysis, answer_style: str | None) -> str:
    style = (answer_style or "").lower()
    answer_type = analysis.answer_type
    if "checklist" in style:
        return _CHECKLIST_INSTRUCTION
    if answer_type == "troubleshooting" or "troubleshoot" in style:
        return _TROUBLESHOOTING_INSTRUCTION
    if answer_type == "steps" or any(term in style for term in ("step", "setup", "install", "how to")):
        return _STEP_BY_STEP_INSTRUCTION
    return ""


def _depth_instruction(answer_depth: str) -> str:
    if answer_depth == "concise":
        return (
            "Answer depth: concise. Give the shortest complete grounded answer, but still include every directly required fact."
        )
    if answer_depth == "detailed":
        return (
            "Answer depth: detailed. If the context supports it, provide a complete knowledge-card answer: "
            "first a short direct answer, then a detailed explanation, then steps, bullets, or a table where useful. "
            "Use fenced code blocks for any commands, code, or config examples found in the context. "
            "Use all directly relevant details and multiple relevant sentences or paragraphs from the retrieved context when they answer the question. "
            "Do not omit relevant caveats, limits, prerequisites, or follow-up actions found in the context."
        )
    return (
        "Answer depth: normal. Provide a complete grounded answer with enough detail to be useful without adding unsupported facts."
    )


def _context_budget(answer_depth: str) -> int:
    if answer_depth == "concise":
        return 5000
    if answer_depth == "detailed":
        return 10000
    return 7000
