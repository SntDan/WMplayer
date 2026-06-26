from __future__ import annotations

from typing import Any


_LANG = "en"


_STRINGS = {
    "en": {
        "language": "Language",
        "language_en": "English",
        "language_zh": "Chinese",
        "library": "Library",
        "artists": "Artists",
        "albums": "Albums",
        "queue": "Queue",
        "lyrics": "Lyrics",
        "playlists": "Playlists",
        "general": "General",
        "settings": "Settings",
        "search_library": "Search artists / albums / songs",
        "search_queue": "Search queue",
        "search_artists": "Search artists...",
        "search_albums": "Search albums...",
        "scan_library": "Scan Library",
        "save_as_playlist": "Save as Playlist",
        "clear": "Clear",
        "play": "Play",
        "play_now": "Play Now (Replace Queue)",
        "enqueue": "Add to Queue",
        "add_to_playlist": "Add to Playlist...",
        "open_artist": "Open Artist",
        "open_album": "Open Album",
        "load_and_play": "Load and Play",
        "rename": "Rename...",
        "delete": "Delete",
        "new_name": "New name:",
        "delete_playlist": "Delete Playlist",
        "delete_playlist_confirm": "Delete playlist \"{name}\"?\n(Original music files will not be deleted)",
        "playlist_name": "Playlist name:",
        "remove_from_queue": "Remove from Queue",
        "tracks_count": "{n} songs",
        "albums_count": "{n} albums",
        "artists_count": "{n} artists",
        "items_count": "{n} items",
        "artist_header": "Artists ({n})",
        "album_header": "Albums ({n})",
        "song_header": "Songs ({n})",
        "album_track_count": "{albums} albums · {tracks} songs",
        "artist_track_count": "{artist} · {tracks} songs",
        "unknown_artist": "Unknown Artist",
        "unknown_album": "Unknown Album",
        "no_cover": "No Cover",
        "scanning": "Scanning...",
        "scan_progress": "Scanning {done}/{total}",
        "default_dir": "Default directory:",
        "default_dir_tooltip": "Default directory, always enabled and cannot be changed",
        "other_library_dirs": "Other library folders:",
        "other_playlist_sources": "Other playlist sources or .m3u8 files:",
        "add_folder": "+ Add Folder",
        "add_playlist_file": "+ Add Playlist File",
        "remove_selected": "Remove Selected",
        "choose_library_root": "Choose Library Root",
        "choose_playlist_folder": "Choose Playlist Folder",
        "choose_playlist_file": "Choose Playlist File",
        "playlist_hint": (
            "<div style='color:#888;font-size:11px;'>"
            "New, renamed, and deleted playlists are stored in the default directory.<br>"
            "Additional playlist sources are read-only and can only be played."
            "</div>"
        ),
        "volume": "Volume",
        "auto_resume": "Resume last playback position on startup",
        "factory_reset": "Factory Reset...",
        "factory_reset_title": "Factory Reset",
        "factory_reset_confirm": (
            "Clear all caches (library index, play queue) and restore default settings, "
            "then close the app automatically.\nThis cannot be undone. Continue?"
        ),
        "about": (
            "<div style='color:#9E9E9E;font-size:11px;'>"
            "Audio engine: libVLC &nbsp;|&nbsp; UI: PyQt6<br>"
            "Supports: MP3 / FLAC / WAV / ALAC / APE / OGG / Opus / DSD"
            "</div>"
        ),
        "default_playlist_dir": "Default directory: {path}",
        "sequential_play": "Play in Order",
        "shuffle_play": "Shuffle Play",
        "back": "Back",
        "no_lrc": "No matching .lrc file",
        "plain_text": "Plain Text",
        "lyrics_missing_help": (
            "No lyrics found\n\n"
            "Put a matching .lrc file in the same folder as the song\n"
            "(for example song.flac -> song.lrc)"
        ),
        "clear_queue_title": "Clear Queue",
        "clear_queue_confirm": "Clear the play queue?",
        "save_failed_title": "Save Failed",
        "save_failed_msg": "Could not write the playlist file. Please check playlist directory permissions.",
        "saved_playlist_status": "Saved playlist \"{name}\"",
        "added_to_queue_status": "Added {n} songs to queue",
        "new_playlist": "New Playlist",
        "select_playlist": "Select target playlist:",
        "join_playlist": "Add to Playlist",
        "create_playlist_status": "Created playlist \"{name}\" and added {n} songs",
        "added_to_playlist_status": "Added {n} songs to playlist \"{name}\"",
        "empty_playlist_title": "Empty Playlist",
        "empty_playlist_msg": "Playlist \"{name}\" is empty.",
        "readonly_rename_title": "Cannot Rename",
        "readonly_rename_msg": "This playlist is from an additional read-only source. Copy it to the default directory before renaming.",
        "rename_failed_title": "Rename Failed",
        "rename_failed_msg": "The new name may already exist, or the file could not be renamed.",
        "readonly_delete_title": "Cannot Delete",
        "readonly_delete_msg": "This playlist is from an additional read-only source. Delete it manually at its original location.",
        "error_status": "Error: {msg}",
    },
    "zh": {
        "language": "语言",
        "language_en": "英文",
        "language_zh": "中文",
        "library": "曲库",
        "artists": "歌手",
        "albums": "专辑",
        "queue": "播放队列",
        "lyrics": "歌词",
        "playlists": "歌单",
        "general": "通用",
        "settings": "设置",
        "search_library": "搜索歌手 / 专辑 / 歌曲",
        "search_queue": "搜索队列内",
        "search_artists": "搜索歌手...",
        "search_albums": "搜索专辑...",
        "scan_library": "扫描曲库",
        "save_as_playlist": "另存为歌单",
        "clear": "清空",
        "play": "播放",
        "play_now": "立即播放(替换队列)",
        "enqueue": "加入播放队列",
        "add_to_playlist": "加入歌单...",
        "open_artist": "打开歌手",
        "open_album": "打开专辑",
        "load_and_play": "加载并播放",
        "rename": "重命名...",
        "delete": "删除",
        "new_name": "新名称:",
        "delete_playlist": "删除歌单",
        "delete_playlist_confirm": "确定要删除歌单 \"{name}\" 吗?\n(原始音乐文件不会被删除)",
        "playlist_name": "歌单名称:",
        "remove_from_queue": "从队列移除",
        "tracks_count": "{n} 首",
        "albums_count": "{n} 张专辑",
        "artists_count": "{n} 位歌手",
        "items_count": "{n} 个",
        "artist_header": "歌手 ({n})",
        "album_header": "专辑 ({n})",
        "song_header": "歌曲 ({n})",
        "album_track_count": "{albums} 张专辑 · {tracks} 首",
        "artist_track_count": "{artist} · {tracks} 首",
        "unknown_artist": "未知歌手",
        "unknown_album": "未知专辑",
        "no_cover": "无封面",
        "scanning": "正在扫描...",
        "scan_progress": "扫描中 {done}/{total}",
        "default_dir": "默认目录:",
        "default_dir_tooltip": "默认目录,始终启用,不可更改",
        "other_library_dirs": "其他曲库目录:",
        "other_playlist_sources": "其他歌单源或.m3u8文件:",
        "add_folder": "+ 添加文件夹",
        "add_playlist_file": "+ 添加歌单文件",
        "remove_selected": "移除选中",
        "choose_library_root": "选择曲库根目录",
        "choose_playlist_folder": "选择歌单文件夹",
        "choose_playlist_file": "选择歌单文件",
        "playlist_hint": (
            "<div style='color:#888;font-size:11px;'>"
            "新建/重命名/删除的歌单都保存到默认目录。<br>"
            "附加源里的歌单只能播放,不能修改。"
            "</div>"
        ),
        "volume": "音量",
        "auto_resume": "启动时恢复上次播放进度",
        "factory_reset": "恢复出厂设置...",
        "factory_reset_title": "恢复出厂设置",
        "factory_reset_confirm": "将清除所有缓存(曲库索引、播放队列)并恢复默认设置，然后自动关闭程序。\n此操作不可撤销，是否继续？",
        "about": (
            "<div style='color:#9E9E9E;font-size:11px;'>"
            "音频内核: libVLC &nbsp;|&nbsp; UI: PyQt6<br>"
            "支持: MP3 / FLAC / WAV / ALAC / APE / OGG / Opus / DSD"
            "</div>"
        ),
        "default_playlist_dir": "默认目录: {path}",
        "sequential_play": "顺序播放",
        "shuffle_play": "随机播放",
        "back": "返回",
        "no_lrc": "没有同名 .lrc 文件",
        "plain_text": "纯文本",
        "lyrics_missing_help": "未找到歌词\n\n把同名 .lrc 文件放在歌曲同一目录下\n(例如 song.flac -> song.lrc)",
        "clear_queue_title": "清空队列",
        "clear_queue_confirm": "确定要清空播放队列吗?",
        "save_failed_title": "保存失败",
        "save_failed_msg": "无法写入歌单文件,请检查歌单目录权限。",
        "saved_playlist_status": "已保存歌单 \"{name}\"",
        "added_to_queue_status": "已加入 {n} 首到队列",
        "new_playlist": "新建歌单",
        "select_playlist": "选择目标歌单:",
        "join_playlist": "加入歌单",
        "create_playlist_status": "已创建歌单 \"{name}\" 并加入 {n} 首",
        "added_to_playlist_status": "已加入 {n} 首到歌单 \"{name}\"",
        "empty_playlist_title": "歌单为空",
        "empty_playlist_msg": "歌单 \"{name}\" 是空的。",
        "readonly_rename_title": "无法重命名",
        "readonly_rename_msg": "该歌单来自附加源,只读。请把它复制到默认目录后再重命名。",
        "rename_failed_title": "重命名失败",
        "rename_failed_msg": "新名称可能已存在,或文件无法重命名。",
        "readonly_delete_title": "无法删除",
        "readonly_delete_msg": "该歌单来自附加源,只读。请到对应位置手动删除。",
        "error_status": "错误: {msg}",
    },
}


def set_language(lang: str) -> None:
    global _LANG
    _LANG = "zh" if lang == "zh" else "en"


def language() -> str:
    return _LANG


def tr(key: str, **kwargs: Any) -> str:
    text = _STRINGS.get(_LANG, _STRINGS["en"]).get(key, _STRINGS["en"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text
