import discord
import os
import sqlite3
import datetime
import logging
import requests
import hashlib
from discord import app_commands
from dotenv import load_dotenv
from urllib.parse import urlparse

# 環境変数のロード
load_dotenv()

# データベース名
DATABASE_NAME = '/data/sound_effects.db'

# ログの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_db():
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sound_effects (
            guild_id INTEGER,
            name TEXT,
            file TEXT,
            PRIMARY KEY (guild_id, name)
        )
    ''')
    conn.commit()
    conn.close()

initialize_db()

def execute_db_query(query, params=(), commit=False):
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    c.execute(query, params)
    if commit:
        conn.commit()
    result = c.fetchall()
    conn.close()
    return result

def log_database_contents():
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    try:
        c.execute('SELECT * FROM sound_effects')
        rows = c.fetchall()
        if rows:
            for row in rows:
                logger.info(f"Database row: {row}")
        else:
            logger.info("No data found in the database.")
    except sqlite3.Error as e:
        logger.error(f"Error occurred while reading the database: {e}")
    finally:
        conn.close()

def download_sound_file(url, guild_id):
    response = requests.get(url)
    if response.status_code == 200:
        # URLからファイル名を安全に生成
        parsed_url = urlparse(url)
        file_name = hashlib.sha256(url.encode('utf-8')).hexdigest()
        extension = os.path.splitext(parsed_url.path)[-1]
        sound_file_name = f"{file_name}{extension}"
        save_path = f"/data/sounds/{guild_id}/{sound_file_name}"
        
        # ディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        return save_path
    else:
        raise Exception(f"Failed to download file from URL: {url}, Status Code: {response.status_code}")

class MyClient(discord.Client):
    def __init__(self, intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        for guild in self.guilds:
            try:
                await self.tree.sync(guild=guild)
                print(f'コマンドをサーバー `{guild.name}` に同期しました。')
            except Exception as e:
                print(f'サーバー `{guild.name}` へのコマンド同期に失敗しました: {e}')

        try:
            await self.tree.sync()
            print('グローバルコマンドを同期しました。')
        except Exception as e:
            print(f'グローバルコマンドの同期に失敗しました: {e}')

    async def on_ready(self):
        print('ログインしました')
        new_activity = discord.Game(name="テスト動作")
        await self.change_presence(activity=new_activity)
        
        # データベースの内容をログに出力
        log_database_contents()

        try:
            commands = await self.tree.fetch_commands()
            print('登録されているコマンド:')
            for command in commands:
                print(f' - {command.name}')
        except Exception as e:
            print(f'コマンドの取得に失敗しました: {e}')

    async def on_message(self, message):
        if message.author == self.user:
            return

        guild_id = message.guild.id
        sound_file = self.get_sound_file(guild_id, message.content)

        if sound_file:
            voice_client = message.guild.voice_client

            if voice_client is None:
                if message.author.voice:
                    channel = message.author.voice.channel
                    voice_client = await channel.connect()
                else:
                    await message.channel.send("ボイスチャンネルに接続してください。")
                    return

            try:
                voice_client.play(discord.FFmpegPCMAudio(sound_file))
            except Exception as e:
                await message.channel.send(f"効果音 `{message.content}` の再生に失敗しました: {str(e)}")

    def get_sound_file(self, guild_id, name):
        result = execute_db_query('SELECT file FROM sound_effects WHERE guild_id = ? AND name = ?', (guild_id, name))
        if result:
            return result[0][0]
        return None

# 必要なインテントの設定
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.voice_states = True

client = MyClient(intents=intents)

# helpコマンド
@client.tree.command(name='h', description="ヘルプを表示します。")
async def help_command(interaction: discord.Interaction):
    help_message = (
        "**ヘルプ**\n\n"
        "コマンド一覧 **/list**\n"
        "詳細については [こちら](https://disk22.wixsite.com/bengiken/about-5) をご覧ください。"
    )
    await interaction.response.send_message(help_message)

# listコマンド
@client.tree.command(name='list', description="コマンド一覧を表示します。")
async def help_command(interaction: discord.Interaction):
    help_message = (
        "**コマンド一覧**\n\n"
        "/list:コマンド一覧を表示します。\n/join:コマンド実行者のいるVCに参加します。\n/disc:VCから退出します。\n/event:簡易的なイベントを作成します。（Discord標準のイベント機能ではありません。）\n/q:アンケートを作成します。選択肢は2個以上20個未満です。\n/se_add:効果音を登録します。\n/se_del:登録された効果音を削除します。\n/se_list:登録された効果音の一覧を表示します。"
        "詳細については [こちら](https://disk22.wixsite.com/bengiken/about-5) をご覧ください。"
    )
    await interaction.response.send_message(help_message)

# イベント作成コマンド
@client.tree.command(name="event", description="イベントを作成します。")
async def create_event(
    interaction: discord.Interaction,
    name: str,
    date: str,
    time: str,
    description: str,
    mention_everyone: bool = False
):
    try:
        event_datetime_str = f"{date} {time}"
        event_date = datetime.datetime.strptime(event_datetime_str, "%Y/%m/%d %H:%M")
        embed = discord.Embed(
            title=name,
            description=f"概要: {description}\n日付: {event_date.strftime('%Y/%m/%d %H:%M')}",
            color=0xFFFF00
        )
        await interaction.response.send_message(embed=embed)

        if mention_everyone:
            await interaction.channel.send("@everyone")

    except ValueError:
        await interaction.response.send_message("日付または時刻に誤りがあります。「YYYY/MM/DD」と「HH:MM」フォーマットを使用してください。")

# アンケート作成コマンド
@client.tree.command(name="q", description="アンケートを作成します。選択肢は最大20個までです。")
async def create_poll(interaction: discord.Interaction, name: str, options: str):
    options_list = [option.strip() for option in options.split(",")]

    if len(options_list) < 2:
        await interaction.response.send_message("選択肢は2つ以上必要です！")
        return

    if len(options_list) > 20:
        await interaction.response.send_message("選択肢は最大20個までです！")
        return

    embed = discord.Embed(title=name, description="React to vote!", color=0x00ff00)
    emojis = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯", "🇰", "🇱", "🇲", "🇳", "🇴", "🇵", "🇶", "🇷", "🇸", "🇹"]

    for i, option in enumerate(options_list):
        embed.add_field(name=f"{emojis[i]} {option}", value="\u200b", inline=False)

    await interaction.response.send_message("アンケートを作成しています...", ephemeral=True)
    message = await interaction.followup.send(embed=embed, ephemeral=False)

    for i in range(len(options_list)):
        await message.add_reaction(emojis[i])

# VC参加コマンド
@client.tree.command(name="join", description="ボイスチャンネルに参加します")
async def join(interaction: discord.Interaction):
    if interaction.user.voice is not None:
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client is None:
            await channel.connect()
            await interaction.response.send_message(f"ボイスチャンネル `{channel.name}` に参加しました。")
        else:
            await interaction.response.send_message("ボットはすでにボイスチャンネルに参加しています。")
    else:
        await interaction.response.send_message("ボイスチャンネルに参加していません。")

# VC切断コマンド
@client.tree.command(name="disc", description="ボイスチャンネルからボットが切断します")
async def disc(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is not None:
        await voice_client.disconnect()
        await interaction.response.send_message("ボイスチャンネルから切断しました。")
    else:
        await interaction.response.send_message("ボットは現在、どのボイスチャンネルにも接続していません。")

# 効果音登録コマンド
@client.tree.command(name="se_add", description="効果音を登録します")
async def se_add(interaction: discord.Interaction, name: str, url: str):
    guild_id = interaction.guild.id
    try:
        file_path = download_sound_file(url, guild_id)
        execute_db_query('INSERT OR REPLACE INTO sound_effects (guild_id, name, file) VALUES (?, ?, ?)', (guild_id, name, file_path), commit=True)
        await interaction.response.send_message(f"効果音 `{name}` を登録しました。")
    except Exception as e:
        await interaction.response.send_message(f"効果音 `{name}` の登録に失敗しました: {str(e)}")

# 効果音削除コマンド
@client.tree.command(name="se_del", description="効果音を削除します")
async def se_del(interaction: discord.Interaction, name: str):
    guild_id = interaction.guild.id
    execute_db_query('DELETE FROM sound_effects WHERE guild_id = ? AND name = ?', (guild_id, name), commit=True)
    await interaction.response.send_message(f"効果音 `{name}` を削除しました。")

# 効果音一覧コマンド
@client.tree.command(name="se_list", description="登録されている効果音の一覧表示します")
async def se_view(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    sound_list = execute_db_query('SELECT name, file FROM sound_effects WHERE guild_id = ?', (guild_id,))
    if sound_list:
        sound_list_text = "\n".join([f"{name}: {url}" for name, url in sound_list])
        await interaction.response.send_message(f"登録されている効果音:\n{sound_list_text}")
    else:
        await interaction.response.send_message("登録されている効果音はありません。")

client.run(os.getenv('TOKEN'))
