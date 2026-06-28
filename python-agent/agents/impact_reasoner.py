import os
import logging
from utils.ollama_client import OllamaClient

log = logging.getLogger(__name__)

IMPACT_SYSTEM_PROMPT = """
You are a financial markets analyst assistant. Your role is educational — helping
people understand how news events have historically affected markets.

You MUST follow these rules on every response:
- Never recommend buying or selling any security
- Never use the words: buy, sell, invest, purchase, short, guaranteed, price target,
  strong buy, strong sell, recommend, should buy, should sell
- Always express uncertainty — markets are unpredictable
- Always cite the specific news driving your analysis
- State what would change your assessment
- Output ONLY valid JSON matching the schema below — nothing else

OUTPUT SCHEMA:
{
  "event_type": "fed_rate|earnings|merger|regulatory|macro|other",
  "sentiment": "bullish|bearish|neutral",
  "confidence": 0.0-1.0,
  "affected_tickers": ["AAPL"],
  "affected_sectors": ["technology"],
  "time_horizon": "intraday|days|weeks|months",
  "impact_summary": "One paragraph explaining the likely market impact and historical context.",
  "historical_precedents": ["Brief reference to similar past events and their outcomes."],
  "uncertainty_factors": ["Specific factors that could make this analysis wrong."],
  "source_citations": ["Exact headline or source name that drove this analysis."],
  "disclaimer": "NOT FINANCIAL ADVICE. Educational analysis only."
}

If you cannot produce a confident analysis (confidence < 0.65), return ONLY:
{"signal": "no_signal", "reason": "Brief explanation of why analysis is not confident enough."}
"""


def analyze_impact(article: dict, sentiment: dict, rag_context: list[str], ollama: OllamaClient) -> dict:
    """
    Produce a structured impact analysis for the given article.
    Returns raw JSON dict — caller must pass through validate_signal() in guardrails.py.
    """
    context_text = (
        "\n---\n".join(rag_context[:3])
        if rag_context
        else "No recent historical context available."
    )

    prompt = f"""
Event type:    {article['event_type']}
Headline:      {article['headline']}
Sentiment:     {sentiment['sentiment']} (confidence: {sentiment['confidence']:.2f})
Tickers:       {article.get('tickers', [])}

Recent related news context (for historical comparison):
{context_text}

Analyze the likely market impact of this event for educational purposes.
Express genuine uncertainty. Do not recommend any action.
"""

    response = ollama.generate(
        model=os.getenv("IMPACT_REASONER_MODEL", "mistral"),
        system=IMPACT_SYSTEM_PROMPT,
        prompt=prompt,
    )

    return ollama.parse_json(response)
