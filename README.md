# WMplayer

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## WMplayer

WMplayer is a local desktop music player written in Python and PyQt6. It focuses on a black-and-white, classic portable music player style, with a left-side playback panel and a right-side library, artist, album, queue, lyrics, and playlist workspace.

It uses libVLC for playback and supports common lossless and lossy audio formats, including MP3, FLAC, WAV, ALAC, APE, OGG, Opus, and DSD.

## Features

- Local music library scanning with metadata cache
- Album, artist, song, playlist, play queue, and lyrics views
- Search results grouped by artist, album, and song
- M3U/M3U8 playlist loading and saving
- Sequential play, shuffle play, repeat-all, and repeat-one modes
- Album playback limited to the selected album
- Artist shuffle playback from the artist detail page
- Cover thumbnails for fast scrolling
- Async cover preloading to reduce cover flicker during track changes
- LRC lyric parsing, synced lyric scrolling, and click-to-seek
- English and Simplified Chinese UI, with English as the default

## Requirements

| Dependency | Version |
|---|---|
| Python | >= 3.10 |
| PyQt6 | >= 6.5 |
| python-vlc | >= 3.0.20 |
| mutagen | >= 1.47 |
| Pillow | >= 10.0 |
| VLC media player | Required by libVLC |

## Usage

```bash
python WMplayer.py
```

1. Install VLC on your system.
2. Install Python dependencies with `pip install -r requirements.txt`.
3. Start WMplayer.
4. Open **Settings -> Library** and add your music folders.
5. Scan the library.
6. Use the right-side tabs to browse songs, artists, albums, the play queue, lyrics, and playlists.

The app also scans the built-in `library/` folder if it exists.

## Playlists

WMplayer reads and writes M3U/M3U8 playlists. Playlist files are stored in the `playlists/` folder by default, and additional playlist folders or files can be added in Settings.

```m3u
#EXTM3U
D:\Music\Album\Song 01.flac
D:\Music\Album\Song 02.mp3
```

Lines beginning with `#` are treated as comments when reading playlists.

## Lyrics

Put a `.lrc` file with the same base name next to the audio file:

```text
Song.flac
Song.lrc
```

Synced LRC files scroll automatically. Plain text lyric files can still be displayed, but they do not sync to playback.

## Project Structure

```text
.
|-- WMplayer.py              # Application entry point
|-- requirements.txt         # Python dependencies
|-- library/                 # Optional built-in music folder
|-- playlists/               # Default playlist folder
|-- core/
|   |-- audio_engine.py      # libVLC playback engine
|   |-- config.py            # Settings and app paths
|   |-- library.py           # Library scanning and metadata cache
|   |-- lrc.py               # LRC parser
|   |-- m3u.py               # M3U/M3U8 reader and writer
|   |-- metadata.py          # Audio metadata and cover reading
|   |-- playlist.py          # Play queue and playback modes
|   `-- playlist_store.py    # Playlist storage
`-- ui/
    |-- main_window.py       # Main window wiring
    |-- player_panel.py      # Left playback panel
    |-- library_panel.py     # Library view
    |-- artists_panel.py     # Artist view
    |-- albums_panel.py      # Album view
    |-- queue_panel.py       # Play queue view
    |-- lyrics_panel.py      # Lyrics view
    |-- playlists_panel.py   # Playlist view
    |-- settings_dialog.py   # Settings dialog
    |-- i18n.py              # UI translations
    |-- widgets.py           # Custom controls
    `-- theme.py             # Theme styles
