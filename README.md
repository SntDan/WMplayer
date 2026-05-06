# 高保真本地音乐播放器

Python 写的桌面音乐播放器,黑底 + 白线 + 红按钮。
内核 libVLC,支持 MP3 / FLAC / WAV / ALAC / APE / OGG / Opus / DSD 等。

## v1.1 新增

- **曲库 + 歌单 + 队列三层模型**(以前是单一播放列表)
  - 曲库 = 你指定的若干文件夹,扫描出全部音频
  - 歌单 = `playlists/` 目录下的多个 `.m3u8` 文件
  - 队列 = 当前正在播的曲目列表
- **M3U8 互通**:歌单格式与你给的样例一致(`#EXTM3U` + 路径行),可直接和 foobar2000 / Hi-By Music / Walkman 等互通
- **增量扫描**:曲库元数据缓存到 `library_cache.json`,文件 mtime 没变就跳过重读
- **右侧三视图切换**:曲库 / 队列 / 歌单 — 顶部分段控件 + 左下三个红色按钮都能切

## 目录结构

```
music_player/
├── README.md
├── main.py                  ← 入口
├── requirements.txt
├── library/                 ← (可选)放音乐到这里,会被自动扫描
├── playlists/               ← 歌单 .m3u8 文件存放在这里
├── core/
│   ├── audio_engine.py      ← libVLC 封装
│   ├── playlist.py          ← 当前播放队列(含 4 种播放模式)
│   ├── library.py           ← 曲库扫描 + 元数据缓存
│   ├── playlist_store.py    ← 多 .m3u8 歌单 CRUD
│   ├── m3u.py               ← M3U/M3U8 读写
│   ├── metadata.py          ← MP3/FLAC/M4A/OGG 标签 + 封面
│   └── config.py            ← 跨平台配置
└── ui/
    ├── widgets.py           ← 自绘按钮 / 进度条 / 封面
    ├── player_panel.py      ← 左侧播放器
    ├── library_panel.py     ← 右侧·曲库视图
    ├── queue_panel.py       ← 右侧·队列视图
    ├── playlists_panel.py   ← 右侧·歌单视图
    ├── main_window.py       ← 主窗口
    ├── settings_dialog.py   ← 设置(含曲库管理)
    └── theme.py
```

## 安装

### 1. 系统级:VLC

- macOS: `brew install --cask vlc`
- Windows: 到 https://www.videolan.org/vlc/ 下载安装(64 位 Python 装 64 位 VLC)
- Linux: `sudo apt install vlc`

### 2. Python

```bash
cd music_player
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 运行

```bash
python main.py
# 或 python -m music_player
```

## 使用流程

### 第一次

1. 打开后点 **右下工具箱图标 → 设置 → 曲库** tab
2. 添加你的音乐文件夹(可加多个),勾选"同时扫描程序自带 library/"
3. 点 OK,程序会自动扫描

或者:把音乐直接拖进程序根目录的 `library/` 子文件夹,启动时也会被扫描。

### 切换三个视图

- 左下 **红色书** = 曲库
- 左下 **红色返回** = 播放队列(默认)
- 中下 **红色文件夹** = 歌单
- 也可以点右侧顶部 segmented control 切换

### 创建歌单

- 在曲库视图选中若干曲目 → 右键 → "加入歌单..." → 选已有或新建
- 或在队列视图点 "另存为歌单"
- 也可以手动把 `.m3u8` 文件拷到 `playlists/` 目录,程序自动识别

### M3U8 格式

```
#EXTM3U
#我的最爱.m3u8
D:\Music\Vansire\After Fillmore County\Vansire - The Latter Teens.mp3
D:\Music\GRAE\2725\GRAE - 2725.flac
```

注释行(`#` 开头的)解析时全部跳过,所以与各家播放器格式都兼容。

## 快捷键

| 键 | 作用 |
|---|---|
| Space | 播放/暂停 |
| ← / → | 后退/前进 5 秒 |
| ↑ / ↓ | 音量 ±5 |
| Delete | 从队列删除选中项 |
| 双击 | 立即播放 |

## 配置文件位置

- macOS: `~/Library/Application Support/MusicPlayer/`
- Linux: `~/.config/MusicPlayer/`
- Windows: `%APPDATA%/MusicPlayer/`

含 `settings.json`、`library_cache.json`、`queue.m3u8`(下次启动恢复用)。
歌单本身在程序根的 `playlists/` 里(可在设置中改)。
