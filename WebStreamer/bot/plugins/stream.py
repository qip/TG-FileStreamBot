# This file is a part of TG-FileStreamBot
# Coding : Jyothis Jayanth [@EverythingSuckz]

import os
import logging
import asyncio
import subprocess
from pyrogram import filters, errors, Client
from WebStreamer.vars import Var
from urllib.parse import quote
from WebStreamer.bot import StreamBot, logger
from WebStreamer.utils import get_hash, get_name, get_file_id, DB, users, downloader
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery


@StreamBot.on_message(
    filters.private
    & (
        filters.document
        | filters.video
        | filters.audio
        | filters.animation
        | filters.voice
        | filters.video_note
        | filters.photo
        | filters.sticker
    ),
    group=4,
)
async def media_receive_handler(client: Client, m: Message):
    try:
        user = users.get(m.chat.id)
        if not user.status_message:
            user.status_message = True
            user.status_message = await client.send_message(
                chat_id=m.chat.id,
                text="Processing...",
            )
            #await user.status_message.pin()
            user.set_status_message(user.status_message.id)
        elif type(user.status_message) is int:
            user.status_message = await client.get_messages(m.chat.id, user.status_message)
        if Var.ALLOWED_USERS and not ((str(m.from_user.id) in Var.ALLOWED_USERS) or (m.from_user.username in Var.ALLOWED_USERS)):
            return await m.reply("You are not in the group.", quote=True)
        log_msg = await m.forward(chat_id=Var.BIN_CHANNEL)
        file_hash = get_hash(log_msg, Var.HASH_LENGTH)
        file_name = DB.query_by_column("downloaded", "file_unique_id", file_hash).get("file_name")
        if file_name:
            stream_link = f"{Var.URL}static/{file_name}"
            stream_link_quoted = f"{Var.URL}static/{quote(file_name)}"
            try:
                sent = await m.reply_text(
                    text=f"<code>{stream_link}</code>",
                    quote=True,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("Open", url=stream_link_quoted)]]
                    ),
                )
            except errors.ButtonUrlInvalid:
                sent = await m.reply_text(
                    text=stream_link_quoted,
                    quote=True,
                    parse_mode=ParseMode.HTML,
                )
        else:  # TODO: sum file_size from m to status_text
            file_name = get_name(m)
            stream_link = f"{Var.URL}{log_msg.id}/{quote(file_name)}?hash={file_hash}"
            short_link = f"{Var.URL}{file_hash}.{log_msg.id}"
            logger.info(f"Generated link: {stream_link} for {m.from_user.first_name}")
            try:
                sent = await m.reply_text(
                    text=f"<code>{stream_link}</code>\n(<a href='{short_link}'>shortened</a>)",
                    quote=True,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("Open", url=stream_link)], [InlineKeyboardButton("Retry", callback_data=file_hash)]]
                    ),
                )
            except errors.ButtonUrlInvalid:
                sent = await m.reply_text(
                    text=f"<code>{stream_link}</code>\n\nshortened: {quote(short_link)}",
                    quote=True,
                    parse_mode=ParseMode.HTML,
                )
            downloader.download(stream_link, short_link, file_hash, get_file_id(log_msg), file_name, sent)
            #asyncio.create_task(downloader(stream_link, short_link, file_hash, get_file_id(log_msg), file_name, sent))
    except Exception as e:
        sent = await m.reply_text(
            text=f"<code>{e}</code>",
            quote=True,
            parse_mode=ParseMode.HTML,
        )
        raise e


@StreamBot.on_callback_query(filters.regex("^https?://"))
async def on_retry_callback(client: Client, callback_query: CallbackQuery):
    file_unique_id = callback_query.data
    row = DB.query_by_column("downloading", "file_unique_id", file_unique_id)
    steam_link = row["stream_link"]
    short_link = row["short_link"]
    file_id = row["file_id"]
    file_name = row["file_name"]
    await callback_query.message.edit_text(
        text=f"Retrying<br>\n<code>{stream_link}</code>\n(<a href='{short_link}'>shortened</a>)",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Open", url=stream_link)]]
        ),
    )
    await callback_query.answer()
    downloader.download(stream_link, short_link, file_unique_id, file_id, file_name, callback_query.message)


async def manage_downloads():
    while True:
        if downloader.downloading:
            status_text = downloader.status
            # process status message
            if downloader.num_downloading:
                for user_id in users.users:
                    user = users.get(user_id)
                    if user.status_message and user.status_text != status_text:
                        user.status_text = status_text
                        await user.status_message.edit_text(
                            text=status_text,
                            parse_mode=ParseMode.HTML,
                        )
            else:  # TODO: if there's already completed downloads, new downloads will trigger clean causing this to delete progress message, resulting progress message created later as newer message.
                for user_id in users.users:
                    user = users.get(user_id)
                    if user.status_message:
                        try:
                            if type(user.status_message) is int:
                                user.status_message = await client.get_messages(m.chat.id, user.status_message)
                            await user.status_message.delete()
                        except Exception as e:
                            print(e)
                        user.status_message = None
                        user.set_status_message(None)
                downloader.clear_downloading_when_all_completed()
            # process media reply message
            for index, (download, message, stream_link, file_unique_id, file_id, file_name) in enumerate(downloader.downloading):
                if message:
                    if download.is_complete:
                        DB.save_downloaded(stream_link, file_unique_id, file_id, file_name)
                        stream_link = f"{Var.URL}static/{file_name}"
                        stream_link_quoted = f"{Var.URL}static/{quote(file_name)}"
                        try:
                            await message.edit_text(
                                text=f"<code>{stream_link}</code>",
                                parse_mode=ParseMode.HTML,
                                reply_markup=InlineKeyboardMarkup(
                                    [[InlineKeyboardButton("Open", url=stream_link_quoted)]]
                                ),
                            )
                        except errors.ButtonUrlInvalid as e:
                            await message.edit_text(
                                text=stream_link_quoted,
                                parse_mode=ParseMode.HTML,
                            )
                        downloader.downloading[index][1] = None  # set message to None to prevent editing it again
                    elif download.has_failed:
                        try:
                            await message.edit_text(
                                text=f"Download failed<br>\n<code>{stream_link}</code>\n(<a href='{short_link}'>shortened</a>)",
                                parse_mode=ParseMode.HTML,
                                reply_markup=InlineKeyboardMarkup(
                                    [[InlineKeyboardButton("Open", url=stream_link)], [InlineKeyboardButton("Retry", callback_data=file_unique_id)]]
                                ),
                            )
                        except errors.ButtonUrlInvalid:
                            await message.edit_text(
                                text=f"Download failed<br>\n<code>{stream_link}</code>\n\nshortened: {short_link}",
                                parse_mode=ParseMode.HTML,
                            )
                        downloader.downloading[index][1] = None  # set message to None to prevent editing it again
            #downloader.downloading = [download for download in downloader.downloading if not download[0].is_complete and not download[0].has_failed]
            #print(downloader.downloading, [download[0].status for download in downloader.downloading])
        await asyncio.sleep(5)


asyncio.create_task(manage_downloads())