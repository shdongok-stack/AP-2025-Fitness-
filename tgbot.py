# Импорт библиотек
import os
import asyncio
import requests

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram import F

# Настройка бота
bot = Bot(token=os.getenv("Bot_Token"))
dp = Dispatcher()
router = Router()

# Словарь для хранения данных
users = {}

# Переменная для хранения API-ключа OpenWeatherMap (берется из переменных окружения)
api_key_owm = os.getenv("OpenWeatherMap_API_Key")

def current_temperature_api(city: str):
    """
    Получает текущую температуру в градусах Цельсия для указанного города через OpenWeatherMap
    Код взят из предыдущего ДЗ
    """
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": api_key_owm,
        "units": "metric"
        }

    response = requests.get(url, params=params)
    data = response.json()
    temp = data["main"]["temp"]
    print(f"[OWM] Температура в '{city}' = {temp} C")

    if response.status_code != 200:
        return None

    return temp

# Команда старта бота
@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Стартовая команда
    Регистрирует пользователя + приветствует его
    """
    user_id = message.from_user.id # Получаем id пользователя

    if user_id not in users: # Если пользователя нет в словаре, то регистрируем его
        users[user_id] = {}
        print(f"[/start] Зарегистрирован новый пользователь {user_id}") # Логирование

    await message.answer("Привет! Я фитнес-бот 🏋.\n"
    "Используйте /set_profile для настройки профиля.")

# Команда настройки профиля
@router.message(Command("set_profile"))
async def cmd_set_profile(message: Message):
    """
    Команда настройки профиля пользователя
    Запускает небольшую анкету (уточняет у пользователя рост, вес, возраст, время активности и город)
    """
    user_id = message.from_user.id
    print(f"[/set_profile] user_id={user_id}")
    users[user_id] = {"step": "height"}  # Используем step для определения порядка заполнения анкеты
    await message.answer("Пожалуйста, введите ваш рост в сантимертрах:")

# Функция расчета нормы воды
def calc_water_goal(user: dict):
    """
    Расчет дневной нормы воды (30 мл воды на 1 кг веса +500 мл за каждые 30 минут активности)
    + учитывается температура воздуха в городе пользователя
    """
    water_goal = user["weight"] * 30
    water_goal += (user["activity"] // 30) * 500

    temp = current_temperature_api(user["city"]) # Получаем текущую температуру в городе, указанном пользователем

    if temp is not None:
        if temp >= 30:
            water_goal += 1000
        elif temp >= 25:
            water_goal += 500

    return int(water_goal)

# Функция расчета нормы ккал
def calc_calories_goal(user: dict):
    """
    Расчет дневной нормы калорий по формуле Миффлина-Сан Жеора (без учета пола + с учетом уровня активности)
    """
    calories_goal = 10 * user["weight"] + 6.25 * user["height"] - 5 * user["age"]

    if user["activity"] <= 30:
        calories_goal += 100
    elif user["activity"] <= 60:
        calories_goal += 200
    else:
        calories_goal += 300

    return int(calories_goal)

# Функция записи выпитой воды
@router.message(Command("log_water"))
async def cmd_log_water(message: Message):
    """
    Логирование потребленной воды
    """
    user_id = message.from_user.id

    # Проверяем настроил ли пользователь свой профиль
    if user_id not in users or "water_goal" not in users[user_id]:
        await message.answer("Пожалуйста, сначала заполните профиль. Используйте команду /set_profile")
        return

    try:
        amount = int(message.text.split()[1])
        print(f"[/log_water] user_id={user_id}, amount={amount}")
        users[user_id]["logged_water"] += amount
        remaining = users[user_id]["water_goal"] - users[user_id]["logged_water"]

        # Если пользователь еще не выполнил свою цель, то бот пришлет информацию о том, сколько пользователю еще необходимо выпить воды
        if remaining > 0:
            await message.answer(
                f"📝 Записано {amount} мл\n"
                f"🎯 Осталось выпить {remaining} мл")
        else:
            await message.answer("Норма воды выполнена 🎉")
    except (IndexError, ValueError):
        await message.answer("Пожалуйста, введите количество воды числом (мл). Пример: /log_water 300")

# Получение калорийности продукта через OpenFoodFacts API
def get_kcal(product_name: str):
    """
    Получение калорийности продукта через OpenFoodFacts API. Возвращает ккал на 100 грамм продукта или None, если продукт не найден
    """
    # Отправляем запрос к OpenFoodFacts API
    r = requests.get("https://world.openfoodfacts.org/cgi/search.pl",
        params={
            "search_terms": product_name,
            "json": 1
            })

    products = r.json().get("products", [])
    if not products:
        return None

    return products[0].get("nutriments", {}).get("energy-kcal_100g")

# Функция логирования еды
@router.message(Command("log_food"))
async def cmd_log_food(message: Message):
    """
    Логирование еды. Сначала определяется продукт, затем запрашивается количество грамм для подсчета калорий
    """
    user_id = message.from_user.id

    # Проверяем, заполнен ли профиль
    if user_id not in users or "calorie_goal" not in users[user_id]:
        await message.answer("Пожалуйста, сначала заполните профиль. Используйте команду /set_profile")
        return

    # Получаем название продукта из сообщения
    try:
        product_name = message.text.split(maxsplit=1)[1]
        print(f"[/log_food] user_id={user_id}, product='{product_name}'")
    except IndexError:
        await message.answer("Введите, пожалуйста, название продукта. Например: /log_food банан")
        return

    # Получаем калорийность продукта
    kcal_100g = get_kcal(product_name)
    if kcal_100g is None:
        await message.answer("Не удалось найти продукт")
        return

    # Сохраняем калорийность указанного продукта и запрашиваем количество потребленных грамм
    users[user_id]["last_food"] = kcal_100g
    users[user_id]["step"] = "food_weight"

    await message.answer(f"{product_name} — {kcal_100g} ккал на 100 г. Сколько грамм вы съели?")

# Функция логирования тренировок
@router.message(Command("log_workout"))
async def cmd_log_workout(message: Message):
    """
    Логирование тренировок. Пользователь вводит вид тренировки и продолжительность в минутах
    Учитывается расход калорий (соженные ккал) и доп. потребность в воде
    """
    user_id = message.from_user.id

    # Проверяем, заполнен ли профиль
    if user_id not in users or "burned_calories" not in users[user_id]:
        await message.answer("Пожалуйста, сначала заполните профиль. Используйте команду /set_profile")
        return
    
    # Получаем вид тренировки и продолжительность из сообщения
    try:
        cmd, exercise, minute = message.text.split()
        minutes = int(minute)
    except ValueError:
        await message.answer("Введите, пожалуйста, продолжительность тренировки в минутах. Например: /log_workout бег 30")
        return

    burned_kcal = minutes * 6.67 # Примерный расход калорий (6,67 ккал в минуту)
    users[user_id]["burned_calories"] += burned_kcal # Записываем сожженные калории
    extra_water = (minutes // 30) * 200 # Расчет доп. потребности в воде
    users[user_id]["water_goal"] += extra_water
    print(f"[/log_workout] user_id={user_id}, "
    f"exercise={exercise}, minutes={minutes}, burned_kcal={burned_kcal}")
    await message.answer(
        f"📝 Записана тренировка: {exercise} — {minutes} мин\n"
        f"🔥 Сожжено ~{burned_kcal} ккал\n"
        f"💧 Выпейте дополнительно {extra_water} мл воды")


# Функция проверки текущего прогресса
@router.message(Command("check_progress"))
async def cmd_check_progress(message: Message):
    """
    Отчет о текущем прогрессе по воде и калориям
    """
    
    user_id = message.from_user.id
    print(f"[/check_progress] user_id={user_id}")

    # Проверяем, заполнен ли профиль
    if user_id not in users or "water_goal" not in users[user_id]:
        await message.answer("Сначала заполните профиль")
        return

    await message.answer(
        "📊 Отчет о текущем прогрессе:\n\n"
        f"💧 Вода:\n"
        f"- Выпито: {users[user_id]['logged_water']} / {users[user_id]['water_goal']} мл\n"
        f"- Осталось {users[user_id]['water_goal'] - users[user_id]['logged_water']} мл\n\n"
        f"🔥 Калории:\n"
        f"- Употреблено: {int(users[user_id]['logged_calories'])}\n"
        f"- Сожжено: {int(users[user_id]['burned_calories'])}\n"
        f"- Цель: {users[user_id]['calorie_goal']}")

# Хендлер для обработки текстовых сообщений
@router.message(F.text & ~F.text.startswith("/")) # Отфильтровываем только текстовые сообщения (т.е не затрагиваются команды)
async def handler(message: Message):
    """
    Обработка обычных текстовых сообщений. Используется для пошагового заполнения профиля (в т.ч. логирования еды)
    """
    user_id = message.from_user.id 
    step = users.get(user_id, {}).get("step") # Получаем текущий шаг пользователя (необходим для пошагового заполнения анкеты)

    if user_id not in users:
        await message.answer("Пожалуйста, начите с команды /set_profile")
        return

    # Проходимся по каждому шагу анкеты и сохраняем введенные данные в словарь
    if step == "height":
        try: 
            users[user_id]["height"] = int(message.text)
            users[user_id]["step"] = "weight"
            await message.answer("Пожалуйста, введите ваш вес в килограммах:")
        except ValueError:
            await message.answer("Пожалуйста, введите рост числом. Пример: 175")
    
    elif step == "weight":
        try:
            users[user_id]["weight"] = float(message.text)
            users[user_id]["step"] = "age"
            await message.answer("Введите возраст:")
        except ValueError:
            await message.answer("Пожалуйста, введите вес числом. Пример: 73.5 или 73")

    elif step == "age":
        try:
            users[user_id]["age"] = int(message.text)
            users[user_id]["step"] = "activity"
            await message.answer("Пожалуйста, введите ваш уровень активности в минутах:\n" 
            "(например, 30 для низкой активности, 60 для средней, 90 для высокой)")
        except ValueError:
            await message.answer("Пожалуйста, введите возраст числом. Пример: 22")

    elif step == "activity":
        try:
            users[user_id]["activity"] = int(message.text)
            users[user_id]["step"] = "city"
            await message.answer("Пожалуйста, введите ваш город:\n"
            "(например, Moscow, Beijing и т.д.)")
        except ValueError:
            await message.answer("Пожалуйста, введите активность числом. Пример: 30")

    elif step == "city":
        users[user_id]["city"] = message.text
        users[user_id]["step"] = None

        users[user_id]["water_goal"] = calc_water_goal(users[user_id])
        users[user_id]["calorie_goal"] = calc_calories_goal(users[user_id])

        users[user_id]["logged_water"] = 0
        users[user_id]["logged_calories"] = 0
        users[user_id]["burned_calories"] = 0

        await message.answer(
            "Профиль сохранен ✅\n"
            f"💧 Цель по воде: {users[user_id]['water_goal']} мл\n"
            f"🔥 Цель по калориям: {users[user_id]['calorie_goal']} ккал")

    elif step == "food_weight":
        try: 
            grams = float(message.text)
            kcal = users[user_id]["last_food"] * grams / 100
            users[user_id]["logged_calories"] += kcal
            users[user_id]["step"] = None
            await message.answer(f"📝 Записано {int(kcal)} ккал")
        except ValueError:
            await message.answer("Пожалуйста, введите количество грамм числом. Пример: 150 или 150.5")

# Функция запуска бота
async def main():
    """
    Функция запуска бота
    """
    dp.include_router(router)
    print("Бот успешно запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
