#!/usr/bin/env python3
"""Regression tests for parse_week_ahead in bsc-data-dump.py.

The 2026-06-15 6am HOLD root cause: the day-by-day Week Ahead section
(Year 3 Showcase, KS1 Sports day, Y5 Book Look, etc.) lives beyond the
8000-char newsletter truncation, so the agent never saw "today's events".
parse_week_ahead extracts that section and surfaces it as structured
data with per-day Y3 attribution.

Run:
    cd /opt/data/james-bsc-live-clean/data/.ocplatform/workspace
    python3 -m pytest tests/test_week_ahead_parser.py -v
"""
import importlib.util
import pathlib
import unittest

WS = pathlib.Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace")


def _load_parser():
    spec = importlib.util.spec_from_file_location(
        "bsc_data_dump",
        str(WS / "scripts" / "bsc-data-dump.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse_week_ahead


# Reduced fixture mirroring the 2026-06-14 newsletter shape: prose section
# that mentions inline dates (must NOT be parsed as day headers), then the
# day-by-day section with `Nth MMM` uppercase abbreviation headers.
LIVE_NEWSLETTER = """
Title: Junior School Week Ahead
THE WEEK AHEAD FOR BSC JUNIORS

**Key Stage 1&2 - Notices from Ms Lakmali**
**Year 2 - Significant People** Children are welcome to dress up on Friday, 19th June.
**Year 6 Got Talent Auditions - Tuesday, 16th June** auditions take place on Tuesday, 16th June.
**Year 5 Book Look - Wednesday, 17th June** the Book Look will now be held for Year 5 parents only.

**Term Dates for Academic Year 2026-27**

15th JUN![Image](url)_Parent Collective Volunteer Meeting for 2026/27 - **7.30am to 8.30am - Lecture Hall** Year 3 Showcase at **12.30pm** **KS1 Sports day - Year 1 at 8.00 am-10.00am/ Year 2 at 11:00am -1.15pm**_ _**Nursery Stay & Splash morning 7.45am-8.30am**_

16th JUN![Image](url)_Nursery Stay & Splash morning **7.45am-8.30am**_ _**Junior Duke Assembly from 8.15am-9am Prize Giving PG A at 9.30am to 11.00am**_

17th JUN![Image](url)_**Prize Giving PG B at 9.30am to 11.00am**_ _**Year 5 Book Look from 12.30pm-1.30pm**_

18th JUN![Image](url)_**Prize Giving PG C at 9.30 am to 11.00am**_ _**Step up day Nursery- Year 6- 7.45-9.45am**_

19th JUN![Image](url)_**Step Up Morning Playgroup to Nursery 8am to 9:30 Academy Concert at 2pm**_ _**Last Day for ECAs**_

22nd JUN![Image](url)_**Nursery & Reception Prize Giving at 8.30am to 10am**_ _**KS1 Prize Giving at 10.30am -12pm**_

[](http://britishschool.lk/events/)_Tuesday 23rd June_ _Year 3 & 4 Prize Giving at 8.30am-10.00am_

CONNECT WITH /BSColomboLK
"""


class WeekAheadParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = _load_parser()
        self.result = self.parser(LIVE_NEWSLETTER, "2026-06-14")

    def test_finds_six_day_entries(self):
        dates = [r["date"] for r in self.result]
        self.assertEqual(dates, [
            "2026-06-15", "2026-06-16", "2026-06-17",
            "2026-06-18", "2026-06-19", "2026-06-22",
        ])

    def test_ignores_inline_prose_dates(self):
        # "Friday, 19th June" and "Tuesday, 16th June" appear in the prose
        # section. Those must NOT generate duplicate entries — only one entry
        # per date, anchored to the day-by-day section.
        from collections import Counter
        date_counts = Counter(r["date"] for r in self.result)
        for d, c in date_counts.items():
            self.assertEqual(c, 1, f"{d} appears {c} times — prose date leaked into headers")

    def test_today_15jun_is_y3_relevant(self):
        today = next(r for r in self.result if r["date"] == "2026-06-15")
        self.assertTrue(today["y3_relevant"],
            f"15 Jun must be Y3-relevant (Year 3 Showcase): {today}")
        self.assertIn("Year 3", today["year_groups_mentioned"])
        self.assertIn("Year 3 Showcase", today["raw_excerpt"])

    def test_17jun_y5_book_look_is_not_y3_relevant(self):
        wed = next(r for r in self.result if r["date"] == "2026-06-17")
        self.assertFalse(wed["y3_relevant"],
            f"17 Jun is Year 5 only Book Look — must NOT be Y3-relevant: {wed}")
        self.assertIn("Year 5", wed["year_groups_mentioned"])

    def test_22jun_nursery_reception_ks1_only_not_y3(self):
        mon22 = next(r for r in self.result if r["date"] == "2026-06-22")
        self.assertFalse(mon22["y3_relevant"],
            f"22 Jun has only Nursery/Reception/KS1 events: {mon22}")

    def test_18jun_step_up_day_includes_year_6(self):
        thu = next(r for r in self.result if r["date"] == "2026-06-18")
        self.assertIn("Year 6", thu["year_groups_mentioned"])
        # Step up day Nursery-Year 6 covers Year 3 → relevant
        self.assertTrue(thu["y3_relevant"])

    def test_footer_section_not_appended_to_last_day(self):
        # The Tuesday 23rd June "Coming Up" section and CONNECT WITH footer
        # must not bleed into the 22 Jun entry.
        mon22 = next(r for r in self.result if r["date"] == "2026-06-22")
        self.assertNotIn("Tuesday 23rd June", mon22["raw_excerpt"])
        self.assertNotIn("CONNECT WITH", mon22["raw_excerpt"])

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(self.parser("", "2026-06-14"), [])
        self.assertEqual(self.parser(None, "2026-06-14"), [])

    def test_missing_issue_date_returns_empty(self):
        self.assertEqual(self.parser(LIVE_NEWSLETTER, None), [])
        self.assertEqual(self.parser(LIVE_NEWSLETTER, "garbage"), [])

    def test_day_names_match_iso_dates(self):
        for r in self.result:
            from datetime import date
            d = date.fromisoformat(r["date"])
            self.assertEqual(r["day_name"], d.strftime("%A"),
                f"day_name mismatch for {r['date']}: {r['day_name']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
