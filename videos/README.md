# Free-trial videos

The website's `/videos` page lists the fourteen free-trial videos (`frontend/src/site/videos.tsx` holds their titles).
On the server this folder is mounted read-only into the web container at `/media/videos`
(`docker-compose.prod.yml`) and served by Caddy, so a finished video is published by copying its files here: no
release, no restart.

The English captions are part of each video's picture, so no caption file is needed (a caption track would
make the browser show the text twice). Per video, with plain file names (letters, digits, `.`, `_`, `-`):

- the video, `NN-short-title.mp4` (H.264 and AAC, as the video pipeline writes it);
- optionally a poster, `NN-short-title.jpg` (a frame of the title slide).

Then add it to `videos.json`, the list the page reads:

```json
{
  "videos": [
    { "number": 1, "file": "01-welcome.mp4", "poster": "01-welcome.jpg", "minutes": 5.4 }
  ]
}
```

A video missing from `videos.json`, or listed with a malformed entry, shows as "Coming soon". The media files are not
kept in git (`.gitignore`); this README is.
