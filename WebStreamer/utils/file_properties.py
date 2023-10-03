import hashlib
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.file_id import FileId
from typing import Any, Optional, Union
from pyrogram.raw.types.messages import Messages
from WebStreamer.server.exceptions import FIleNotFound
from datetime import datetime


async def parse_file_id(message: "Message") -> Optional[FileId]:
    media = get_media_from_message(message)
    if media:
        return FileId.decode(media.file_id)

async def parse_file_unique_id(message: "Messages") -> Optional[str]:
    media = get_media_from_message(message)
    if media:
        return media.file_unique_id

async def get_file_ids(client: Client, chat_id: int, message_id: int) -> Optional[FileId]:
    message = await client.get_messages(chat_id, message_id)
    if message.empty:
        raise FIleNotFound
    media = get_media_from_message(message)
    file_unique_id = media.file_unique_id
    file_id = FileId.decode(media.file_id)
    setattr(file_id, "file_size", getattr(media, "file_size", 0))
    setattr(file_id, "mime_type", getattr(media, "mime_type", ""))
    media_name = getattr(media, "file_name", "")
    file_name = get_name_prefix(message) + (media_name or "")
    setattr(file_id, "file_name", file_name)
    setattr(file_id, "unique_id", file_unique_id)
    return file_id

def get_media_from_message(message: "Message") -> Any:
    media_types = (
        "audio",
        "document",
        "photo",
        "sticker",
        "animation",
        "video",
        "voice",
        "video_note",
    )
    for attr in media_types:
        media = getattr(message, attr, None)
        if media:
            return media


def get_hash(media_msg: Union[str, Message], length: int = -1) -> str:
    if isinstance(media_msg, Message):
        media = get_media_from_message(media_msg)
        unique_id = getattr(media, "file_unique_id", "")
    else:
        unique_id = media_msg
    return unique_id
    long_hash = hashlib.sha256(unique_id.encode("UTF-8")).hexdigest()
    return long_hash[:length]


def get_file_id(media_msg: Message) -> str:
    media = get_media_from_message(media_msg)
    return media.file_id


def get_name_prefix(media_msg: Message) -> str:
    # prefix: forwarded_from_chat?.username, foward_date?:date (datetime to string), caption?
    prefix = ''
    forward_date = getattr(media_msg, "forward_date", None)
    if forward_date:
        prefix += forward_date.strftime("%Y-%m-%d %H-%M-%S") + ' '
    else:
        prefix += media_msg.date.strftime("%Y-%m-%d %H-%M-%S") + ' '
    forwarded_from_chat = getattr(media_msg, "forward_from_chat", None)
    if forwarded_from_chat:
        username = getattr(forwarded_from_chat, "username", None)
        if username:
            prefix += '@' + username + ' '
    caption = getattr(media_msg, "caption", None)
    if caption:
        prefix += caption.replace('\n', ' ').strip() + ' '
    prefix += get_hash(media_msg) + ' '
    #print(media_msg, forwarded_from_chat, forward_date, caption, prefix)
    return prefix


def get_name(media_msg: Union[Message, FileId]) -> str:

    if isinstance(media_msg, Message):
        media = get_media_from_message(media_msg)
        media_name = getattr(media, "file_name", "")
        file_name = get_name_prefix(media_msg) + (media_name or "")

    elif isinstance(media_msg, FileId):
        file_name = getattr(media_msg, "file_name", "")
    
    file_name = file_name.strip()

    if isinstance(media_msg, Message) and media_msg.media:
        media_type = media_msg.media.value
    elif media_msg.file_type:
        media_type = media_msg.file_type.name.lower()
    else:
        media_type = "file"

    formats = {
        "photo": "jpg", "audio": "mp3", "voice": "ogg",
        "video": "mp4", "animation": "mp4", "video_note": "mp4",
        "sticker": "webp"
    }

    ext = formats.get(media_type)
    ext = "." + ext if ext else ""

    if not file_name.lower().endswith(ext):
        file_name += ext

    #date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_name = f"{media_type}/{file_name}"

    return file_name
