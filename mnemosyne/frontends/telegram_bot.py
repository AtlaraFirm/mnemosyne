import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from mnemosyne.agent.loop import run as agent_run
from mnemosyne.config import get_settings
from mnemosyne.db.connection import get_history, init_db, save_messages
from mnemosyne.services.writes import apply_plan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_pending_plans = {}
_pending_plans_lock = asyncio.Lock()

# Simple in-memory rate limiter: {chat_id: [timestamps]}
_rate_limits = {}
RATE_LIMIT_WINDOW = 30  # seconds
RATE_LIMIT_MAX = 5  # max messages per window


def _rate_limited(chat_id: int) -> bool:
    import time

    now = time.time()
    window = RATE_LIMIT_WINDOW
    max_msgs = RATE_LIMIT_MAX
    times = _rate_limits.get(chat_id, [])
    # Remove timestamps outside the window
    times = [t for t in times if now - t < window]
    if len(times) >= max_msgs:
        _rate_limits[chat_id] = times
        return True
    times.append(now)
    _rate_limits[chat_id] = times
    return False


def _is_allowed(chat_id: int) -> bool:
    settings = get_settings()
    if not settings.telegram_allowed_chat_ids:
        return True
    return chat_id in settings.telegram_allowed_chat_ids


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "**Mnemosyne** — your Obsidian vault assistant\n\n"
        "/ask *question* — Q&A over vault\n"
        "/search *query* — keyword search\n"
        "/new *title* — create a note (follow prompts)\n"
        "/related *path* — find related notes\n"
        "/reindex — rebuild search index\n\n"
        "Or just send a message to chat with your vault."
    )
    await update.message.reply_markdown(text)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_chat.id):
        return
    if _rate_limited(update.effective_chat.id):
        await update.message.reply_text(
            "Rate limit: Please wait before sending more messages."
        )
        return
    chat_id = str(update.effective_chat.id)
    n = 10
    if context.args and context.args[0].isdigit():
        n = int(context.args[0])
    from mnemosyne.db.connection import get_history

    history = get_history(chat_id)[-n * 2 :]
    if not history:
        await update.message.reply_text("No history found.")
        return
    lines = []
    for msg in history:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        lines.append(f"*{role.title()}:* {content}")
    await update.message.reply_markdown("\n\n".join(lines[-n * 2 :]))


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_chat.id):
        return
    if _rate_limited(update.effective_chat.id):
        await update.message.reply_text(
            "Rate limit: Please wait before sending more messages."
        )
        return
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return
    from mnemosyne.services.index import search_fts

    results = search_fts(query, limit=5)
    if not results:
        await update.message.reply_text("No results found.")
        return
    lines = [
        f"• **{r.note_title}** ({r.note_path})\n  {r.excerpt[:120]}" for r in results
    ]
    await update.message.reply_markdown("\n\n".join(lines))


async def cmd_related(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_chat.id):
        return
    if _rate_limited(update.effective_chat.id):
        await update.message.reply_text(
            "Rate limit: Please wait before sending more messages."
        )
        return
    path = " ".join(context.args)
    if not path:
        await update.message.reply_text("Usage: /related <path>")
        return
    from mnemosyne.services.related import find_related

    results = find_related(path, limit=5)
    if not results:
        await update.message.reply_text("No related notes found.")
        return
    lines = [f"• [[{r['title']}]] ({r['path']}) — {r['score']}" for r in results]
    await update.message.reply_markdown("\n".join(lines))


async def cmd_reindex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_chat.id):
        return
    if _rate_limited(update.effective_chat.id):
        await update.message.reply_text(
            "Rate limit: Please wait before sending more messages."
        )
        return
    await update.message.reply_text("Reindexing vault...")
    from mnemosyne.services import embed as emb
    from mnemosyne.services import index as idx
    from mnemosyne.services import vault as v

    loop = asyncio.get_event_loop()

    def do_reindex():
        notes = v.crawl_vault()
        chunks = [c for note in notes for c in v.chunk_note(note)]
        idx.upsert_chunks(chunks)
        emb.ensure_collection()
        emb.index_chunks(chunks)
        return len(chunks)

    n = await loop.run_in_executor(None, do_reindex)
    await update.message.reply_text(f"✓ Reindexed {n} chunks.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not _is_allowed(update.effective_chat.id):
            return
        if _rate_limited(update.effective_chat.id):
            await update.message.reply_text(
                "Rate limit: Please wait before sending more messages."
            )
            return
        chat_id = str(update.effective_chat.id)
        text = update.message.text
        await update.message.reply_text("⏳ Searching your vault...")
        loop = asyncio.get_event_loop()
        history = get_history(chat_id)

        def do_agent():
            return agent_run(text, history)

        response = await loop.run_in_executor(None, do_agent)
        save_messages(
            chat_id,
            "telegram",
            [
                {"role": "user", "content": text},
                {"role": "assistant", "content": response.text},
            ],
        )
        reply = response.text
        if response.tool_calls_made:
            reply += f"\n\n_Tools: {', '.join(response.tool_calls_made)}_"
        await update.message.reply_markdown(reply)
        for plan in response.write_plans:
            async with _pending_plans_lock:
                _pending_plans[plan.plan_id] = plan
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Apply", callback_data=f"apply:{plan.plan_id}"
                        ),
                        InlineKeyboardButton(
                            "❌ Reject", callback_data=f"reject:{plan.plan_id}"
                        ),
                    ]
                ]
            )
            preview = plan.preview[:400] + ("..." if len(plan.preview) > 400 else "")
            await update.message.reply_text(
                f"**Proposed: {plan.operation}**\n`{plan.path}`\n\n```\n{preview}\n```",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
    except Exception:
        logger.exception("Error in handle_message")
        await update.message.reply_text("An error occurred. Please try again later.")
        preview = plan.preview[:400] + ("..." if len(plan.preview) > 400 else "")
        await update.message.reply_text(
            f"**Proposed: {plan.operation}**\n`{plan.path}`\n\n```\n{preview}\n```",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        action, plan_id = query.data.split(":", 1)
        async with _pending_plans_lock:
            plan = _pending_plans.pop(plan_id, None)
        if not plan:
            await query.edit_message_text(
                "This plan has already been handled or expired."
            )
            return
        if action == "apply":
            result = apply_plan(plan)
            await query.edit_message_text(f"✅ {result}")
        else:
            await query.edit_message_text("❌ Write rejected.")
    except Exception:
        logger.exception("Error in handle_callback")
        await update.callback_query.edit_message_text(
            "An error occurred. Please try again later."
        )


def run_bot():
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in .env")
    init_db()

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("related", cmd_related))
    app.add_handler(CommandHandler("reindex", cmd_reindex))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    logger.info("Mnemosyne bot starting...")
    app.run_polling()
