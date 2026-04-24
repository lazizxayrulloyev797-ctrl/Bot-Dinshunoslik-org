"""
=====================================================
  PDF QUIZ BOT - Telegram bot (multi-PDF versiya)
  Railway deployment uchun moslashtirilgan
=====================================================
"""

import os
import random
import logging
import pdfplumber
from datetime import datetime

from telegram import (
    Update,
    Poll,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    PollAnswerHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =====================================================
#                   SOZLAMALAR
#   Railway > Variables bo'limida qo'shing:
#     BOT_TOKEN  =  BotFatherdan olgan token
#     WEBHOOK_URL = https://your-app.up.railway.app
# =====================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8797376130:AAGPmiJekbXdfVBjAJCsSmmB2yuXWD_Hf7M")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://web-production-08b6c.up.railway.app")      # https://your-app.up.railway.app
PORT = int(os.environ.get("PORT", 8443))             # Railway avtomatik o'rnatadi

# =====================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# =====================================================
#              GLOBAL MA'LUMOTLAR
# =====================================================
user_pdfs = {}
user_pdf_counter = {}
user_quiz_state = {}
poll_to_user = {}


# =====================================================
#              MENYU TUGMALARI
# =====================================================
BTN_QUIZ = "🚀 Testni boshlash"
BTN_STOP = "🛑 To'xtatish"
BTN_RESULT = "📊 Natija"
BTN_PDFS = "📚 PDF lar"
BTN_HELP = "ℹ️ Yordam"

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_QUIZ), KeyboardButton(BTN_STOP)],
        [KeyboardButton(BTN_PDFS), KeyboardButton(BTN_RESULT)],
        [KeyboardButton(BTN_HELP)],
    ],
    resize_keyboard=True,
    input_field_placeholder="Tugmani tanlang yoki PDF yuboring...",
)


# =====================================================
#              PDF NI O'QISH
# =====================================================
def parse_pdf_to_questions(pdf_path: str):
    questions = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                cleaned = []
                for row in table:
                    if row and any(cell and str(cell).strip() for cell in row):
                        text = " ".join(
                            str(c).strip() for c in row if c and str(c).strip()
                        )
                        text = text.lstrip("-").strip()
                        cleaned.append(text)

                for i in range(0, len(cleaned), 5):
                    chunk = cleaned[i: i + 5]
                    if len(chunk) < 5:
                        continue

                    question_text = chunk[0]
                    correct_answer = chunk[1]
                    wrong_answers = chunk[2:5]

                    if len(question_text) > 300:
                        question_text = question_text[:297] + "..."

                    def trim(s):
                        return (s[:97] + "...") if len(s) > 100 else s

                    correct_answer = trim(correct_answer)
                    wrong_answers = [trim(w) for w in wrong_answers]

                    questions.append({
                        "question": question_text,
                        "correct_answer": correct_answer,
                        "wrong_answers": wrong_answers,
                    })
    return questions


def shuffle_options(question_data: dict):
    correct = question_data["correct_answer"]
    wrong = question_data["wrong_answers"]
    all_options = [correct] + list(wrong)
    random.shuffle(all_options)
    correct_id = all_options.index(correct)
    return all_options, correct_id


def get_user_pdfs(user_id: int) -> dict:
    return user_pdfs.get(user_id, {})


def get_pdf_short_name(name: str, max_len: int = 30) -> str:
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    if len(name) > max_len:
        return name[:max_len - 1] + "…"
    return name


