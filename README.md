## aria2 branch: Download with aria2, then serve files from the download directory instead of fetching from server.
new env:
```sh
SAVE_TO=/catalyst/edge/syncthing/Telegram
MAX_CONCURRENT_DOWNLOADS=2
ARIA2_API=http://localhost
ARIA2_PORT=6800
```