# ❓ FAQ

### Do I need an AI model to use this?

No. The studio is manifest-driven. An AI makes the workflow faster, but you can write the JSON and assets yourself.

### Which model works best?

Any model that can read files and follow structured instructions. A coding assistant with terminal access can validate and render. A chat-only model can return manifests and asset lists.

### Can AI make its own audio?

Yes. It can import WAVs, use the built-in Foley bank, or write a Sound Lab recipe and synthesize a new cue into the channel.

### Can AI make its own effects?

Yes. It can write an SVG by hand, use the built-in kit, or generate a palette-matched effect with Effect Lab.

### Can I disable sound mastering, captions or thumbnails?

Yes. Use `audio.master.enabled: false`, `render.captions: false`, `render.thumbnail: false` or the matching CLI flags.

### Can I use my own font?

Yes. Add the font path to `channel.json` or `captions.font` and regenerate.

### Does it support 60 fps?

The schema allows 12, 15, 24, 25, 30, 48, 50 and 60 fps. 24 is the default because it reads well for animation.

### Can I render a vertical Short longer than 60 seconds?

Yes, up to the platform limit or 12 minutes. The studio checks `max_seconds`.

### Can I use real footage?

You can import images and SVG. Video layers are not part of the current manifest. Use a licensed clip as a reference or bake it into frames before import.

### Where do my private channels live?

`workspace/` is gitignored. Only `examples/` is published.

### Why is there a `wiki/` folder if GitHub has a Wiki tab?

`wiki/` is a versioned mirror of the documentation. The GitHub Wiki tab is the live copy. Keep the two in sync when a page changes.

### How do I edit the wiki?

Use the GitHub Wiki tab directly. The `wiki/` folder in the repository is there so documentation changes can be reviewed and versioned with the code.

### Is the example content free to reuse?

The code and structure are MIT. The example characters and art are original showcase material; build your own world rather than copying them.

## 🔗 Related guides

- [Quick Start](Quick-Start)
- [Contributing](Contributing)
