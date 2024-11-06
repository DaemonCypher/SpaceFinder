from config import TOKEN
from web1 import bot

try:
    bot.run(TOKEN)
except Exception as e:
    print(f"An error occurred: {e}")