import os
import asyncio
import random

from discord import Embed

from musicbot import exceptions
from musicbot.constants import DISCORD_MSG_CHAR_LIMIT
from musicbot.constructs import Response


class CollabPlaylists:

    track_weights = {}
    weight_increment = 0.1
    start_weight = weight_increment * 10

    @staticmethod
    def get_playlist_file(music_bot, playlist_name):
        if playlist_name not in music_bot.config.collab_playlist_lists:
            return Response(playlist_name + " not a valid playlist. Use !ListTunes to get a list.", delete_after=20)

        playlist_url = os.path.join(music_bot.config.collab_playlist_url, playlist_name + ".txt")

        # Access locally.
        if not os.path.exists(playlist_url):
            os.makedirs(os.path.dirname(playlist_url), exist_ok=True)
            open(playlist_url, 'w').close()

        return playlist_url

    @staticmethod
    async def add_track(music_bot, playlist_name, song_url):
        playlist_url = CollabPlaylists.get_playlist_file(music_bot, playlist_name)
        if type(playlist_url) is Response:
            return playlist_url

        # Attempt atomic file operation using a temporary file and renaming that to the target file.
        temp_file_name = playlist_url + ".tmp"
        if os.path.exists(playlist_url):
            # Skip if song is already in playlist.
            with open(playlist_url, 'r') as playlist_file:
                for line in playlist_file.readlines():
                    if song_url in line:
                        return Response("Song already in playlist.", delete_after=20)
            # Create temp copy.
            os.rename(playlist_url, temp_file_name)

        # Get song title
        song_entry = song_url
        try:
            info = await music_bot.downloader.extract_info(music_bot.loop, song_url, download=False)
            song_entry += "," + info.get('title', 'Untitled')
        except Exception as e:
            raise exceptions.ExtractionError('Could not extract information from {}\n\n{}'.format(song_url, e))

        temp_file = open(temp_file_name, 'a+')
        temp_file.write(song_entry+"\n")
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        # Rename
        os.rename(temp_file_name, playlist_url)

        # Add to track weights.
        if playlist_name in CollabPlaylists.track_weights:
            CollabPlaylists.track_weights[playlist_name].append(CollabPlaylists.start_weight)

        return Response("Added song to collaborative playlist!", delete_after=10)

    @staticmethod
    def remove_track(music_bot, playlist_name, track_index):
        playlist_url = CollabPlaylists.get_playlist_file(music_bot, playlist_name)
        if type(playlist_url) is Response:
            return playlist_url

        playlist_file = open(playlist_url, 'r')
        songs = playlist_file.readlines()
        playlist_file.close()

        if len(songs) <= track_index:
            return Response("Invalid track number.")

        # Get the song title for the response.
        song_title = songs[track_index].split(",")[1].replace("\n", "")
        # Remove the specified index.
        del songs[track_index]
        # Write changes.
        with open(playlist_url, 'w') as playlist_file:
            playlist_file.writelines(songs)

        # Remove from track weightings.
        if playlist_name in CollabPlaylists.track_weights:
            del CollabPlaylists.track_weights[playlist_name][track_index]

        return Response("Removed **{0}** from the playlist.".format(song_title), delete_after=30)

    @staticmethod
    def list_playlists(music_bot):
        reply_text = ""
        for index, playlist in enumerate(music_bot.config.collab_playlist_lists):
            reply_text += "- {0}\n".format(playlist)

        return Response(reply_text, delete_after=60)

    @staticmethod
    async def list_playlist(music_bot, channel, playlist_name):
        playlist_url = CollabPlaylists.get_playlist_file(music_bot, playlist_name)
        if type(playlist_url) is Response:
            return playlist_url

        playlist_file = open(playlist_url, 'r')
        songs = playlist_file.readlines()
        playlist_file.close()
        songs = list(filter(None, songs))
        # Process songs
        reply_text = ""
        file_updated = False  # Whether the file needs updating to add missing song titles.
        for index, song in enumerate(songs):
            song = song.replace("\n", "")
            # Add song name if it hasn't been already.
            if "," not in song:
                try:
                    info = await music_bot.downloader.extract_info(music_bot.loop, song, download=False)
                except Exception as e:
                    raise exceptions.ExtractionError('Could not extract information from {}\n\n{}'.format(song, e))
                songs[index] = song + "," + info.get('title', 'Untitled')
                file_updated = True
            song_url, song_title = songs[index].split(",", 1)
            song_text = "**{0}**. {1}\n".format(index+1, song_title)
            if len(reply_text) + len(song_text) >= DISCORD_MSG_CHAR_LIMIT:
                content = music_bot._gen_embed()
                content.title = playlist_name
                content.description = reply_text
                await music_bot.safe_send_message(channel, content, expire_in=120)
                reply_text = ""
            reply_text += song_text

        # Add missing song names to playlist file.
        if file_updated:
            with open(playlist_url, 'w') as playlist_file:
                playlist_file.writelines(songs + "\n")

        content = music_bot._gen_embed()
        content.title = playlist_name
        content.description = reply_text
        return Response(content, delete_after=120)

    @staticmethod
    def get_track(music_bot, playlist_name):
        playlist_url = CollabPlaylists.get_playlist_file(music_bot, playlist_name)
        if type(playlist_url) is Response:
            return None

        playlist_file = open(playlist_url, 'r')
        songs = playlist_file.readlines()
        playlist_file.close()
        songs = list(filter(None, songs))

        if len(songs) == 0:
            return Response(playlist_name + " is empty! Add a song with !AddTune [playlistname] [song_url].", delete_after=20)

        # Init starting weights for each track index.
        if playlist_name not in CollabPlaylists.track_weights:
            CollabPlaylists.track_weights[playlist_name] = [CollabPlaylists.start_weight for i in range(len(songs))]

        selected_song = random.choices(songs, CollabPlaylists.track_weights[playlist_name])[0]
        selected_index = songs.index(selected_song)
        # Increment each track's weighting.
        for i in range(len(songs)):
            CollabPlaylists.track_weights[playlist_name][i] += CollabPlaylists.weight_increment
        # Push the chosen track way down.
        CollabPlaylists.track_weights[selected_index] = -(CollabPlaylists.weight_increment * (len(songs) * 0.2))

        return selected_song.strip("\n")