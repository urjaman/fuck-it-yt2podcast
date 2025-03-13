#!/usr/bin/env python3
# This script makes a podcast RSS feed from a youtube channel
# Requirements:
# pacman -S yt-dlp ffmpeg python-parse
import yt_dlp
import sys
import os
import time
import datetime
import json
from parse import *
import subprocess
from email import utils

# Change things in this segment (cast_url is the address the webserver is visible at + folder where you put the podcast)
channel = 'https://www.youtube.com/CHANNEL/videos'
title = 'TITLE'
cast_url = "https://example.org/poddir"
cast_lang = "en-us"

# You can also add any extra stuff (categories, podcast description, etc) you want in the feed here
def feed_header():
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
xmlns:podcast="https://podcastindex.org/namespace/1.0"
xmlns:atom="http://www.w3.org/2005/Atom"
xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<atom:link href="{cast_url}/cast.rss" rel="self" type="application/rss+xml" />
<title>{xmlsafe(title)}</title>
<link>{xmlsafe(channel)}</link>
<language>{cast_lang}</language>
<itunes:explicit>false</itunes:explicit>
<itunes:image href="{cast_url}/podthumb.jpg" />
"""

debug = 0

def ytdl(url):
    dla = "dl-list.txt"
    opts = {}
    outtmpl = {
        'default': '%(release_date>%Y-%m-%d,upload_date>%Y-%m-%d)s %(title)s [%(id)s].%(ext)s',
        'pl_thumbnail': 'podthumb.%(ext)s',
        'pl_infojson': ''
    }
    opts['outtmpl'] = outtmpl
    opts['format'] = 'bestaudio/best'
    opts['extractaudio'] = True
    opts['audioformat'] = 'mp3'
    opts['writeinfojson'] = True
    opts['writethumbnail'] = True
    opts['match_filter'] = yt_dlp.utils.match_filter_func("!is_live")
    opts['ignoreerrors'] = True
    opts['download_archive'] = dla
    opts['audioquality'] = '5'
    opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': opts['audioformat'],
            'preferredquality': opts['audioquality'],
            'nopostoverwrites': False,
        }]

    # If we have downloaded something before, only read the first page of the playlist for updates
    if os.path.exists(dla):
        opts['playliststart'] = 1
        opts['playlistend'] = 15

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

def xmlsafe(s):
    escapes = {
        '&': '&amp;',
        '>': '&gt;',
        '<': '&lt;'
    }
    for k in escapes:
        s = s.replace(k, escapes[k])
    return s

def urlsafe(s):
    out = ""
    sb = s.encode('utf-8')
    for c in sb:
        if (c < 127) and (c > 32):
            okchr = "-_.()"
            cs = chr(c)
            if cs.isalnum() or cs in okchr:
                out += cs
                continue
        out += '%' + c.to_bytes(1).hex().upper()
    return out

def tag(tag, content, param="", lv=1):
    l = ' ' * lv
    l += '<' + tag
    if param:
        l += ' ' + param
    l += '>'
    l += content
    l += '</' + tag + '>\n'
    return l

def makefeed():
    items = []
    with os.scandir('.') as entries:
        for entry in entries:
            if debug:
                print(entry.name)
            if not entry.name.endswith('.mp3'):
                continue
            (entry_name, ext) = os.path.splitext(entry.name)

            infofn = entry_name + '.info.json'
            if not os.path.exists(infofn):
                print(f"Missing {infofn}")
                continue

            d = parse("{} {} [{}]", entry_name)
            if d is None:
                print(f"Cant parse name {entry_name}")
                continue

            (datestr, fn_title, id) = d

            metadata = None
            for line in open(infofn, 'r'):
                d = json.loads(line)
                if d['id'] == id:
                    metadata = d
                    break
            if metadata is None:
                mf = open(infofn, "r")
                metadata = json.load(mf)
                mf.close()

            webp_thumb = entry_name + '.webp'
            jpg_thumb = entry_name + '.jpg'
            if os.path.exists(webp_thumb):
                rv = subprocess.run(["ffmpeg", '-y', "-i", webp_thumb, '-update', '1', jpg_thumb ])
                if rv.returncode:
                    print("ffmpeg error", rv)
                    continue
                if not os.path.exists(jpg_thumb):
                    print("thumbnail conversion failed?")
                    continue
                os.unlink(webp_thumb)

            item = {}
            item['fn'] = entry.name
            item['id'] = id
            item['thumb'] = jpg_thumb if os.path.exists(jpg_thumb) else None
            # Use the title from metadata so we avoid filename limitations (:/?= and so on..)
            item['title'] = metadata['title']
            item['sort'] = entry_name
            item['date'] = datestr
            item['desc'] = metadata['description']
            item['size'] = entry.stat().st_size
            item['dur'] = str(metadata['duration'])

            items.append(item)
            if debug:
                print("Item processed")
                print(item)

    items.sort(reverse=True, key=lambda e: e['sort'])
    print("Making feed:")
    feed = [feed_header()]
    for i in items:
        print(i['fn'])
        feed.append('<item>\n')
        feed.append( tag("title", xmlsafe(i['title']) ) )
        dt = datetime.datetime.strptime(i['date'],"%Y-%m-%d")
        ds = time.strftime("%a, %-d %b %Y", dt.timetuple()) + " 00:00:00 +0000"
        feed.append( tag("pubDate", ds ) )
        feed.append( tag("guid", i['id'], 'isPermaLink="false"') )
        feed.append( tag("link", "https://www.youtube.com/watch?v=" + i['id'] ) )
        feed.append( tag("description", xmlsafe(i['desc']) ) )
        enc = ' <enclosure length="' + str(i['size']) + '" type="audio/mpeg" url="'
        enc += cast_url + '/' + urlsafe(i['fn'])
        enc += '" />\n'
        feed.append(enc)
        if i['thumb'] is not None:
            img = ' <itunes:image href="'
            img += cast_url + '/' + urlsafe(i['thumb'])
            img += '" />\n'
            feed.append(img)
        feed.append( tag("itunes:duration", i['dur']) )
        feed.append('</item>\n')

    feed.append("</channel></rss>\n")
    with open("cast.rss.new", "w") as f:
        f.write(''.join(feed))
    os.rename("cast.rss.new", "cast.rss")

ytdl(channel)
makefeed()
print("Done.")
