# Discovery and channel branding

## Research a recent style

- Use the user's platform, market, language, and genre preferences. Determine the exact rolling seven-day window. With an available YouTube Data API key, use `video.py discover` to get a bounded candidate sample. Otherwise use browser research. For other platforms use their public pages or authorized analytics. Search more than one related query when useful.
- Verify the original video and channel pages, the publication date, public view count, channel genre, and video format. Focus on videos published in the window. Treat older videos as a separate set if dated analytics demonstrate a surge. Report timestamped cumulative public views, label rounded figures, and compare separate format or platform cohorts where appropriate. A video length alone cannot establish its Shorts classification.
- Show at least five distinct channels with channel genre, strongest sampled recent video and its views, observed high-performing formats, and likely reasons the videos work. Include direct source links and label hypotheses about the hook, packaging, pacing, or payoff. Inspect supporting examples where possible. If the data source yields fewer than five, expand the search within the brief first. Share the verified subset and ask whether to expand the market, genre, or platform if the gap persists.
- Make the choice practical. Describe which recurring format or technique to adapt, approximate production effort, and why it suits the channel the user wants. Wait for the direction choice unless the user delegated it. Use original names, assets, character designs, and scripts.

## Build a reusable identity

Draft the name and handle candidate, audience promise, tagline, channel description, tags, mark, colors, and intended voice and recurring format. Verify the intended platform's current requirements and public handle availability where possible. Tie the identity to the direction the user selected. Group unresolved identity choices into a single review when needed.

Save the approved identity at `channels/<slug>/channel.json`. Save creative rules such as tone, publishing formats, recurring characters, thumbnail language, and voice preferences beside it in `brief.md`. Set the banner dimensions and safe area in the manifest based on the platform. Run `video.py brand` to make the original logo, banner, safe-area preview, and channel metadata. Inspect the logo at avatar size and the banner's cropped preview. If the user supplies approved brand assets or a more bespoke design is needed, store those next to the manifest and deliver the approved files with the brand kit. Use the same palette, font, and voice rules in subsequent episodes. Update them on request.
