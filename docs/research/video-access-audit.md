# Public video / transcript access audit
Checked 2026-11-18. Scope below is a targeted set, NOT all official videos.

## Important access correction
Web tool direct opens often gave 403, but ordinary unauthenticated curl fetched the official free-sample page, June 2020 room page and 2016 live-commentary transcript with HTTP 200. Thus “website inaccessible” is too broad. No paywall, signup, email submission or authentication used.

## Five official sample-page items (metadata verified from direct HTML)
Canonical source: https://www.brookstradingcourse.com/free-sample-price-action-trading-videos/
1. 12A Market Cycle — full sample, 43:28. Official YouTube mirror https://www.youtube.com/watch?v=_wQ5CRIQ6mc . YouTube watch HTML accessible; English auto-caption track listed. Actual caption fetch returned HTTP 200 with zero bytes. Embedded Bunny player rendered 403. Content NOT watched or transcript-reviewed.
2. 20AB Measured Moves — 15:30 sample. Official YouTube mirror https://www.youtube.com/watch?v=cRWGKdmTkKc . YouTube watch HTML accessible; English auto-caption track listed. Caption fetch HTTP 200, zero bytes. Official embedded Bunny player rendered 403. Content NOT watched or primary transcript-reviewed.
3. 37 How to Trade — 14:20 sample. Metadata verified; no playback/subtitle retrieval attempt.
4. 42A Trading Climactic Reversals (Failed Breakouts) — 13:45 sample. Metadata verified; no playback/subtitle retrieval attempt.
5. Trading the Open, TradersEXPO 2017 — full 47:29 presentation drawn from course section 48. Metadata verified; no playback/subtitle retrieval attempt.

## Public live-room items
6. https://www.brookstradingcourse.com/ask-al/trading-room-video-june-12-2020/ — full 2h28m recording advertised. Official page directly fetched. Sprout embed returned “Embedding not allowed on this domain”; did not bypass restriction. No full transcript available in fetched article. Chapter times and description only, NOT watched.
7. https://www.brookstradingcourse.com/ask-al/trading-room-commentary/ — 5:04 excerpt of April 5, 2016 session, posted November 6, 2016. Direct official page HTML fetched; the complete posted transcript was read. Video itself not watched, charts not visually reviewed.

## Actual learning from item 7 (paraphrase)
The live narration weighs repeated weak bear follow-through against bulls still failing to establish control above the moving average. It describes two prior lows plus a failed downside breakout as three pushes, illustrating overlapping double-bottom/wedge interpretation. Prior lower highs become candidate targets. Al changes directional assessments as bars arrive and explicitly remains flat while evidence is inconclusive. The end-of-day label must not be imported into the earlier live decision.
Engineering implications: preserve competing hypotheses and their evidence; allow WAIT despite bullish lean; log revisions at observation time; do not score overlapping shapes as independent evidence. Bar references alone cannot calibrate geometric thresholds without reviewing the chart.

## Real coverage counts, denominator explicitly bounded
- Targeted official video items catalogued here: 7.
- Metadata inspected: 7/7.
- Full official posted transcript read: 1/7 (item 7 only).
- Full primary caption/subtitle files successfully retrieved: 0/7.
- Videos fully watched: 0/7.
- Main requested samples with actual caption retrieval attempted: 2/2 (both empty responses).
- Requested full-room sample playback attempted: 1/1 (embed restriction).
- Other catalogued sample playback not attempted: 3.
- No claim of all-channel coverage, total hours studied, or full Brooks corpus completion.

## Secondary leads excluded from primary evidence
Search surfaced an auto-summary of 12A and an apparent auto-transcript of 20AB on third-party AI sites. They include obvious transcription/summary errors and were not used as authoritative sources. Search also surfaced suspected unauthorized full-course mirrors/torrents; none were fetched. The primary official text sources in public-material-concept-cards.md remain the factual basis until audiovisual evidence can be inspected.
