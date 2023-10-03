import os
import sqlite3
import asyncio
import aria2p
from collections import deque
from datetime import timedelta
from ..vars import Var


class Connect(object):
    def __init__(self) -> None:
        self.conn = sqlite3.connect('downloaded.db')
        self.conn.row_factory = sqlite3.Row
        self.c = self.conn.cursor()
        self.c.execute('CREATE TABLE IF NOT EXISTS downloaded (file_unique_id TEXT PRIMARY KEY, file_id TEXT, file_name TEXT, date timestamp)')
        self.c.execute('CREATE TABLE IF NOT EXISTS downloading (stream_link TEXT PRIMARY KEY, short_link TEXT, file_unique_id TEXT, file_id TEXT, file_name TEXT, date timestamp)')
        self.c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, status_message INTEGER)')
        self.conn.commit()
    
    def query_by_column(self, table: str, key: str, value: str) -> dict:
        self.c.execute(f"SELECT * FROM {table} WHERE {key} = ?", (value,))
        row = self.c.fetchone()
        if row:
            return dict(row)
        return {}

    def save_downloading(self, stream_link: str, short_link: str, file_unique_id: str, file_id: str, file_name: str) -> None:
        self.c.execute("INSERT OR REPLACE INTO downloading VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))", (stream_link, short_link, file_unique_id, file_id, file_name))
        self.conn.commit()
    
    def save_downloaded(self, stream_link: str, file_unique_id: str, file_id: str, file_name: str) -> None:
        self.c.execute("INSERT INTO downloaded VALUES (?, ?, ?, datetime('now','localtime'))", (file_unique_id, file_id, file_name))
        self.c.execute("DELETE FROM downloading WHERE stream_link = ?", (stream_link,))
        self.conn.commit()


DB = Connect()


class User(object):
    def __init__(self, user_id: int, status_message: int | None = None, skip_check: bool = False) -> None:
        if not skip_check:
            user = DB.query_by_column("users", "user_id", user_id)
            if not user:
                DB.c.execute("INSERT INTO users VALUES (?, ?)", (user_id, status_message))
                DB.conn.commit()
            else:
                status_message = user['status_message']
        self.init(user_id, status_message)

    def init(self, user_id: int, status_message: int | None) -> None:
        self.user_id = user_id
        self.status_message = status_message
        self.status_text = ''
    
    def set_status_message(self, status_message: int) -> None:
        DB.c.execute("UPDATE users SET status_message = ? WHERE user_id = ?", (status_message, self.user_id))
        DB.conn.commit()


class Users(object):
    def __init__(self) -> None:
        self.users = {}
        for user in DB.c.execute("SELECT * FROM users"):
            self.users[user['user_id']] = User(user['user_id'], user['status_message'], skip_check=True)
    
    def get(self, user_id: int) -> User:
        if user_id not in self.users:
            self.users[user_id] = User(user_id)
        return self.users[user_id]
    

users = Users()
skip_download = aria2p.Download('', {'bitfield': '0000000000', 'completedLength': '0', 'connections': '1', 'dir': '/downloads', 'downloadSpeed': '0', 'files': [{'index': '1', 'length': '0', 'completedLength': '0', 'path': '/downloads/file', 'selected': 'true', 'uris': [{'status': 'used', 'uri': 'http://example.org/file'}]}], 'gid': '0000000000000001', 'numPieces': '34', 'pieceLength': '1048576', 'status': 'complete', 'totalLength': '0', 'uploadLength': '0', 'uploadSpeed': '0'})
skip_download.update = lambda: None


class Downloader(object):
    def __init__(self) -> None:
        self.aria2 = aria2p.API(
            aria2p.Client(
                host=Var.ARIA2_API,
                port=Var.ARIA2_PORT,
                secret=""
            )
        )
        try:
            # TODO: options aren't all applied for some reason
            options = {
                "dir": Var.SAVE_TO,
                "continue_downloads": True,
                "max-concurrent-downloads": Var.MAX_CONCURRENT_DOWNLOADS,
                "split": 1,
                "min-split-size": "1M",
                "max_connection_per_server": Var.MAX_CONCURRENT_DOWNLOADS,
            }
            options = aria2p.Options(self.aria2, options)
            self.aria2.set_global_options(options)
        except Exception as e:
            print(e)
            exit(1)
        self.downloading = []
    
    @property
    def num_downloading(self) -> int:
        return sum([download[0].is_active for download in self.downloading])

    def clear_downloading_when_all_completed(self) -> None:
        if all([download[0].is_complete and not download[1] for download in self.downloading]):
            self.downloading.clear()

    def download_url(self, uri: str, file_name: str, callback_message: 'Message', file_unique_id: str, file_id: str) -> None:
        self.clear_downloading_when_all_completed()
        if os.path.exists(os.path.join(Var.SAVE_TO, file_name)):
            self.downloading.append([skip_download, callback_message, uri, file_unique_id, file_id, file_name])
        else:
            self.downloading.append([self.aria2.add_uris([uri], options={"out": file_name}), callback_message, uri, file_unique_id, file_id, file_name])

    def download(self, stream_link: str, short_link: str, file_unique_id: str, file_id: str, file_name: str, callback_message: 'Message'):
        # limit basename part of file_name to at most 255 chars in utf8
        # preserving extension
        # add "..." to indicate that the name was cut
        base_filename = os.path.basename(file_name)
        if len(base_filename.encode()) > 255:
            ext = os.path.splitext(base_filename)[1]
            base_filename = base_filename[: 255 - len(ext) - 3] + "..." + ext
            file_name = os.path.join(os.path.dirname(file_name), base_filename)
        DB.save_downloading(stream_link, short_link, file_unique_id, file_id, file_name)
        self.download_url(stream_link, file_name, callback_message, file_unique_id, file_id)
    
    def _update_all_downloads(self) -> None:
        for download in self.downloading:
            download[0].update()

    @property
    def status(self) -> str:
        status = self.aria2.get_stats()
        self._update_all_downloads()
        completed_count = sum([download[0].is_complete for download in self.downloading])
        waiting_count = status.num_waiting # sum([download[0].is_waiting for download in self.downloading])
        completed_size = sum([download[0].completed_length for download in self.downloading])
        total_size = sum([download[0].total_length for download in self.downloading])
        try:
            total_eta = sum([download[0].eta for download in self.downloading], timedelta())
        except OverflowError:
            total_eta = timedelta(seconds=0)
        download_speed = status.download_speed # sum([download[0].download_speed for download in self.downloading])
        if download_speed == 0:
            pending_eta = '?'
        else:
            pending_eta = aria2p.utils.human_readable_timedelta(timedelta(seconds=(total_size - completed_size) / download_speed))
        message = f'''<code>Downloading {len(self.downloading)} tasks: {aria2p.utils.human_readable_bytes(completed_size, digits=0)} / {aria2p.utils.human_readable_bytes(total_size)}
Current tasks ETA: {aria2p.utils.human_readable_timedelta(total_eta)} / Pending ETA: {pending_eta}
Completed: {completed_count} / Pending: {waiting_count}
{aria2p.utils.human_readable_bytes(download_speed, postfix="/s")}</code>
'''
        return message


downloader = Downloader()
