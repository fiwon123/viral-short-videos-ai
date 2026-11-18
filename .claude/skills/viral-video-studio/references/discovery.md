# Discovery and channel branding

## Interview the user, one question at a time

When the user starts a channel and the direction is not already known, ask before researching. Ask **one question per message** with three or four concrete options (the recommended one first, marked as such) and room for their own answer. Skip any question the user already answered or clearly delegated. If they say "you choose", pick the option with the best potential from the research and say why. Write each answer to `workspace/<slug>/research/onboarding.md` as soon as it is given, so an interrupted session can resume at the next question.

1. **Purpose and audience.** Who is it for (kids, teens, adults, a professional niche), and what do viewers get (laughs, comfort, curiosity, learning, suspense)?
2. **Tone.** Serious, comedy, wholesome, dark or mystery, satire, motivational, or educational. A mix is fine; ask which leads.
3. **Topic and genre.** Offer niches that fit the tone (for example comedy: workplace, animals, everyday absurdity; serious: history, science, true stories, psychology). Ask what they enjoy or know well, since that sustains a channel.
4. **Format.** A series with recurring characters and continuity, standalone episodes in a shared world, or a narrated explainer format. Also narrator, dialogue, or silent.
5. **Animation style.** 2D flat vector, 2D cut-out rig (the generated characters), 2.5D paper or parallax, stylised 3D, or mixed. State the production effort of each, and which the studio does best (see the [animation cookbook](animation-cookbook.md)).
6. **Platform, language, and market.** YouTube Shorts, TikTok, Reels or long-form; the spoken language; the target country or region for trend research.
7. **Length and cadence.** Typical runtime and how many episodes per week. Be honest that the cadence has to be sustainable.
8. **Voice and sound.** Narrator or character voices, energy and gender, and music mood.

Close with a one-paragraph summary of the answers and ask the user to confirm it before trend research.

## Research what is working now

- Use the confirmed answers for queries, market, and language. Use the exact rolling window (default seven days; also check fourteen when the niche is slow). Search several related queries: the topic, the format, and the style (for example "animated story short", "<topic> animation").
- **With `YOUTUBE_API_KEY`:** run `video.py discover` three ways and merge the results. `--rank views` gives the biggest videos, `--rank velocity` gives views per hour since publish (the fastest risers), and `--rank outlier` gives views per subscriber (videos that broke out of their audience, the best sign that a format, not an existing fanbase, did the work). Add `--shorts` for short-form and `--snapshots workspace/<slug>/research/snapshots`. Run it again 6–24 hours later with the same folder to get `views_gained` and `views_per_hour_since_last`: real growth, not an average.
- **Without a key:** use browser research. Use the platform search with the upload-date and type filters, the channel pages, and public trend pages (for example TikTok Creative Center for hashtags and sounds, Google Trends for topic interest). Record each view count with the time you read it, and read it again later in the session or the next day to estimate growth.
- Verify each video on its original page: publication date, public views, channel size, format, and Shorts status. A video's length alone does not prove it is a Short. Label rounded figures and estimates, and never invent numbers.

## Present the findings

Save the research to `workspace/<slug>/research/trends-YYYY-MM-DD.md`, then show the user:

1. **Ranked table**, most views first. Columns: rank, video (link), channel and subscribers, age, views, views per hour, growth since the last check (when measured), views per subscriber, type (narrated story, sketch, explainer, compilation, character series...), topic, and a labelled hypothesis of why it works (hook in the first two seconds, packaging, pacing, payoff, timeliness).
2. **Fastest risers.** Re-sort the same set by views per hour and by views per subscriber, and call out small channels with outsized videos. Those formats are the most transferable.
3. **Patterns.** Recurring topics, hooks, formats, lengths, visual styles, and how quickly the videos grew. Most Shorts earn the bulk of their views in the first 48–72 hours, and a video still accelerating after day 3 is being pushed to new audiences. Note posting cadence where visible.
4. **Directions with potential.** Two to four original directions that fit the user's answers. For each: the audience promise, a repeatable episode premise, why it could grow quickly (which observed pattern it borrows, which gap it fills), production effort, and one pilot idea. Be honest: no format guarantees virality, and early consistency (several episodes a week, a strong hook, a clear series promise) matters more than any one video.

Use original names, characters, world, scripts, and assets. Transfer techniques, not content. Wait for the direction choice unless the user delegated it, then build the identity and set up the channel memory (see [episode planning](episode-planning.md)).

## Build a reusable identity

Draft the name and handle candidate, audience promise, tagline, channel description, tags, mark, colors, and intended voice and recurring format. Verify the intended platform's current requirements and public handle availability where possible. Tie the identity to the direction the user selected. Group unresolved identity choices into a single review when needed.

Save the approved identity at `workspace/<slug>/channel/channel.json`. Save creative rules such as tone, publishing formats, recurring characters, thumbnail language, and voice preferences in `brief.md` and `channel/AGENTS.md`. Set the banner dimensions and safe area in the manifest based on the platform. Run `video.py brand` to make the original logo, banner, safe-area preview, and channel metadata. Inspect the logo at avatar size and the banner's cropped preview. If the user supplies approved brand assets or a more bespoke design is needed, store those next to the manifest and deliver the approved files with the brand kit. Use the same palette, font, and voice rules in subsequent episodes. Update them on request, and log the change in the channel memory's direction history.
