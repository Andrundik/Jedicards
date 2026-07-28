import asyncio
from datetime import datetime, timedelta
import os
import random
import aiosqlite
from aiogram import Bot, Dispatcher, F, types

# Токен теперь автоматически берется из переменных окружения Render
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
  raise ValueError("Не найден токен! Укажи переменную BOT_TOKEN в настройках Render.")

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_NAME = "star_wars_bot.db"

# База всех доступных карточек (замени ссылки на свои картинки)
CARDS_DATABASE = [
    {
        "id": "jedi_holocron",
        "photo": "https://example.com/holocron_jedi.jpg",
        "caption": (
            "🌌 **Голокрон Джедаев**\n⭐ Очки мудрости: **250 XP**\n«Терпение —"
            " путь к Силе»."
        ),
    },
    {
        "id": "bounty_puck",
        "photo": "https://example.com/bounty_hunter.jpg",
        "caption": (
            "🎯 **Шар наемника**\n⭐ Кредиты: **500 CR**\n«Награда за голову"
            " назначена»."
        ),
    },
    {
        "id": "death_star_pass",
        "photo": "https://example.com/death_star.jpg",
        "caption": (
            "🔴 **Имперский допуск**\n⭐ Уровень угрозы: **Максимальный**\n«Слава"
            " Империи!»"
        ),
    },
    {
        "id": "lightsaber_kyber",
        "photo": "https://example.com/kyber.jpg",
        "caption": (
            "💎 **Кристалл Кайбер**\n⭐ Сила светового меча: **1000 XP**\n«Сердце"
            " меча — это кристалл»."
        ),
    },
]


# Инициализация базы данных
async def init_db():
  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute("""
            CREATE TABLE IF NOT EXISTS user_cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_used TEXT
            )
        """)
    await db.execute("""
            CREATE TABLE IF NOT EXISTS user_library (
                user_id INTEGER,
                card_id TEXT,
                count INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, card_id)
            )
        """)
    await db.commit()


# Выбор карточки с уменьшенным шансом для повторок
async def get_weighted_random_card(user_id: int):
  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT card_id, count FROM user_library WHERE user_id = ?", (user_id,)
    ) as cursor:
      rows = await cursor.fetchall()
      user_cards = {row[0]: row[1] for row in rows}

  cards_pool = []
  weights = []

  for card in CARDS_DATABASE:
    cards_pool.append(card)
    count = user_cards.get(card["id"], 0)

    if count == 0:
      weight = 10  # Высокий шанс для новых карточек
    else:
      weight = max(1, 10 // (count + 1))  # Меньше шанс для повторок

    weights.append(weight)

  return random.choices(cards_pool, weights=weights, k=1)[0]


# Обработка кодовой фразы
@dp.message(F.text.lower().in_(["да пребудет сила", "да прибудет сила"]))
async def handle_force_phrase(message: types.Message):
  user_id = message.from_user.id
  user_name = message.from_user.first_name
  now = datetime.now()

  async with aiosqlite.connect(DB_NAME) as db:
    # Проверка кулдауна (1 час)
    async with db.execute(
        "SELECT last_used FROM user_cooldowns WHERE user_id = ?", (user_id,)
    ) as cursor:
      row = await cursor.fetchone()

      if row:
        last_used_time = datetime.fromisoformat(row[0])
        time_diff = now - last_used_time

        if time_diff < timedelta(hours=1):
          remaining_minutes = int(
              (timedelta(hours=1) - time_diff).total_seconds() // 60
          )
          await message.reply(
              f"🌌 Сила еще восстанавливается, {user_name}. Следующую карточку"
              f" можно получить через **{remaining_minutes} мин.**"
          )
          return

  card = await get_weighted_random_card(user_id)

  async with aiosqlite.connect(DB_NAME) as db:
    # Сохранение карточки или увеличение счетчика копий
    await db.execute(
        """
            INSERT INTO user_library (user_id, card_id, count) VALUES (?, ?, 1)
            ON CONFLICT(user_id, card_id) DO UPDATE SET count = count + 1
        """,
        (user_id, card["id"]),
    )

    # Обновление таймера
    await db.execute(
        """
            INSERT INTO user_cooldowns (user_id, last_used) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_used = ?
        """,
        (user_id, now.isoformat(), now.isoformat()),
    )
    await db.commit()

  await message.answer_photo(
      photo=card["photo"],
      caption=(
          f"✨ **Сила услышала вас, {user_name}!**\nВ вашу личную библиотеку"
          f" добавлена карточка:\n\n{card['caption']}"
      ),
      parse_mode="Markdown",
  )


# Просмотр библиотеки (только собранные карточки)
@dp.message(F.text.lower() == "моя библиотека")
async def show_library(message: types.Message):
  user_id = message.from_user.id

  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT card_id, count FROM user_library WHERE user_id = ?", (user_id,)
    ) as cursor:
      rows = await cursor.fetchall()
      user_cards = {row[0]: row[1] for row in rows}

  if not user_cards:
    await message.reply(
        "📁 Ваша библиотека пуста. Напишите «Да пребудет сила», чтобы выбить"
        " первую карточку!"
    )
    return

  total_cards = len(CARDS_DATABASE)
  collected_unique = len(user_cards)

  text = (
      f"📚 **Ваша библиотека голокронов:**\nСобрано уникальных: "
      f"{collected_unique} из {total_cards}\n\n"
  )
  cards_dict = {card["id"]: card for card in CARDS_DATABASE}

  for card_id, count in user_cards.items():
    if card_id in cards_dict:
      card_title = cards_dict[card_id]["caption"].split("\n")[0]
      text += f"✅ {card_title} (x{count})\n"

  await message.reply(text, parse_mode="Markdown")


async def main():
  await init_db()
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