# =====================================================
#                  KOMANDALAR
# =====================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 <b>Salom!</b>\n"
        "Men <b>PDF Quiz Bot</b>man.\n\n"
        "📄 Menga bir nechta PDF fayl yuborishingiz mumkin.\n"
        "🚀 Testni boshlaganda — qaysi PDF bilan ishlashni tanlaysiz.\n\n"
        "🎲 Savollar va javoblar random tartibda keladi.\n"
        "✅ Bitta sessiyada savollar takrorlanmaydi.\n\n"
        "👇 Boshlaymizmi?"
    )
    await update.message.reply_text(text, reply_markup=MAIN_MENU, parse_mode="HTML")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ <b>Yordam</b>\n\n"
        "<b>Qadamlar:</b>\n"
        "1️⃣ Bir yoki bir nechta PDF yuboring\n"
        "2️⃣ <b>🚀 Testni boshlash</b> ni bosing\n"
        "3️⃣ Qaysi PDF bilan ishlashni tanlang\n"
        "4️⃣ Savollarga javob bering\n\n"
        "<b>Tugmalar:</b>\n"
        "🚀 Testni boshlash — quizni boshlash (PDF tanlash)\n"
        "🛑 To'xtatish — to'xtatib natijani ko'rish\n"
        "📚 PDF lar — yuklangan PDF lar ro'yxati\n"
        "📊 Natija — joriy holat\n"
        "ℹ️ Yordam — bu menyu\n\n"
        "<b>PDF talabi:</b>\n"
        "Har jadval 5 qatorli:\n"
        "1-qator → savol\n"
        "2-qator → TO'G'RI javob\n"
        "3, 4, 5-qator → noto'g'ri javoblar"
    )
    await update.message.reply_text(text, reply_markup=MAIN_MENU, parse_mode="HTML")


# =====================================================
#              PDF QABUL QILISH
# =====================================================
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    document = update.message.document

    if not document.file_name.lower().endswith(".pdf"):
        await update.message.reply_text(
            "❌ Iltimos, faqat PDF fayl yuboring.",
            reply_markup=MAIN_MENU,
        )
        return

    await update.message.reply_text(
        "⏳ PDF qayta ishlanmoqda, kuting...",
        reply_markup=MAIN_MENU,
    )

    file = await document.get_file()
    # /tmp papkasi Railway serverida yozish uchun mavjud
    pdf_path = f"/tmp/pdf_{user_id}_{datetime.now().timestamp()}.pdf"
    await file.download_to_drive(pdf_path)

    try:
        questions = parse_pdf_to_questions(pdf_path)
    except Exception as e:
        logger.exception("PDF parse xatosi")
        await update.message.reply_text(
            f"❌ Xatolik: {e}",
            reply_markup=MAIN_MENU,
        )
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        return

    if os.path.exists(pdf_path):
        os.remove(pdf_path)

    if not questions:
        await update.message.reply_text(
            "❌ PDF dan savollar topilmadi.\nJadvallar 5 qatorli bo'lishi kerak.",
            reply_markup=MAIN_MENU,
        )
        return

    counter = user_pdf_counter.get(user_id, 0) + 1
    user_pdf_counter[user_id] = counter
    pdf_id = counter

    if user_id not in user_pdfs:
        user_pdfs[user_id] = {}

    user_pdfs[user_id][pdf_id] = {
        "name": document.file_name,
        "questions": questions,
        "uploaded_at": datetime.now().strftime("%H:%M %d.%m.%Y"),
    }

    total_pdfs = len(user_pdfs[user_id])
    short_name = get_pdf_short_name(document.file_name, 40)

    await update.message.reply_text(
        f"✅ PDF saqlandi!\n\n"
        f"📄 <b>{short_name}</b>\n"
        f"❓ Savollar: <b>{len(questions)}</b> ta\n"
        f"📚 Jami PDF lar: <b>{total_pdfs}</b>\n\n"
        f"👇 Quizni boshlash uchun <b>🚀 Testni boshlash</b> ni bosing.",
        reply_markup=MAIN_MENU,
        parse_mode="HTML",
    )


