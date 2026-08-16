"""Seed the photobooth-route campaign's 45 westside venue leads + manual drafts.

One-off (2026-08-16), idempotent — re-running skips existing rows. The campaign row
must exist first (scripts.sync_campaigns picks up backend/campaigns/photobooth-route/).

Leads are venues, not people: linkedin_url holds the venue's Instagram profile URL
(the unique key + the tap-to-open link in /drafts), email_status stays NULL so the
email sender's deliverability gate can never match them. Drafts use channels
'manual_ig' / 'manual_email', which no sender query matches — the operator sends
every message personally from the dashboard via Copy + Mark sent.

Message style (operator, 2026-08-16): handwritten feel — ZERO hyphens or dashes of
any kind in message bodies (mirrors _humanize()'s no-em-dash rule, extended to all
'-' characters), short plain sentences, contractions, no colon lists. VENUES below
is the single source of truth for bodies; scripts.update_photobooth_bodies pushes
edits here onto existing pending drafts.

    uv run python -m scripts.seed_photobooth_route
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

from config import require

T1, T2, T3 = "Tier 1 target", "Tier 2 target", "Tier 3 target"
SIG = {T1: 5, T2: 3, T3: 2}

# (name, area, tier, ig_handle, email|None, subject|None, vibe, hook, busy, message)
VENUES: list[tuple] = [
    ('The Gaslite', 'Santa Monica · Wilshire', T1, 'thegaslite', None, None,
     'Shoebox karaoke dive since 1962, free popcorn, zero pretension',
     'Karaoke 365 days a year, from 8am on weekends', 'Hour+ waits, packed weekends',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Tavern on Main', 'Santa Monica · Main St', T1, 'tavernonmainsm', 'info@tavernonmainsm.com', 'photo booth for the Tavern?',
     'Neighborhood sports bar, 20+ TVs, karaoke and DJ nights',
     "Main St's only pool table; Most Loved Happy Hour 2025; same owners as Circle Bar + Hinano", 'Game-day + karaoke crowds to 2am',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Circle Bar', 'Santa Monica · Main St', T1, 'circlebarsm', 'info@circlebar-sm.com', None,
     'Red-lit 1949 dive reborn May 2026 as a late-night DJ den',
     'The Halo elevated DJ booth + 8K laser rig; same owners as Tavern on Main + Hinano', 'Nightly DJs Thu-Sat to 2am',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Hinano Cafe', 'Venice · Washington Blvd', T1, 'hinanovenice', 'info@hinanocafevenice.com', None,
     "Sawdust-floor beach dive since 1962, Jim Morrison's local",
     'Bands Fri/Sat/Sun 5pm; legendary charred-patty cheeseburger; same owners as Circle Bar + Tavern on Main', 'Bands 3 nights/wk + NFL Sundays',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ("Ye Olde King's Head", 'Santa Monica · downtown', T1, 'yeoldekingshead', 'info@yeoldekingshead.com', 'a photo booth that pays the pub',
     'British pub institution since 1974, a block from the beach',
     'HOT LEAD: rented a photo booth for their 50th anniversary party (2024)', 'Promenade tourist flow, 1900+ Yelp reviews',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Townhouse & Del Monte Speakeasy', 'Venice · Windward Ave', T1, 'townhousevenice', 'info@townhousevenice.com', 'photo booth for the Del Monte?',
     'Oldest bar in Venice (1915); Prohibition speakeasy basement',
     'Real Prohibition speakeasy (liquor via dumbwaiter); live jazz/comedy/burlesque nightly', 'Weekend lines at the bar, ticketed shows',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Brig', 'Venice · Abbot Kinney', T1, 'thebrigvenice', 'info@thebrig.com', None,
     "Abbot Kinney's last true dive (~70 years), retro remodel, patio",
     'Famous for great mojitos at a shot-and-beer dive', 'Saturday crowds spill onto the patio',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Roosterfish', 'Venice · Abbot Kinney', T1, 'roosterfish_venice', 'RoosterfishAK@gmail.com', 'photo booth idea for Roosterfish',
     'Landmark LGBTQ+ bar since 1979, revived after 2016 closure',
     '18-cocktail craft list; weekend disco/dance nights to 2am', 'Fri-Sun to 2am, weekend dance nights',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ("Prince O' Whales", 'Playa del Rey · Culver Blvd', T1, 'princeowhales', 'prince.o.whales.management@gmail.com', 'photo booth for PoW?',
     'Beachside neighborhood dive since 1955; two bars, two patios',
     'Karaoke Tue/Thu 10pm (Thu hosted by Kiki); ping pong + darts in-bar', 'Popular weekends, late karaoke crowds',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ("Q's Billiard Club", 'Brentwood · Wilshire', T1, 'qsbilliards', 'contact@qsbilliardclub.com', "photo booth for Q's?",
     'Two-story pool-hall sports bar since 1989, DJ nightly',
     '10 red-felt tables; beer pong Sundays; trivia Wednesdays', "Hour+ pool waits, 'entirely too crowded' weekends",
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Nickel Mine', 'West LA · Santa Monica Blvd', T1, 'nickelmine', 'thenickelmine@gmail.com', 'photo booth for the Nickel Mine?',
     "Big independent sports bar (2016), 'well-kept frat house' energy",
     'Hidden speakeasy-style back room (~30 ppl); board games; 24 rotating taps', 'Packed-to-the-gills game days',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Garage on Motor Ave', 'Palms · Motor Ave', T1, 'garageonmotor', 'info@garageonmotor.com', 'photo booth for the Garage?',
     "Palms' sports bar 10+ years; 30+ TVs, fight nights",
     "Hidden back bar 'Motor Club' Wed-Sat to 2am; karaoke Fri/Sat 10pm; UFC/boxing PPVs", 'PPV fight nights pack the room',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ("Harvelle's", 'Santa Monica · 4th St', T1, 'harvellessm', 'info@harvelles.com', "photo booth for Harvelle's?",
     'Candlelit 1931 blues/burlesque club, live acts nightly',
     'Oldest live-music venue on the westside; Toledo Show burlesque Sundays', 'Ticketed shows 7 nights to 2am',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Blind Barber', 'Culver City · Washington Blvd', T1, 'blindbarber_la', None, None,
     'Barbershop-front speakeasy, 1970s styling, DJ + dancefloor',
     "Invite-only 'Secret Show' comedy monthly (Chappelle/Ali Wong drop-ins); grilled cheese menu", 'Crowded after 9:30pm',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Cinema Bar', 'Culver City · Sepulveda', T1, 'thecinemabar_', None, None,
     "'World's smallest honky-tonk' (1947), family-owned 30 years",
     'Free live music 7 nights, no cover; space genuinely tight', 'Packed on band nights',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('No Smoking Bar', 'Culver City Arts District', T1, 'nosmokingbar', None, None,
     'Retro cabin-paneled dive-meets-cocktail bar (ex-Mandrake space)',
     'Opened 2024 in the 18-year Mandrake arts space; frozen ube colada; weekend DJs', "'Overcrowded on busy nights', 2am Fri/Sat",
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Cozy Inn', 'Culver City · Washington Pl', T1, '_cozyinn', None, None,
     'No-frills family dive, 6am-2am, heavy pours, devoted regulars',
     'Vintage shuffleboard mid-bar; own free parking lot', 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Chez Jay', 'Santa Monica · Ocean Ave', T1, 'chezjay1959', 'peanuts@chezjays.com', 'photo booth for Chez Jay?',
     'Nautical 1959 celebrity dive, peanut shells on the floor',
     "A bar peanut flew to the moon on Apollo 14; 'The Backyard' patio bar", 'Small room fills nightly',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Waterfront Venice', 'Venice · boardwalk', T2, 'thewaterfrontvenice', None, None,
     'European-style beer garden on the boardwalk, ocean-view patio',
     'Trivia Thursdays; weekend DJ day-parties; ~28-30k boardwalk passersby daily', 'Boardwalk volume + weekend DJ parties',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Venice West', 'Venice · Lincoln Blvd', T2, 'thevenicewest', 'events@venicemusicgroup.com', 'photo booth for the Venice West?',
     'Beat-era-inspired live music venue, ticketed shows most nights',
     'Books national acts; Beatles/Dead brunches; line-dancing nights; calendar into 2027', 'Ticketed shows most nights',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Lincoln', 'Venice · Lincoln Blvd', T2, 'thelincolnvenice', 'info@thelincolnvenice.com', 'photo booth for The Lincoln?',
     'Dark mid-century cocktail den for Venice locals, opens 7pm',
     'Ford Model T Roadster built into the decor; pours to 2am nightly', 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Baja Cantina', 'Marina del Rey · Washington', T2, 'bajacantinamdr', None, None,
     'Margarita-and-tequila institution since Sept 1975, fire-pit patio',
     '$15 margarita-flight Thursdays; live local music every weekend', 'Busy weekends, 1100+ Yelp reviews',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ("Mo's Place", 'Playa del Rey · Culver Blvd', T2, 'mosplace_pdr', None, None,
     "PdR's classic sports bar 25+ years, 12+ screens",
     'New management added trivia, patio DJs, live music; Best Sports Bar on the Westside', 'Game days pack 12+ screens',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ("Joxer Daly's", 'Culver City · Washington Blvd', T2, 'joxer_d', None, None,
     'Irish pub and sports dive, soccer mornings, pool at night',
     'Thursday karaoke anchor; westside spot for early Premier League broadcasts', 'Karaoke Thursdays popular, soccer mornings',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Scarlet Lady Saloon', 'Culver City · Sepulveda', T2, 'scarlet_lady_saloon', None, None,
     'Strong-pour karaoke dive since 1999, open 8am-2am',
     'Karaoke 5 nights/wk from 9pm; Saints fan bar with full NFL package', 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Daily Pint', 'Santa Monica · Pico', T2, 'thedailypintsm', 'thedailypint@yahoo.com', 'photo booth for the Pint?',
     'British-leaning whiskey-and-beer dive, BYO food',
     '3 cask ales on hand pumps (Imbibe best-cask list); 500-bottle whiskey wall; shuffleboard', 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ("Sonny McLean's", 'Santa Monica · Wilshire', T2, 'sonnymcleans', None, None,
     'Boston-in-exile Irish sports pub, 29 TVs + beer garden',
     '#1 Patriots bar on the West Coast; 9am weekend openings for East Coast kickoffs', 'Boston game days pack the room',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Santa Monica Brew Works', 'Santa Monica · Colorado Ave', T2, 'santamonicabrewworks', 'info@santamonicabrewworks.com', 'photo booth for the taproom?',
     "SM's only production brewery; industrial taproom + beer garden",
     '11.5-ft outdoor jumbotron installed for World Cup 2026; Tuesday trivia; Emmy Squared pizza', 'World Cup viewing hub positioning',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Alibi Room', 'Del Rey · W Washington', T2, 'alibiroomla', 'info@alibiroomla.com', 'photo booth for Alibi Room?',
     'Low-lit neighborhood lounge, 30+ beers, westside date spot',
     "Roy Choi's Kogi test kitchen — Kogi tacos from the bar kitchen; glass-door patio", 'Steady dinner crowds, 1600+ Yelp',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Accomplice Bar', 'Mar Vista · Grand View', T2, 'accomplice_bar', 'info@littlefattyla.com', 'photo booth for Accomplice?',
     'Acclaimed cocktail bar attached to Little Fatty, date-spot energy',
     'Top-10 US cocktail bar, 2024 Spirited Awards; Hainan-chicken-mezcal signature drink', 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Wellesbourne', 'West LA · Pico', T2, 'thewellesbourne', None, None,
     'Candlelit English manor-house lounge, book-lined walls',
     'Live jazz select nights in the library room', 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Dots Space LA', 'Sawtelle Japantown', T2, 'dotsspace_la', 'info@dotsspacela.com', 'photo booth for Dots?',
     'Neon karaoke lounge, public stage + bar, open to 4am nightly',
     '4 themed private karaoke rooms bookable to 3am', 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Purple Orchid', 'El Segundo · Richmond St', T2, 'purpleorchidtikilounge', None, None,
     'Kitschy tiki dive since 2001, tropical drinks till 2am',
     '2 pool tables under the tiki decor; live bands weekend nights', "'Really busy and crowded' Fridays",
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Melody Bar & Grill', 'Westchester · Sepulveda', T2, 'melodylax', None, None,
     'Independent 1952 roadside bar near LAX; locals + airport crews',
     'Wednesday karaoke; monthly live music, themed DJ parties, comedy', 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ("Father's Office", 'Culver City · Helms', T3, 'fathersofficeofficial', 'info@fathersoffice.com', 'photo booth for the Helms patio crowd?',
     'Landmark Helms Bakery gastropub, 36 taps (Sang Yoon group)',
     'No-substitutions Office Burger; Helms patio with free lot parking', "'Packed almost every night'",
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Firestone Walker Propagator', 'Marina del Rey · Washington', T3, 'firestonewalker_propagator', None, None,
     'Pilot brewhouse + gastropub taproom (corporate parent)',
     'On-site R&D brewhouse makes Venice-only beers; Tuesday trivia $22 pizza+pint', '1100+ Yelp, game-day crowds',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('LA Ale Works Culver City', 'Culver City · Ivy Station', T3, 'laaleworks', 'info@laaleworks.com', 'photo booth for the Ivy Station taproom?',
     'Modern 21+ brewery taproom at Ivy Station, 25 taps',
     'Lucky Guess Trivia Tuesdays with organized meetup groups; at the Metro E Line escalators', "Time Out 'local hit'",
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ("Barney's Beanery Westwood", 'Westwood Village', T3, 'barneysbeaneryww', 'info@barneysbeanery.com', 'photo booth for the Westwood room?',
     'Roadhouse-style UCLA hangout, billiards + arcade (small chain)',
     'Trivia Tuesdays 8:30pm; 21+ karaoke Thursdays 10pm', 'Daily Bruin staple, UCLA game days',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ("Rocco's Tavern Westwood", 'Westwood Village', T3, 'roccoswestwood', None, None,
     'THE UCLA bar at Gayley & Weyburn (small chain)',
     'Live-band karaoke nights alongside game-day broadcasts', 'Central student nightlife spot',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Chestnut Club', 'Santa Monica · 14th St', T3, 'thechestnutclub', 'marketing@happytoserveyou.com', 'photo booth for Chestnut?',
     'Moody spirits-driven den, deliberately zero TVs (HTSY group)',
     "400+ bottle back bar; bartender 'preference interview' ritual", 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Library Alehouse', 'Santa Monica · Main St', T3, 'libraryalehouse', 'info@libraryalehouse.com', 'photo booth for the Alehouse?',
     'Wood-paneled craft-beer gastropub since 1995',
     "One of LA's first craft-beer bars; restored 2022 by two young co-owners; 29 Cicerone-curated taps", 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Brixton', 'Santa Monica · Pico', T3, 'thebrixtonsm', 'events@thebrixtonsm.com', 'photo booth for the Brixton?',
     'Casual Pico gastropub-sports hybrid, families early, games late',
     'Latin Night parties; Saturday bottomless brunch from 9:30am', 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('The Mulberry', 'Sawtelle Japantown', T3, 'themulberryla', None, None,
     'New (Jan 2026) Michelin-Guide Korean-American bistro + late bar',
     'Bar pours to 2am Thu-Sat — nearly the only late option on Sawtelle', 'Michelin/Resy buzz, no line reports yet',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('El Segundo Brewing', 'El Segundo · Main St', T3, 'esbcbrews', 'info@elsegundobrewing.com', 'photo booth for the taproom?',
     'Hop-forward production brewery taproom on Main St',
     "Brews Stone Cold Steve Austin's Broken Skull IPA on site; closes 9-10pm", 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
    ('Brewport Tap House', 'El Segundo · Main St', T3, 'brewporttaphouse', None, None,
     'Self-pour craft beer hall, front/back patios + beer garden',
     "60 wristband self-pour taps; 'Trivia with BUDDS' Tuesdays 7pm", 'unknown',
     "Hi, I'm Chance and I put vintage style photo booths in event spaces/bars. Free to the bar, I handle all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply or contact me at 3237101190. Thanks,"),
]


def main() -> None:
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute("select id from campaigns where slug = 'photobooth-route'")
        row = cur.fetchone()
        if not row:
            raise SystemExit("photobooth-route campaign missing — run scripts.sync_campaigns first")
        campaign_id = row[0]
        cur.execute("select id from profiles where is_admin limit 1")
        admin = cur.fetchone()
        admin_id = admin[0] if admin else None

        leads_new = drafts_new = 0
        for name, area, tier, ig, email, subject, vibe, hook, busy, msg in VENUES:
            ig_url = f"https://instagram.com/{ig}"
            cur.execute(
                """
                insert into leads (linkedin_url, name, headline, company, role, location,
                                   campaign_id, user_id, email, source, status, updated_at)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual:photobooth-route','drafted', now())
                on conflict (linkedin_url) do update set updated_at = now()
                returning id, (xmax = 0) as inserted
                """,
                (ig_url, name, vibe, area, tier, "Westside LA",
                 campaign_id, admin_id, email),
            )
            lead_id, inserted = cur.fetchone()
            leads_new += 1 if inserted else 0

            channel = "manual_email" if email and subject else "manual_ig"
            hook_obj = {
                "type": "venue-context",
                "reference": hook,
                "why_it_matters": busy,
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
                (lead_id, channel, Jsonb(hook_obj), msg),
            )
            drafts_new += cur.rowcount
        conn.commit()
        print(f"venues processed: {len(VENUES)}  leads inserted: {leads_new}  drafts inserted: {drafts_new}")

        cur.execute(
            """
            select d.channel, count(*) from drafts d
            join leads l on l.id = d.lead_id
            where l.campaign_id = %s and d.status = 'draft'
            group by 1 order by 1
            """,
            (campaign_id,),
        )
        for ch, n in cur.fetchall():
            print(f"  pending {ch}: {n}")


if __name__ == "__main__":
    main()
