"""Sentiment analyst using pre-fetched news/event data for a target ticker.

The agent pre-fetches ticker news before the LLM is invoked and injects it
into the prompt as a structured block. It deliberately does not fetch Reddit,
StockTwits, or other forum/community streams because those sources add noise
for the A-share workflow.

The agent does not use tool-calling; the data is in the prompt from turn 0.
Output uses the structured-output pattern, falling back to free-text generation
for providers that lack native support, so the sentiment header is consistent
across runs and providers.
"""

from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.schemas import SentimentReport, render_sentiment_report
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_news,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    Pre-fetches news/event data, injects it into the prompt as a structured
    block, and produces a deterministic sentiment report via structured output
    with a free-text fallback for providers that do not support it.
    """
    structured_llm = bind_structured(llm, SentimentReport, "Sentiment Analyst")

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = get_instrument_context_from_state(state)

        # Forum/community streams are intentionally skipped; they were noisy
        # for A-share analysis. Sentiment is based on news and event flow only.
        news_block = get_news.func(ticker, start_date, end_date)

        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        formatted_messages = prompt.format_messages(messages=state["messages"])

        report_text = invoke_structured_or_freetext(
            structured_llm,
            llm,
            formatted_messages,
            render_sentiment_report,
            "Sentiment Analyst",
        )

        return {
            "messages": [AIMessage(content=report_text)],
            "sentiment_report": report_text,
        }

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
) -> str:
    """Assemble the sentiment-analyst system message with structured data blocks."""
    return f"""You are a financial market sentiment analyst. Produce a concise sentiment report for {ticker} covering the period from {start_date} to {end_date}, using only the news/event data already collected for you.

## Data sources (pre-fetched, in this prompt)

### News headlines and market event data, past 7 days
Fact-driven signal. Treat news, policy, macro, company announcements, and sector events as the only sentiment inputs. Do not infer sentiment from Reddit, StockTwits, or other forum/community posts.

<start_of_news>
{news_block}
<end_of_news>

## How to analyze this data

1. Separate confirmed events from interpretation. A policy, earnings item, contract, regulatory action, or sector move is stronger evidence than vague commentary.
2. Identify recurring narrative themes across the collected news.
3. Map each signal to direction and confidence: bullish, bearish, mixed, or neutral.
4. Be honest about data limits. If news sources are sparse, stale, or unavailable, say so.
5. Identify catalysts and risks from news/event data, including policy, earnings, product launches, competitive threats, macro headlines, and sector rotation.
6. Sentiment is not predictive by itself. Frame conclusions as signal for the trader to weigh alongside fundamentals and technicals.

## Output fields

Fill the following fields:

- **overall_band**: Exactly one of Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. Use Mixed when sources point in clearly different directions; Neutral only when all sources are genuinely silent.
- **overall_score**: A number from 0 (maximally bearish) to 10 (maximally bullish); 5 is neutral. Keep it consistent with overall_band.
- **confidence**: low / medium / high, based on data quality and sample size.
- **narrative**: Source-by-source news/event breakdown, dominant narrative themes, catalysts and risks, and a markdown summary table of key sentiment signals (direction, source, supporting evidence).

{get_language_instruction()}"""


def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`."""
    import warnings

    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