# =====================================================
#              PDF TANLASH
# =====================================================
async def show_pdf_selection(update_or_msg, user_id: int, context: ContextTypes.DEFAULT_TYPE, action: str = "start"):
    pdfs = get_user_pdfs(user_id)

    if hasattr(update_or_msg, 'message'):
        send = update_or_msg.message.reply_text
    else:
        send = update_or_msg.reply_text

    if not pdfs:
        await send(
            "📭 Sizda hali PDF yo'q.\n\nMenga PDF fayl yuboring.",
            reply_markup=MAIN_MENU,
        )
        return

    if action == "start":
        buttons = []
        for pdf_id, info in pdfs.items():
            short = get_pdf_short_name(info["name"], 28)
            count = len(info["questions"])
            buttons.append([
                InlineKeyboardButton(
                    f"📄 {short} ({count})",
                    callback_data=f"start_pdf:{pdf_id}",
                )
            ])

        keyboard = InlineKeyboardMarkup(buttons)
        await send(
            f"📚 <b>Sizda {len(pdfs)} ta PDF bor.</b>\n\n"
            f"Qaysi PDF bilan testni boshlaymiz?",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    elif action == "list":
        text = f"📚 <b>Yuklangan PDF lar ({len(pdfs)} ta):</b>\n\n"
        buttons = []
        for pdf_id, info in pdfs.items():
            short = get_pdf_short_name(info["name"], 30)
            count = len(info["questions"])
            text += f"📄 <b>{short}</b>\n   ❓ {count} ta savol • 🕐 {info['uploaded_at']}\n\n"
            buttons.append([
                InlineKeyboardButton(
                    f"🚀 {get_pdf_short_name(info['name'], 18)}",
                    callback_data=f"start_pdf:{pdf_id}",
                ),
                InlineKeyboardButton(
                    "🗑",
                    callback_data=f"del_pdf:{pdf_id}",
                ),
            ])

        keyboard = InlineKeyboardMarkup(buttons)
        await send(text, reply_markup=keyboard, parse_mode="HTML")


# =====================================================
#              SAVOLNI YUBORISH
# =====================================================
async def send_next_question(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    state = user_quiz_state.get(user_id)
    if not state or not state.get("running"):
        return

    pdf_id = state["pdf_id"]
    pdfs = get_user_pdfs(user_id)
    if pdf_id not in pdfs:
        await context.bot.send_message(
            state["chat_id"],
            "⚠️ Quiz ishlayotgan PDF o'chirib yuborilgan.",
            reply_markup=MAIN_MENU,
        )
        user_quiz_state.pop(user_id, None)
        return

    questions = pdfs[pdf_id]["questions"]
    chat_id = state["chat_id"]
    queue = state["queue"]

    if not queue:
        await finish_quiz(user_id, context, completed=True)
        return

    q_index = queue.pop(0)
    state["asked"].append(q_index)

    q = questions[q_index]
    options, correct_id = shuffle_options(q)

    asked_count = len(state["asked"])
    total = state["total"]

    try:
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"{asked_count}/{total}. {q['question']}",
            options=options,
            type=Poll.QUIZ,
            correct_option_id=correct_id,
            is_anonymous=False,
        )
        poll_id = message.poll.id
        state["current_poll_id"] = poll_id
        state["current_correct_id"] = correct_id
        poll_to_user[poll_id] = user_id

    except Exception as e:
        logger.error(f"Poll yuborishda xato: {e}")
        await context.bot.send_message(
            chat_id,
            f"⚠️ Savol yuborilmadi: {e}\nKeyingisiga o'tamiz...",
            reply_markup=MAIN_MENU,
        )
        await send_next_question(user_id, context)


# =====================================================
#         FOYDALANUVCHI JAVOB BERGANDA
# =====================================================
async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = poll_to_user.get(poll_id)

    if user_id is None:
        return

    state = user_quiz_state.get(user_id)
    if not state or not state.get("running"):
        return

    if state.get("current_poll_id") != poll_id:
        return

    selected = answer.option_ids[0] if answer.option_ids else -1
    correct_id = state.get("current_correct_id", -1)

    if selected == correct_id:
        state["correct"] += 1
    else:
        state["wrong"] += 1

    poll_to_user.pop(poll_id, None)
    await send_next_question(user_id, context)


# =====================================================
#                NATIJA MATNI
# =====================================================
def build_progress_text(state: dict, pdf_name: str = "") -> str:
    correct = state["correct"]
    wrong = state["wrong"]
    answered = correct + wrong
    asked = len(state["asked"])
    total = state["total"]

    percent = (correct / answered * 100) if answered > 0 else 0

    text = ""
    if pdf_name:
        text += f"📄 <b>{get_pdf_short_name(pdf_name, 35)}</b>\n\n"

    text += (
        f"📊 <b>Natija:</b>\n\n"
        f"📚 Jami savollar: <b>{total}</b>\n"
        f"❓ So'ralgan: <b>{asked}</b>\n"
        f"✅ To'g'ri: <b>{correct}</b>\n"
        f"❌ Noto'g'ri: <b>{wrong}</b>\n"
        f"📈 Foiz: <b>{percent:.1f}%</b>"
    )
    return text


# =====================================================
#                QUIZ FUNKSIYALARI
# =====================================================
def has_resumable_quiz(user_id: int) -> bool:
    state = user_quiz_state.get(user_id)
    if not state:
        return False
    if not state.get("running") and state.get("queue"):
        pdf_id = state.get("pdf_id")
        if pdf_id in get_user_pdfs(user_id):
            return True
    return False


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    pdfs = get_user_pdfs(user_id)
    if not pdfs:
        await update.message.reply_text(
            "❌ Avval menga PDF fayl yuboring.",
            reply_markup=MAIN_MENU,
        )
        return

    state = user_quiz_state.get(user_id)
    if state and state.get("running"):
        await update.message.reply_text(
            "⚠️ Quiz allaqachon ishlamoqda.\n🛑 To'xtatish uchun tugmani bosing.",
            reply_markup=MAIN_MENU,
        )
        return

    if has_resumable_quiz(user_id):
        pdf_id = state["pdf_id"]
        pdf_info = pdfs[pdf_id]
        remaining = len(state["queue"])
        asked = len(state["asked"])
        total = state["total"]

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"▶️ Davom etish ({remaining} qoldi)",
                    callback_data="resume",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔄 Boshqa PDF tanlash",
                    callback_data="choose_pdf",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🆕 Boshidan boshlash (shu PDF)",
                    callback_data=f"start_pdf:{pdf_id}",
                ),
            ],
        ])

        await update.message.reply_text(
            f"♻️ <b>Tugamagan quiz bor:</b>\n\n"
            f"📄 {get_pdf_short_name(pdf_info['name'], 30)}\n"
            f"❓ So'ralgan: <b>{asked}/{total}</b>\n"
            f"✅ To'g'ri: <b>{state['correct']}</b>\n"
            f"❌ Noto'g'ri: <b>{state['wrong']}</b>\n\n"
            f"Qanday davom etamiz?",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    if len(pdfs) == 1:
        pdf_id = list(pdfs.keys())[0]
        await start_new_quiz(user_id, chat_id, pdf_id, context)
        return

    await show_pdf_selection(update, user_id, context, action="start")


async def start_new_quiz(user_id: int, chat_id: int, pdf_id: int, context: ContextTypes.DEFAULT_TYPE):
    pdfs = get_user_pdfs(user_id)
    if pdf_id not in pdfs:
        await context.bot.send_message(
            chat_id,
            "❌ Bu PDF topilmadi.",
            reply_markup=MAIN_MENU,
        )
        return

    pdf_info = pdfs[pdf_id]
    questions = pdf_info["questions"]
    total = len(questions)

    indices = list(range(total))
    random.shuffle(indices)

    user_quiz_state[user_id] = {
        "running": True,
        "chat_id": chat_id,
        "pdf_id": pdf_id,
        "queue": indices,
        "asked": [],
        "current_poll_id": None,
        "current_correct_id": -1,
        "correct": 0,
        "wrong": 0,
        "total": total,
    }

    await context.bot.send_message(
        chat_id,
        f"🚀 <b>Quiz boshlandi!</b>\n\n"
        f"📄 {get_pdf_short_name(pdf_info['name'], 35)}\n"
        f"📚 Jami: <b>{total}</b> ta savol\n"
        f"🎲 Tartib random — takrorlanmaydi.\n"
        f"🛑 To'xtatish uchun tugmani bosing.",
        reply_markup=MAIN_MENU,
        parse_mode="HTML",
    )

    await send_next_question(user_id, context)


async def resume_quiz(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    state = user_quiz_state.get(user_id)
    if not state:
        return

    state["running"] = True
    remaining = len(state["queue"])

    pdfs = get_user_pdfs(user_id)
    pdf_info = pdfs.get(state["pdf_id"], {})
    pdf_name = pdf_info.get("name", "")

    await context.bot.send_message(
        chat_id,
        f"▶️ <b>Davom etamiz!</b>\n"
        f"📄 {get_pdf_short_name(pdf_name, 30)}\n"
        f"❓ Qolgan savollar: <b>{remaining}</b>",
        reply_markup=MAIN_MENU,
        parse_mode="HTML",
    )

    await send_next_question(user_id, context)


# =====================================================
#         INLINE TUGMA BOSILGANDA
# =====================================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    if data == "resume":
        await query.edit_message_text("▶️ Davom etamiz...")
        await resume_quiz(user_id, chat_id, context)

    elif data == "choose_pdf":
        await query.edit_message_text("📚 PDF tanlang:")
        await show_pdf_selection(query, user_id, context, action="start")

    elif data.startswith("start_pdf:"):
        pdf_id = int(data.split(":")[1])
        pdfs = get_user_pdfs(user_id)
        if pdf_id not in pdfs:
            await query.edit_message_text("❌ Bu PDF endi mavjud emas.")
            return
        name = get_pdf_short_name(pdfs[pdf_id]["name"], 30)
        await query.edit_message_text(f"📄 Tanlandi: {name}")
        await start_new_quiz(user_id, chat_id, pdf_id, context)

    elif data.startswith("del_pdf:"):
        pdf_id = int(data.split(":")[1])
        pdfs = get_user_pdfs(user_id)
        if pdf_id in pdfs:
            name = pdfs[pdf_id]["name"]

            state = user_quiz_state.get(user_id)
            if state and state.get("pdf_id") == pdf_id:
                user_quiz_state.pop(user_id, None)

            del pdfs[pdf_id]

            await query.edit_message_text(
                f"🗑 <b>{get_pdf_short_name(name, 30)}</b> o'chirildi.",
                parse_mode="HTML",
            )
            if pdfs:
                await show_pdf_selection(query, user_id, context, action="list")
            else:
                await context.bot.send_message(
                    chat_id,
                    "📭 Endi sizda PDF yo'q. Yangi PDF yuboring.",
                    reply_markup=MAIN_MENU,
                )


# =====================================================
#                QUIZNI TUGATISH
# =====================================================
async def finish_quiz(user_id: int, context: ContextTypes.DEFAULT_TYPE, completed: bool = True):
    state = user_quiz_state.get(user_id)
    if not state:
        return

    chat_id = state["chat_id"]
    state["running"] = False

    old_poll = state.get("current_poll_id")
    if old_poll:
        poll_to_user.pop(old_poll, None)
    state["current_poll_id"] = None

    pdfs = get_user_pdfs(user_id)
    pdf_info = pdfs.get(state["pdf_id"], {})
    pdf_name = pdf_info.get("name", "")

    if completed:
        title = "🎉 <b>Quiz tugadi!</b>\n\n"
        await context.bot.send_message(
            chat_id,
            title + build_progress_text(state, pdf_name) + "\n\nYangi quiz uchun: 🚀 Testni boshlash",
            reply_markup=MAIN_MENU,
            parse_mode="HTML",
        )
        user_quiz_state.pop(user_id, None)
    else:
        title = "🛑 <b>Quiz to'xtatildi.</b>\n\n"
        await context.bot.send_message(
            chat_id,
            title + build_progress_text(state, pdf_name) + "\n\n♻️ Davom etish uchun: 🚀 Testni boshlash",
            reply_markup=MAIN_MENU,
            parse_mode="HTML",
        )


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_quiz_state.get(user_id)

    if not state or not state.get("running"):
        await update.message.reply_text(
            "ℹ️ Hozirda quiz ishlamayapti.",
            reply_markup=MAIN_MENU,
        )
        return

    await finish_quiz(user_id, context, completed=False)


async def result_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_quiz_state.get(user_id)

    if not state:
        await update.message.reply_text(
            "📭 Hozirda quiz yo'q.\nAvval 🚀 Testni boshlash ni bosing.",
            reply_markup=MAIN_MENU,
        )
        return

    pdfs = get_user_pdfs(user_id)
    pdf_info = pdfs.get(state["pdf_id"], {})
    pdf_name = pdf_info.get("name", "")

    status = "🟢 Davom etmoqda" if state.get("running") else "🔴 To'xtatilgan"
    text = f"{status}\n\n" + build_progress_text(state, pdf_name)

    await update.message.reply_text(
        text, reply_markup=MAIN_MENU, parse_mode="HTML"
    )


async def pdfs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await show_pdf_selection(update, user_id, context, action="list")


# =====================================================
#         MATN TUGMALARINI QABUL QILISH
# =====================================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == BTN_QUIZ:
        await quiz_cmd(update, context)
    elif text == BTN_STOP:
        await stop_cmd(update, context)
    elif text == BTN_RESULT:
        await result_cmd(update, context)
    elif text == BTN_PDFS:
        await pdfs_cmd(update, context)
    elif text == BTN_HELP:
        await help_cmd(update, context)
    else:
        await update.message.reply_text(
            "🤔 Tushunmadim.\nPastdagi tugmalardan foydalaning yoki PDF yuboring.",
            reply_markup=MAIN_MENU,
        )


# =====================================================
#         BOT ISHGA TUSHGANDA
# =====================================================
async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "🏠 Botni boshlash"),
        BotCommand("quiz", "🚀 Testni boshlash"),
        BotCommand("stop", "🛑 To'xtatish"),
        BotCommand("result", "📊 Natija"),
        BotCommand("pdfs", "📚 PDF lar ro'yxati"),
        BotCommand("help", "ℹ️ Yordam"),
    ])
    logger.info("Bot komandalari menyusi o'rnatildi.")


