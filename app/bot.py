import logging
import os
import datetime
import random
import yfinance as yf
import plotly.express as px
# from dotenv import load_dotenv
import discord
import matplotlib
matplotlib.use('Agg')  # Set the backend before importing pyplot
import matplotlib.pyplot as plt

import aiocron
from dotenv import load_dotenv

import sub_bot

# 1
from discord.ext import commands

from slack import slack_blueprint
from db import Symbol, setup_database, symbols_schema, db
from flask import Flask

# top_stock_companies = ['AAPL', 'GOOGL', 'TSLA', 'MSFT', 'AMZN', 'FB', 'BRK-B', 'SPY',
#                        'BABA', 'JPM', 'WMT', 'V', 'T', 'UNH', 'PFE', 'INTC', 'VZ', 'ORCL']

top_stock_companies = []

# # Create a Flask application
app = Flask(__name__)

df = None
df_not_none = False
count = 0
random_company = ''
nrows = 0

if not os.path.exists("images"):
    os.mkdir("images")

# # Load environment variables from the .env file
load_dotenv()
TOKEN = os.environ.get('DISCORD_TOKEN')

# 2

intents = discord.Intents.default()
#intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def start_bot(event):

    global app
    global top_stock_companies
    # Signal that shared data is ready
    event.set()
    app = event.data
    with app.app_context():
        symbol_list = Symbol.query.all()
    top_stock_companies = symbols_schema.dump(symbol_list)
    top_stock_companies = [item['symbol'] for item in top_stock_companies]
    bot.run(TOKEN)

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')


@bot.command(name="get-list", help="Check list of companies for which stock details can be fetched.")
async def get_list(ctx):
    await ctx.send(top_stock_companies)




@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send('You do not have the correct role for this command.')
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.send('Please enter correct usage.')


def create_msg(top_stock_company, top_stock_company_df):
    date = str(top_stock_company_df.head(1).index[0]).split(' ')[0]
    msg = '''\
        {company} EOF Data
        - Date: {Date}
        - Open: {Open}
        - High: {High}
        - Low: {Low}
        - Close: {Close}
        - Adj Close: {Adj_Close}
        - Volume: {Volume}\
     '''.format(company=top_stock_company, Date=date, Open=top_stock_company_df.iat[0, 0], High=top_stock_company_df.iat[0, 1], Low=top_stock_company_df.iat[0, 2], Close=top_stock_company_df.iat[0, 3], Adj_Close=top_stock_company_df.iat[0, 4], Volume=top_stock_company_df.iat[0, 5])

    return msg


@aiocron.crontab('0 7 * * mon-fri')
async def send_stock_details():

    top_stock_company = random.choice(top_stock_companies)
    top_stock_company_df = yf.download(top_stock_company, period="1d")

    msg = create_msg(top_stock_company, top_stock_company_df)

    existing_channel = discord.utils.get(
        bot.guilds[0].channels, name='stock-details')

    if not existing_channel:
        print(f'Creating a new channel- stock-details...')
        await bot.guilds[0].create_text_channel("stock-details")
        print('Channel created!')
        existing_channel = discord.utils.get(
            bot.guilds[0].channels, name='stock-details')

    await existing_channel.send(msg)
    await sub_bot.send_daily_trade_updates_plot(top_stock_company, existing_channel)


@aiocron.crontab('30 10-16 * * mon-fri')
async def show_hourly_plot():
    global df_not_none, count, df, random_company, nrows

    now = datetime.datetime.now()
    if now.hour == 10:
        df_not_none = True
        random_company = random.choice(top_stock_companies)
        df = yf.download(random_company,
                         period="1d", interval="1m")
        nrows = len(df.index)

    elif not df_not_none:
        df_not_none = True

        if count == 0:
            if now.hour == 11:
                count = 1
            elif now.hour == 12:
                count = 2
            elif now.hour == 13:
                count = 3
            elif now.hour == 14:
                count = 4
            elif now.hour == 15:
                count = 5
            else:
                count = 6

        random_company = random.choice(top_stock_companies)
        df = yf.download(random_company,
                         period="1d", interval="1m")
        nrows = len(df.index)

    limiter = 6.5 if (count == 6) else (count + 1)
    slice_limiter = 60*limiter

    if count == 6 and nrows != 390:
        slice_limiter = nrows

    df[60*count: slice_limiter].plot(y='Close', linewidth=0.85)

    plt.xlabel('Datetime')
    plt.ylabel('Close')
    plt.title('Stock prices of {company} for {hour1}:30 - {hour2}:30'.format(
        company=random_company, hour1=now.hour-1, hour2=now.hour))

    plt.savefig('images/stock_{i}.png'.format(i=count))

    existing_channel = discord.utils.get(
        bot.guilds[0].channels, name='stock-details')

    if not existing_channel:
        print(f'Creating a new channel- stock-details...')
        await bot.guilds[0].create_text_channel("stock-details")
        print('Channel created!')
        existing_channel = discord.utils.get(
            bot.guilds[0].channels, name='stock-details')

    await existing_channel.send(file=discord.File('images/stock_{i}.png'.format(i=count)))

    os.remove('images/stock_{i}.png'.format(i=count))

    count = count + 1

    if now.hour == 16:
        df_not_none = False
        count = 0
