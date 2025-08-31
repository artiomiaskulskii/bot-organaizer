import telebot
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from config import TOKEN

bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect("reminders.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    datetime TEXT,
    text TEXT,
    sent INTEGER DEFAULT 0
)
""")
conn.commit()

user_temp = {}

@bot.message_handler(commands=["start"])
def start(message):
    text = (
        "Привет! Добро пожаловать в наш бот 👋\n"
        "Чтобы добавить напоминание, введите команду /remind\n"
        "Чтобы увидеть инструкцию, введите команду /help\n"
        "Чтобы увидеть информацию о боте, введите команду /info"
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=["remind"])
def ask_datetime(message):
    bot.reply_to(
        message, text= "Когда напомнить? Пиши: HH:MM (если сегодня) или DD.MM HH:MM (если другой день)\n"
        "Примеры: 18:45, 25.08 09:30"
    )
    bot.register_next_step_handler(message, get_datetime)

@bot.message_handler(commands=["help"])
def help_command(message):
    bot.send_message(message.chat.id, text= 'Привет! Держи инструкцию к боту! 😊\n'
                                     'Чтобы добавить напоминание, введите команду /remind (пример: /remind 18:45)\n'
                                     'Чтобы увидеть список напоминаний, введите команду /myreminders\n'
                                     'Чтобы удалить напоминание, введите команду /delreminder (пример: /delreminder 1)\n'
                                     'Чтобы удалить все напоминания, введите команду /clearreminders\n'
    )
    
@bot.message_handler(commands=["info"])
def info_command(message):
    bot.send_message(message.chat.id,text= 'Привет! Это бот напоминаний. Он будет напоминать тебе что-то в указанное время 😊\n'
                                    'Ихучить команды можно тут: /help\n'
    )

def get_datetime(message):
    user_id = message.from_user.id
    text = message.text.strip()
    remind_dt = None
    now = datetime.now()

    try:
        if len(text) == 5 and ":" in text:
            remind_time = datetime.strptime(text, "%H:%M").time()
            remind_dt = datetime.combine(now.date(), remind_time)
            if remind_dt < now:
                remind_dt += timedelta(days=1)
        else:
            remind_dt = datetime.strptime(text, "%d.%m %H:%M")
            remind_dt = remind_dt.replace(year=now.year)

        remind_dt = remind_dt.replace(second=0, microsecond=0)

    except ValueError:
        bot.reply_to(message, "Не понял... Напиши в формате HH:MM или DD.MM HH:MM, или заново /remind 😶‍🌫️")
        return

    user_temp[user_id] = {"datetime": remind_dt}
    bot.reply_to(message, "Хорошо, напиши о чём напомнить 👍")
    bot.register_next_step_handler(message, save_reminder)


def save_reminder(message):
    user_id = message.from_user.id
    if user_id not in user_temp:
        bot.reply_to(message, "Чёт сломалось( Напиши /remind и попробуй снова 🤨")
        return

    remind_dt = user_temp[user_id]["datetime"]
    reminder_text = message.text.strip()

    cursor.execute(
        "INSERT INTO reminders (user_id, datetime, text) VALUES (?, ?, ?)",
        (user_id, remind_dt.strftime("%Y-%m-%d %H:%M"), reminder_text)
    )
    conn.commit()

    bot.reply_to(message, f"Окей, запомнил\n"
                          f"Напомнить в {remind_dt.strftime('%d.%m %H:%M')}: {reminder_text}")
    del user_temp[user_id]


@bot.message_handler(commands=["myreminders"])
def my_reminders(message):
    user_id = message.from_user.id
    cursor.execute("SELECT id, datetime, text, sent FROM reminders WHERE user_id=? ORDER BY datetime", (user_id,))
    rows = cursor.fetchall()

    if not rows:
        bot.reply_to(message, "Пока ничего... напоминаний нет 😒")
        return

    response = "Твои напоминания:\n\n"
    for r in rows:
        reminder_id, dt_str, text_rem, sent = r
        status = "Готово" if sent else "Ждёт"
        dt_human = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").strftime("%d.%m %H:%M")
        response += f"{reminder_id}. [{dt_human}] {text_rem} - {status}\n"

    response += "\nХочешь удалить напоминание - /delreminder [id] Все напоминания - /clearreminders 😣"
    bot.reply_to(message, response)


@bot.message_handler(commands=["delreminder"])
def delete_reminder(message):
    parts = message.text.split(" ", 1)
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "Введи ID цифрой Пример: /delreminder 1 😊")
        return

    reminder_id = int(parts[1])
    user_id = message.from_user.id

    cursor.execute("SELECT id FROM reminders WHERE id=? AND user_id=?", (reminder_id, user_id))
    row = cursor.fetchone()

    if row:
        cursor.execute("DELETE FROM reminders WHERE id=? AND user_id=?", (reminder_id, user_id))
        conn.commit()
        bot.reply_to(message, f"Окей, удалил напоминание {reminder_id} 🥲")
    else:
        bot.reply_to(message, "Не нашёл такое напоминание 😕")


@bot.message_handler(commands=["clearreminders"])
def clear_reminders(message):
    user_id = message.from_user.id
    cursor.execute("DELETE FROM reminders WHERE user_id=?", (user_id,))
    conn.commit()
    bot.reply_to(message, "Отлично, всё удалил 😌")


def check_reminders():
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            cursor.execute("SELECT id, user_id, text, datetime FROM reminders WHERE datetime<=? AND sent=0", (now,))
            rows = cursor.fetchall()

            for r in rows:
                reminder_id, user_id, text_rem, dt_str = r
                try:
                    bot.send_message(user_id, f"Напоминаю: {text_rem} - {dt_str}")
                    cursor.execute("UPDATE reminders SET sent=1 WHERE id=?", (reminder_id,))
                    conn.commit()
                except Exception as e:
                    print("Ошибка при отправке:", e)

        except Exception as e:
            print("Ошибка при проверке БД:", e)

        time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=check_reminders, daemon=True).start()
    print("Бот функционирует 😊")
    bot.polling(none_stop=True)
