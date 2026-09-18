# British School in Colombo calendar source notes

Session-derived reference for public BSC calendar ingestion.

## Public sources

- Home page: `https://www.britishschool.lk/`
- Calendar page: `https://www.britishschool.lk/calendar`
- Alternate calendar path: `https://www.britishschool.lk/media/calendar`
- Public iCal feed: `https://www.britishschool.lk/media/calendar/ical/Calendar?showhistory=true`
- Term dates page: `https://www.britishschool.lk/admissions/term-dates`

## Useful observations

- The calendar page exposes an official “Subscribe (iCal)” link.
- The `showhistory=true` iCal feed includes historical and future events.
- In the captured session, the feed returned `text/calendar`, `X-WR-CALNAME:The British School in Colombo Sri Lanka Calendar`, and `X-WR-TIMEZONE:Europe/London`.
- The feed contained 494 `VEVENT` records, ranging from `20170523` to `20271225` at that time.
- The term dates page is separate from the calendar feed and should be checked independently when the user asks for term dates.

## Extraction pattern

1. Fetch the iCal URL with a normal browser-like user agent.
2. Save raw `.ics` unchanged.
3. Unfold RFC5545 continuation lines before parsing.
4. Export normalized `.csv` and `.json` with `dtstart`, `dtend`, `summary`, `description`, `location`, `uid`, `categories`, `status`, and `url` fields.
5. For WhatsApp delivery, attach the raw ICS plus CSV/JSON artifacts and keep the message short.
