"""Seed wave 2 of the photobooth route: bowling, entertainment centers, barcades, pool
halls, music/comedy venues, breweries with event programs, and private event venues.

Researched 2026-08-17. Idempotent, re-running skips existing rows. Same manual-send model
as wave 1: channels manual_ig / manual_email, campaign stays paused, operator sends every
message personally from the dashboard.

TIERING IS BY GEOGRAPHY, not just fit. The vending research established that in LA drive
time is the binding constraint on a route business, and these venues sprawl from Saugus to
Long Beach. T1 = central + westside (the service core), T2 = valley and near south bay,
T3 = far south and southeast county.

TWO MESSAGE VARIANTS. Most venues get the standard coin-op pitch. Private event venues
(SmogShoppe, Millwick, Mack Sennett) get a package pitch instead, because guests do not pay
per strip at a private party. There the venue adds the booth to client packages.

Dropped from the research output:
  - Tiny's Hi-Dive: already has a booth (was on the wave 1 exclusion list; the barcade
    agent returned it as "unknown", which was wrong)
  - EightyTwo, Shatto 39: returned by both the bowling and barcade agents, deduped here
  - Barcade Highland Park, Golf N' Stuff, Lucky Strike Mar Vista, Lucky Strike Hollywood:
    no usable direct contact (form only, no local IG). Walk-in targets only.

    uv run python -m scripts.seed_photobooth_wave2
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

from config import require

T1 = "Wave2 T1 (central)"
T2 = "Wave2 T2 (valley/near south)"
T3 = "Wave2 T3 (far)"
SIG = {T1: 5, T2: 3, T3: 2}

MSG_COINOP = (
    "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. "
    "Free to the bar, I handle all upkeep, you keep a cut of every strip. "
    "Is that your call or the owner's? Feel free to reply or contact me at "
    "3237101190. Thanks,"
)

MSG_PACKAGE = (
    "Hi, I'm Chance and I put vintage style photo booths in event spaces. "
    "Free to install, I handle all upkeep, and you can offer it in client packages "
    "and keep a cut. Is that your call or the owner's? Feel free to reply or contact "
    "me at 3237101190. Thanks,"
)

# Booth status came back "unknown" rather than a confirmed no. Glance at IG before sending.
UNVERIFIED = {
    "busbyswest", "sportsfestus", "shatto39", "rhythmroomla", "goldengopherla",
    "tonysdartsaway", "mrfurleysbar", "lanesoaktree", "gardenabowl",
}

# (name, area, tier, url, email|None, subject|None, vibe, hook, busy, package?)
VENUES: list[tuple] = [
    # ================= T1: central + westside =================
    ("EightyTwo", "DTLA Arts District", T1, "https://instagram.com/eightytwola",
     "info@eightytwo.la", "photo booth for EightyTwo?",
     "21+ vintage barcade, dark warehouse floor, nightly DJs, 3000 sq ft patio",
     "55+ quarter fed pinball and arcade cabinets; refuses reservations Fri to Sun because the room fills",
     "1733 Yelp reviews, 2am close Tue to Sun", False),
    ("Shatto 39 Lanes", "Koreatown", T1, "https://instagram.com/shatto39", None, None,
     "Googie era 39 lane bowling palace, nearly untouched since 1954",
     "Invader installed a Big Lebowski mosaic on the exterior in 2018; interior is original 1954 fabric",
     "593 Yelp reviews, open to 2am every day including holidays, free parking", False),
    ("XLanes LA", "Little Tokyo, DTLA", T1, "https://instagram.com/xlanesla",
     "info@xlanesla.com", "photo booth for XLanes?",
     "50,000 sq ft complex: bowling, karaoke, billiards, arcade, sports bar",
     "Three named VIP bowling suites at $275 to $425/hr plus 4 private karaoke rooms and weekend DJs",
     "1175 Yelp reviews, open to 2am Fri and Sat", False),
    ("Highland Park Bowl", "Highland Park", T1, "https://instagram.com/highlandparkbowl",
     None, None,
     "Restored Prohibition era bowling cathedral, cocktail destination more than an alley",
     "LA's oldest bowling alley (1927); restoration uncovered a 1930s mural and built chandeliers from salvaged pinsetter parts",
     "880+ Yelp reviews, only 8 lanes so waits are routine. 1933 Group decision, not a GM", False),
    ("Busby's West", "Santa Monica", T1, "https://instagram.com/busbyswest",
     "bigmikebusbys@gmail.com", "photo booth for Busby's?",
     "Big multi room westside sports bar where every side room is a game room",
     "Event bookings go to an owner's personal address, not an agency. Decision maker is one email away",
     "816 Yelp reviews, open to 1:30am daily", False),
    ("SportsFest", "Santa Monica", T1, "https://instagram.com/sportsfestus", None, None,
     "Indoor batting cage and games complex with two full bars, a block off the Promenade",
     "Cages convert for padel and cricket, and Britannia Pub runs the kitchen instead of an in house one",
     "Open to 2am Mon to Sat, 10am weekend opens for early game slates", False),
    ("Blipsy Bar", "East Hollywood", T1, "https://instagram.com/blipsybar", None, None,
     "Cash only dive that claims to be LA's original arcade bar, open since 2010",
     "Still cash only, was Miss T's Barcade before the rename, DJs almost nightly",
     "396 Yelp reviews, DJ or live act nearly every night", False),
    ("Walt's Bar", "Eagle Rock", T1, "https://instagram.com/waltsbar", None, None,
     "Rockabilly pinball dive in a former plumber's shop, beer wine and hot dogs",
     "The entire food menu is hot dogs and pretzels, the pinball row is the actual draw",
     "176 Yelp reviews, open to 2am Fri and Sat", False),
    ("Rhythm Room LA", "DTLA Historic Core", T1, "https://www.rhythmroomla.com",
     "info@rhythmroomla.com", "photo booth for Rhythm Room?",
     "Basement speakeasy where a live music stage and a full game room share one room",
     "Only takes event inquiries at 50+ guests and runs a dedicated games page separate from the music calendar",
     "423 Yelp reviews, Thu to Sat 6pm to 2am on a booked live music calendar", False),
    ("Golden Gopher", "DTLA Jewelry District", T1, "https://instagram.com/goldengopherla",
     None, None,
     "DTLA's oldest bar (1905), exposed brick, coin op cabinets on the floor",
     "Holds a to go liquor license carried over from its 1905 saloon permit, almost unique in LA",
     "821 Yelp reviews, long running DTLA nightlife anchor with 16 taps", False),
    ("Westside Comedy Theater", "Santa Monica", T1, "https://westsidecomedy.com",
     "chris@westsidecomedy.com", "photo booth for Westside Comedy?",
     "Intimate alley entrance comedy theater off the Promenade, standup plus resident improv teams",
     "Beer and wine bar with 30 beers, unusual for a comedy theater this size. Email goes to a named person",
     "Shows 7 nights a week, 235+ Yelp reviews, ticketed", False),
    ("TRiP Santa Monica", "Santa Monica, Lincoln Blvd", T1,
     "https://instagram.com/tripsantamonica_", "booking@tripsantamonica.com",
     "photo booth for TRiP?",
     "21+ Lincoln Blvd music room running a different themed night every night",
     "Named recurring nights: Open Mic Mondays, 20Q Trivia, Jazz Night, Latin Night",
     "Live music 7 days a week, 21+ door, open to midnight nightly", False),
    ("The Mint", "Mid-City, Pico Blvd", T1, "https://themintla.com",
     "booking@themintla.com", "photo booth for The Mint?",
     "1937 landmark listening room built like a recording studio, food and full bar",
     "Acoustically engineered as a recording studio; alumni wall includes Ray Charles, Stevie Wonder, Herbie Hancock",
     "Shows 7 nights a week, open to 2am Fri and Sat, 405+ Yelp reviews", False),
    ("Lodge Room", "Highland Park", T1, "https://www.lodgeroomhlp.com",
     "info@lodgeroomhlp.com", "photo booth for Lodge Room?",
     "500 cap restored Masonic lodge upstairs, cherry wood paneling, indie touring bookings",
     "Housed in the 1923 Highland Park Masonic Temple with original lodge woodwork; Checker Hall restaurant downstairs 7 nights",
     "Calendar booked solid into 2027, 5 to 7 shows a week", False),
    ("Zebulon Cafe Concert", "Frogtown", T1, "https://zebulon.la", "info@zebulon.la",
     "photo booth for Zebulon?",
     "1930s warehouse turned cafe bar venue, eclectic bookings that turn into a dancefloor late",
     "Revival of the Brooklyn original that closed in 2012; converts to one big dancefloor after 11pm on weekends",
     "Weekend late night dancefloor conversion, listed on Resident Advisor", False),
    ("Moroccan Lounge", "DTLA, Little Tokyo edge", T1, "https://themoroccan.com",
     "info@themoroccan.com", "photo booth for Moroccan Lounge?",
     "Small tiled listening room with a separate front bar that keeps its own crowd",
     "Runs as a three venue group with Teragram Ballroom and The Bellwether. One conversation could cover three rooms",
     "Active calendar Aug to Oct 2026; front bar draws walk ins independent of the show", False),
    ("Gold-Diggers", "East Hollywood", T1, "https://gold-diggers.com",
     "barinfo@gold-diggers.com", "photo booth for Gold-Diggers?",
     "Bar, 150 cap club, boutique hotel and recording studio stacked in one building",
     "One address combines a 150 person club, a 10 room hotel and seven recording studios plus a soundstage",
     "Shows nightly; hotel guests and studio clients feed the bar independently of ticket sales", False),
    ("1720", "DTLA Produce District", T1, "https://instagram.com/1720warehouse", None, None,
     "Raw warehouse running electronic, rave, punk and metal nights for a costume forward crowd",
     "Programming spans techno raves to metal including themed rave nights, in a straight warehouse shell",
     "Ticketed events nearly every weekend, calendar booked months out", False),
    ("The Elysian Theater", "Frogtown", T1, "https://elysiantheater.com",
     "hello@elysiantheater.com", "photo booth for The Elysian?",
     "Scrappy alt comedy house running improv, clown and variety across three rooms at once",
     "Three stages under one roof: the Main Room, The Vault and the Skunk Room",
     "50+ events in a single sampled period, multiple shows stacked per night", False),
    ("Highland Park Brewery Chinatown", "Chinatown", T1, "https://instagram.com/hpbrewing",
     None, None,
     "Chef driven brewery taproom with a patio, food and beer crowd rather than a pure beer crowd",
     "Sits in the Chinatown yard next to the Metro A Line, feeding on Dodger Stadium and Chinatown event traffic",
     "Dodger game day and Chinatown event overflow, patio turns over on weekends", False),
    ("SmogShoppe", "Culver City Arts District", T1, "https://instagram.com/smogshoppe",
     None, None,
     "Former smog check station turned vertical garden wedding venue, 100 to 250 guests",
     "Their own site markets a Magic Closet nook as perfect for selfie stations. A booth alcove already spec'd",
     "100% solar powered venue booking weddings, brand events and shoots year round", True),
    ("Millwick", "DTLA Arts District", T1, "https://instagram.com/millwick_dtla", None, None,
     "Indoor outdoor Arts District courtyard venue, 150 seated to 250 standing",
     "Same owner as SmogShoppe under Marvimon Productions, so one conversation covers two venues",
     "Books weddings, wrap parties, brand experiences and film shoots on one calendar", True),
    ("Mack Sennett Studios", "Silver Lake", T1, "https://macksennett.com",
     "info@macksennett.com", "photo booth for Mack Sennett?",
     "1916 silent film soundstage running as a premiere, launch and wedding venue",
     "Operates out of Mack Sennett's original 1916 Keystone studio, the oldest surviving film stage in LA",
     "Steady production, premiere and private event bookings across multiple stages", True),

    # ================= T2: valley + near south bay =================
    ("Player One Arcade Bar", "North Hollywood", T2,
     "https://instagram.com/player_one_noho", "playeroneevents@gmail.com",
     "photo booth for Player One?",
     "The Valley's largest arcade bar, 5400 sq ft of 80s and 90s cabinets",
     "Hosted Entertainment Weekly's Three Rounds shoot with the Abbott Elementary cast inside the arcade",
     "226 Yelp reviews, already sells party buyouts and reserved game tables", False),
    ("Pinz Bowling Kitchen + Bar", "Studio City", T2, "https://instagram.com/pinzla",
     "info@pinzla.com", "photo booth for Pinz?",
     "Ventura Blvd industry hangout, 60,000 sq ft of boutique lanes, arcade and a real kitchen",
     "Open since 1958 and openly markets its celebrity regulars; arcade stocks hard to find pinball machines",
     "908 Yelp reviews, open to 1am Fri and Sat, runs leagues and private events", False),
    ("Mr. Furley's Bar", "Sherman Oaks", T2, "https://instagram.com/mrfurleysbar", None, None,
     "Three's Company themed bar group built entirely around bar games, 5pm to 2am daily",
     "Opened a dedicated billiards room in NoHo in 2025, five rooms now and still adding game space",
     "All five locations open 5pm to 2am daily. Multi venue upside if one works", False),
    ("Tony's Darts Away", "Burbank", T2, "https://instagram.com/tonysdartsaway",
     "info@tonys.la", "photo booth for Tony's?",
     "All California draft list gastropub on Magnolia Blvd, named for its dart boards",
     "100% California only draft list and a vegan sausage menu, a dart bar that leads with the beer program",
     "1373 Yelp reviews, Magnolia Park corridor anchor", False),
    ("Corbin Bowl", "Tarzana", T2, "https://instagram.com/corbinbowl", None, None,
     "1959 Valley institution with a real live music bar bolted onto the lanes",
     "Bar 10 is booked as an actual music venue, listed on Indie on the Move, with open mics comedy and trivia",
     "468 Yelp reviews, leagues for all ages, recurring nightly event calendar", False),
    ("Montrose Bowl", "Montrose, Glendale", T2, "https://instagram.com/montrose.bowl",
     "info@montrosebowl.com", "photo booth for Montrose Bowl?",
     "Eight lane 1936 time capsule rented out whole, almost every weekend is a private party",
     "Still scored by pencil and paper; filming location for Teen Wolf, Pleasantville and The Outsiders",
     "Weekends booked solid with private parties. Beer and wine only, no full liquor", False),
    ("Three Weavers Brewing", "Inglewood", T2, "https://www.threeweavers.la",
     "info@threeweavers.la", "photo booth for Three Weavers?",
     "Large dog friendly Inglewood taproom, first come seating, fully cashless",
     "Fully cashless taking cards and Apple Pay only. A card reader booth matches exactly how guests already pay",
     "500+ Yelp reviews, open to 11pm Fri and Sat, in the SoFi and Intuit Dome corridor", False),
    ("Common Space Brewery", "Hawthorne", T2, "https://www.commonspace.la",
     "hi@commonspace.la", "photo booth for Common Space?",
     "Big community minded taproom that treats its event calendar as the main draw",
     "Weekly program runs past the usual trivia into plant bingo and on site Ren Faires",
     "Open to midnight Fri and Sat, weekly events plus Dodgers, NFL and World Cup watch parties", False),
    ("Smog City Brewing", "Torrance", T2, "https://instagram.com/smogcitybeer", None, None,
     "Established South Bay production brewery, taproom programs music three nights a week",
     "HAS HIRED A BOOTH VENDOR FOR A THEMED EVENT BEFORE. Demonstrated demand, like King's Head",
     "Live music every Wed, Fri and Sun, plus themed parties like their Emo Night", False),
    ("Mr. Lucky's Billiards", "Torrance", T2, "https://instagram.com/mrluckysbilliards",
     "cheever1343@yahoo.com", "photo booth for Mr. Lucky's?",
     "Serious South Bay pool room with a real bar, league and tournament regulars",
     "Advertises table condition (Simonis wool refelts, dead straight rails) rather than drink specials",
     "Open to 2am Fri and Sat, weekly BCA sanctioned leagues fill tables", False),

    # ================= T3: far south and southeast county =================
    ("Good Times Billiards", "Lakewood", T3, "https://instagram.com/goodtimes_billiards",
     "play@gtbilliards.com", "photo booth for Good Times?",
     "Large 7 day Lakewood pool hall, 18+ after 10pm, rotating kitchen pop up",
     "26 pool tables across four table types, running a Race to One tournament with $1500 added",
     "Open 10am to 2am seven days, weekly APA BCA and USAPL leagues", False),
    ("Cal Bowl", "Lakewood", T3, "https://instagram.com/cal.bowl", "info@calbowl.com",
     "photo booth for Cal Bowl?",
     "68 lane Long Beach area megacenter with a karaoke lounge and a soul food restaurant inside",
     "68 lanes running cosmic bowling under disco lights, plus named house leagues",
     "Sheer scale, arcade open to 11pm, weekend hours to midnight, deep league roster", False),
    ("Gardena Bowl", "Gardena", T3, "https://instagram.com/gardenabowl", None, None,
     "Budget South Bay alley where the attached coffee shop is as much of a draw as the lanes",
     "Runs a full service coffee shop and a 10 table billiards room alongside league play",
     "246 Yelp reviews, leagues for all ages, pro shop on site", False),
    ("Del Rio Lanes", "Downey", T3, "https://instagram.com/delriolanes",
     "info@delriolanes.com", "photo booth for Del Rio?",
     "1959 southeast LA County neighborhood alley with a pizza counter and a loyal league base",
     "Friday and Saturday cosmic bowling on glow lanes, and Vegas Leagues whose sweepers run in Las Vegas",
     "League heavy with annual tournaments, Squeezy's Pizza on site drives its own traffic", False),
    ("Oak Tree Lanes", "Diamond Bar", T3, "https://instagram.com/lanesoaktree", None, None,
     "East county bowling and sports bar combo, the local default since 1978",
     "Trades as Oak Tree Lanes Bowling and Sports Bar, cosmic Friday glow nights, cornhole and pool",
     "284 Yelp reviews, open to midnight Thu to Sat, extensive arcade", False),
    ("Santa Clarita Lanes", "Saugus", T3, "https://santaclaritalanes.com",
     "info@santaclaritalanes.com", "photo booth for Santa Clarita Lanes?",
     "North county alley that doubles as an adult betting parlor",
     "On site off track horse betting is back open, an adult dwell time draw almost no other LA alley has",
     "Weekly leagues with winter and summer 2026 schedules published, quarterly tournaments", False),
    ("Beachwood Blendery", "Long Beach", T3, "https://instagram.com/beachwoodblendery",
     None, None,
     "Sour beer blendery taproom that doubles as a game room with a stay put crowd",
     "Already runs paid amusements on site including pinball, pool and darts, so coin op is a known category to them",
     "Existing coin op machines indicate a crowd that stays and spends on play", False),
    ("Que Sera", "Long Beach, Rose Park", T3, "https://www.queseralb.com",
     "hello@queseralb.com", "photo booth for Que Sera?",
     "Long running neighborhood live music bar with a loyal LGBTQ+ and local band following",
     "Takes direct show submissions through a Book A Show form on its own site rather than a promoter",
     "Regular show calendar with bands booking directly, established Rose Park anchor", False),
]


def main() -> None:
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute("select id from campaigns where slug = 'photobooth-route'")
        row = cur.fetchone()
        if not row:
            raise SystemExit("photobooth-route campaign missing, run scripts.sync_campaigns first")
        campaign_id = row[0]
        cur.execute("select id from profiles where is_admin limit 1")
        admin = cur.fetchone()
        admin_id = admin[0] if admin else None

        leads_new = drafts_new = 0
        for name, area, tier, url, email, subject, vibe, hook, busy, package in VENUES:
            cur.execute(
                """
                insert into leads (linkedin_url, name, headline, company, role, location,
                                   campaign_id, user_id, email, source, status, updated_at)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual:photobooth-wave2','drafted', now())
                on conflict (linkedin_url) do update set updated_at = now()
                returning id, (xmax = 0) as inserted
                """,
                (url, name, vibe, area, tier, "Los Angeles County",
                 campaign_id, admin_id, email),
            )
            lead_id, inserted = cur.fetchone()
            leads_new += 1 if inserted else 0

            channel = "manual_email" if email and subject else "manual_ig"
            handle = url.rsplit("/", 1)[-1] if "instagram.com" in url else ""
            why = busy
            if handle in UNVERIFIED:
                why += " | CHECK IG FOR AN EXISTING BOOTH BEFORE SENDING"
            hook_obj = {
                "type": "package-venue" if package else "venue-context",
                "reference": hook,
                "why_it_matters": why,
                "signal_strength": SIG[tier],
            }
            if subject:
                hook_obj["subject"] = subject
            cur.execute(
                """
                insert into drafts (lead_id, channel, step_index, hook, body, status, variant)
                values (%s, %s, 0, %s, %s, 'draft', 'manual')
                on conflict (lead_id, channel, step_index, variant) do nothing
                """,
                (lead_id, channel, Jsonb(hook_obj),
                 MSG_PACKAGE if package else MSG_COINOP),
            )
            drafts_new += cur.rowcount
        conn.commit()
        print(f"wave 2 venues: {len(VENUES)}  leads inserted: {leads_new}  drafts inserted: {drafts_new}")

        cur.execute(
            """
            select l.role, d.channel, count(*) from drafts d
            join leads l on l.id = d.lead_id
            where l.campaign_id = %s and d.status = 'draft'
            group by 1, 2 order by 1, 2
            """,
            (campaign_id,),
        )
        for role, ch, n in cur.fetchall():
            print(f"  pending {role or '(wave1)'} / {ch}: {n}")


if __name__ == "__main__":
    main()
