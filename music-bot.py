import discord
from discord.ext import commands
import yt_dlp
from youtubesearchpython import VideosSearch
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from async_timeout import timeout
import asyncio

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Spotify credentials
SPOTIFY_CLIENT_ID = 'your_spotify_client_id'
SPOTIFY_CLIENT_SECRET = 'your_spotify_client_secret'

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID,
                                                           client_secret=SPOTIFY_CLIENT_SECRET))

queues = {}


class MusicPlayer:
    def __init__(self, ctx):
        self.bot = bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.current = None
        self.np = None
        self.volume = 0.5
        self.loop = False
        self.voice_client = ctx.voice_client

        bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            if not self.loop:
                try:
                    async with timeout(300):  # wait 5 minutes for the next song
                        self.current = await self.queue.get()
                except asyncio.TimeoutError:
                    await self.voice_client.disconnect()
                    return

            self.voice_client.play(discord.FFmpegPCMAudio(self.current['url'],
                                                          before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"),
                                   after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))

            self.np = await self._channel.send(f"Now playing: **{self.current['title']}**")
            await self.next.wait()

            # Clear the now playing message
            await self.np.delete()
            self.current = None

    def add_to_queue(self, source):
        self.queue.put_nowait(source)

    def toggle_loop(self):
        self.loop = not self.loop

    def stop(self):
        self.queue = asyncio.Queue()
        if self.voice_client.is_playing():
            self.voice_client.stop()


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def get_player(self, ctx):
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player
        return player

    @commands.command(name="play", help="Plays a song from YouTube or Spotify")
    async def play(self, ctx, *, query):
        voice_channel = ctx.author.voice.channel

        if not voice_channel:
            return await ctx.send("You need to be in a voice channel to play music!")

        voice_client = ctx.voice_client

        if not voice_client:
            voice_client = await voice_channel.connect()

        player = self.get_player(ctx)

        if "youtube.com" in query or "youtu.be" in query:
            source = await self.search_youtube(query)
        elif "spotify.com" in query:
            source = await self.search_spotify(query)
        else:
            source = await self.search_youtube(query)

        player.add_to_queue(source)

        await ctx.send(f"Added **{source['title']}** to the queue.")

    async def search_youtube(self, query):
        search = VideosSearch(query, limit=1)
        results = search.result()['result']
        video_info = results[0]

        ydl_opts = {'format': 'bestaudio', 'noplaylist': 'True'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com{video_info['link']}", download=False)
            return {'url': info['formats'][0]['url'], 'title': video_info['title']}

    async def search_spotify(self, query):
        track_id = query.split("/")[-1].split("?")[0]
        track_info = sp.track(track_id)
        track_name = track_info['name']
        artist_name = track_info['artists'][0]['name']
        search_query = f"{track_name} {artist_name}"
        return await self.search_youtube(search_query)

    @commands.command(name="pause", help="Pauses the currently playing song")
    async def pause(self, ctx):
        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Paused the music.")

    @commands.command(name="resume", help="Resumes the currently paused song")
    async def resume(self, ctx):
        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Resumed the music.")

    @commands.command(name="skip", help="Skips the currently playing song")
    async def skip(self, ctx):
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Skipped the song.")

    @commands.command(name="stop", help="Stops the music and clears the queue")
    async def stop(self, ctx):
        player = self.get_player(ctx)
        player.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("Stopped the music and cleared the queue.")

    @commands.command(name="volume", help="Adjusts the playback volume")
    async def volume(self, ctx, volume: int):
        if 0 <= volume <= 100:
            ctx.voice_client.source.volume = volume / 100
            await ctx.send(f"Volume set to {volume}%")
        else:
            await ctx.send("Volume must be between 0 and 100.")

    @commands.command(name="now", help="Shows the current song")
    async def now(self, ctx):
        player = self.get_player(ctx)
        if player.current:
            await ctx.send(f"Now playing: **{player.current['title']}**")
        else:
            await ctx.send("No song is currently playing.")

    @commands.command(name="loop", help="Loops the current song")
    async def loop(self, ctx):
        player = self.get_player(ctx)
        player.toggle_loop()
        await ctx.send(f"Looping is now {'enabled' if player.loop else 'disabled'}")

    @commands.command(name="clear", help="Clears the queue")
    async def clear(self, ctx):
        player = self.get_player(ctx)
        player.stop()
        await ctx.send("Queue cleared.")


bot.add_cog(Music(bot))
bot.run("your_discord_token")