```

## Build

```bash
pyinstaller --noconfirm --onefile --windowed --name WMplayer WMplayer.py
```

## Brand Note

WMplayer is an independent open-source project. It does not use third-party logos, product names, or official branding.

## License

No license file has been added yet. Add a license before publishing the repository as open source.

---

<a name="中文"></a>
## WMplayer

WMplayer 是一个用 Python 和 PyQt6 写的本地桌面音乐播放器。它采用黑底、白线、复古随身听式的视觉风格，左侧是播放控制区，右侧是曲库、歌手、专辑、播放队列、歌词和歌单工作区。

播放器基于 libVLC，支持 MP3、FLAC、WAV、ALAC、APE、OGG、Opus、DSD 等常见有损和无损音频格式。

## 功能

- 本地曲库扫描和元数据缓存
- 曲库、歌手、专辑、歌曲、歌单、播放队列和歌词视图
- 搜索结果按歌手、专辑、歌曲分组显示
- 支持读取和保存 M3U/M3U8 歌单
- 支持顺序播放、随机播放、列表循环和单曲循环
- 从专辑页播放时，队列会限制在当前专辑内
- 歌手详情页支持随机播放该歌手全部歌曲
- 使用封面缩略图提升长列表滚动性能
- 提前读取封面，减少切歌时的封面闪烁
- 支持 LRC 歌词解析、同步滚动和点击跳转
- 支持英文和简体中文界面，默认使用英文

## 运行要求

| 依赖 | 版本 |
|---|---|
| Python | >= 3.10 |
| PyQt6 | >= 6.5 |
| python-vlc | >= 3.0.20 |
| mutagen | >= 1.47 |
| Pillow | >= 10.0 |
| VLC media player | libVLC 需要 |

## 使用方法

```bash
python WMplayer.py
```

1. 先在系统中安装 VLC。
2. 使用 `pip install -r requirements.txt` 安装 Python 依赖。
3. 启动 WMplayer。
4. 打开 **Settings -> Library**，添加音乐文件夹。
5. 扫描曲库。
6. 通过右侧顶部标签浏览歌曲、歌手、专辑、播放队列、歌词和歌单。

如果项目根目录下存在 `library/` 文件夹，程序也会扫描其中的音乐。

## 歌单

WMplayer 支持读取和保存 M3U/M3U8 歌单。默认歌单目录是 `playlists/`，也可以在设置中添加其他歌单文件夹或单独的歌单文件。

```m3u
#EXTM3U
D:\Music\Album\Song 01.flac
D:\Music\Album\Song 02.mp3
```

读取歌单时，`#` 开头的行会被当作注释跳过。

## 歌词

把同名 `.lrc` 文件放在歌曲同一目录下即可：

```text
Song.flac
Song.lrc
```

带时间戳的 LRC 歌词会自动同步滚动。纯文本歌词也可以显示，但不会跟随播放进度。

## 项目结构

```text
.
|-- WMplayer.py              # 程序入口
|-- requirements.txt         # Python 依赖
|-- library/                 # 可选的内置音乐目录
|-- playlists/               # 默认歌单目录
|-- core/
|   |-- audio_engine.py      # libVLC 播放引擎
|   |-- config.py            # 设置和应用路径
|   |-- library.py           # 曲库扫描和元数据缓存
|   |-- lrc.py               # LRC 歌词解析
|   |-- m3u.py               # M3U/M3U8 读写
|   |-- metadata.py          # 音频元数据和封面读取
|   |-- playlist.py          # 播放队列和播放模式
|   `-- playlist_store.py    # 歌单存储
`-- ui/
    |-- main_window.py       # 主窗口连接逻辑
    |-- player_panel.py      # 左侧播放面板
    |-- library_panel.py     # 曲库视图
    |-- artists_panel.py     # 歌手视图
    |-- albums_panel.py      # 专辑视图
    |-- queue_panel.py       # 播放队列视图
    |-- lyrics_panel.py      # 歌词视图
    |-- playlists_panel.py   # 歌单视图
    |-- settings_dialog.py   # 设置窗口
    |-- i18n.py              # 界面翻译
    |-- widgets.py           # 自定义控件
    `-- theme.py             # 主题样式
```

## 打包

```bash
pyinstaller --noconfirm --onefile --windowed --name WMplayer WMplayer.py
```

## 品牌说明

WMplayer 是独立开源项目，不使用第三方 logo、产品名或官方品牌素材。

## 许可证

目前还没有添加许可证文件。如果要正式作为开源项目发布，建议先补充许可证。