# =====================================================
#                       MAIN
# =====================================================
def main():
    if not BOT_TOKEN:
        print("=" * 60)
        print("❌ XATOLIK: BOT_TOKEN environment variable o'rnatilmagan!")
        print("Railway > Variables bo'limiga BOT_TOKEN qo'shing.")
        print("=" * 60)
        return

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .concurrent_updates(True)
        .build()
    )

    # Komandalar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("quiz", quiz_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("result", result_cmd))
    app.add_handler(CommandHandler("pdfs", pdfs_cmd))

    # PDF
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))

    # Inline tugmalar
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Quiz javoblari
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    # Pastdagi menyu
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # -----------------------------------------------
    #  WEBHOOK yoki POLLING — avtomatik tanlanadi
    # -----------------------------------------------
    if WEBHOOK_URL:
        # Railway deployment — Webhook rejimi
        webhook_path = f"/webhook/{BOT_TOKEN}"
        full_webhook_url = f"{WEBHOOK_URL.rstrip('/')}{webhook_path}"

        logger.info(f"Webhook rejimi: {full_webhook_url}")
        print("=" * 60)
        print("✅ BOT WEBHOOK REJIMIDA ISHGA TUSHDI!")
        print(f"🌐 URL: {full_webhook_url}")
        print("=" * 60)

        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=full_webhook_url,
            url_path=webhook_path,
            drop_pending_updates=True,
        )
    else:
        # Local ishlab chiqish — Polling rejimi
        logger.info("Polling rejimi (lokal ishlab chiqish)")
        print("=" * 60)
        print("✅ BOT POLLING REJIMIDA ISHGA TUSHDI! (lokal)")
        print("Railway uchun WEBHOOK_URL ni o'rnating.")
        print("To'xtatish: Ctrl + C")
        print("=" * 60)

        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
